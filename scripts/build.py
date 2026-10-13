#!/usr/bin/env python3
"""Generate every platform-specific file from src/ (contract: docs/architecture.md).

    python scripts/build.py            regenerate the generated files
    python scripts/build.py --check    list files that differ from src/ and exit 1 (CI)

Python 3.11+, standard library only. Never edit generated files by hand.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
import sys
import tomllib

REPO = Path(__file__).resolve().parents[1]
SKILL_NAME = "orchestrate"  # fixed: GENERATED_ROOTS and scripts/install.py use this name

PLATFORMS = ("claude", "codex")
ACCESS_KINDS = ("write", "read-shell", "read-only")
# The only directories the build may write to or delete from (repo-relative, POSIX).
GENERATED_ROOTS = ("skills/orchestrate", "codex/agents", "plugins", ".claude-plugin")

# access -> (frontmatter key, value) for Claude Code agents; see the table in docs/architecture.md.
CLAUDE_ACCESS = {
    "write": ("disallowedTools", "Agent"),
    "read-shell": ("disallowedTools", "Write, Edit, NotebookEdit, Agent"),
    "read-only": ("tools", "Read, Grep, Glob, WebFetch, WebSearch, SendMessage"),
}
CODEX_SANDBOX = {"write": None, "read-shell": "read-only", "read-only": "read-only"}
# One-line meaning of each access kind, written into role briefs. A brief may be injected into a
# general-purpose agent where nothing enforces the access, so it must be stated as an expectation.
ACCESS_NOTES = {
    "claude": {
        "write": "may edit files inside the assignment.",
        "read-shell": "may read, search and run checks such as tests or static analysis, but must not "
                      "modify files (the shell stays available, so this is an instruction, not enforcement).",
        "read-only": "may only read and search files and the web; no shell commands and no file changes "
                     "(enforced by the installed role agent's tool allowlist; an instruction in a general-purpose agent).",
    },
    "codex": {
        "write": "may edit files inside the assignment.",
        "read-shell": "may read, search and run checks such as tests or static analysis, but must not "
                      "modify files (`sandbox_mode = \"read-only\"`, advisory).",
        "read-only": "may only read and search; no file changes and no commands that change state "
                     "(`sandbox_mode = \"read-only\"`, advisory).",
    },
}
CLAUDE_COLORS = frozenset({"red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"})
DEFAULT_KEYWORDS = ("orchestration", "multi-agent", "subagents")
CATALOG_SOURCE = "references/roles.md"  # the only skill file that may use {{role-catalog}}
# {{name}} tokens that render a manifest value as is.
SCALAR_TOKENS = ("version", "repository", "marketplace")

MANIFEST_REQUIRED = ("version", "repository", "license", "author", "marketplace", "skill", "packs")
MANIFEST_OPTIONAL = ("description", "keywords", "legacy")  # [legacy] belongs to install.py
SKILL_KEYS = ("name", "display_name", "short_description")
PACK_REQUIRED = ("description", "platforms")
PACK_OPTIONAL = ("plugin", "color", "keywords")
ROLE_REQUIRED = ("id", "pack", "description", "instructions")
ROLE_OPTIONAL = ("access", "platforms")
# Every installed agent's description is loaded into each session, so keep them short.
MAX_DESCRIPTION = 200

KEBAB = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
VERSION = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]+)?")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
# Characters that cannot appear unescaped in one-line values shared by TOML, YAML and JSON output.
LINE_UNSAFE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")
# Characters a TOML multi-line literal string cannot contain (tab and LF are allowed).
LITERAL_UNSAFE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
MARKER = re.compile(r"[ \t]*<!--[ \t]*@([A-Za-z0-9_-]+)[ \t]*-->[ \t]*")
MARKER_ANYWHERE = re.compile(r"<!--\s*@")
TOKEN = re.compile(r"\{\{(.*?)\}\}")
# A workflow script starts with its meta literal, and meta.name comes first and equals the file stem.
WORKFLOW_META = re.compile(r"\Aexport const meta = \{\s*name:\s*(['\"])([^'\"\n]*)\1")
_REMOVED = object()  # placeholder for a line removed by a platform block


class BuildError(Exception):
    """Invalid source or unsafe output. The message names the offending file."""


@dataclass(frozen=True)
class Pack:
    id: str
    description: str
    plugin: str | None
    platforms: tuple[str, ...]
    color: str | None
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class Role:
    id: str
    pack: str
    description: str
    access: str
    platforms: tuple[str, ...]
    instructions: str
    label: str
    instructions_line: int = 1  # file line of the first instructions line, for error messages


@dataclass(frozen=True)
class Source:
    root: Path
    version: str
    repository: str
    license: str
    author: str
    marketplace: str
    description: str
    keywords: tuple[str, ...]
    skill: dict
    packs: dict  # pack id -> Pack, manifest order
    roles: dict  # role id -> Role, ordered by pack (manifest order) then id
    common: str

    def label(self, path: Path) -> str:
        return f"{self.root.name}/{path.relative_to(self.root).as_posix()}"

    def roles_for(self, platform: str) -> list[Role]:
        return [role for role in self.roles.values() if platform in role.platforms]

    def plugin_packs(self) -> list[Pack]:
        return [pack for pack in self.packs.values() if "claude" in pack.platforms]


# --------------------------------------------------------------------------- source loading

def _read_text(path: Path, label: str) -> str:
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BuildError(f"{label}: not valid UTF-8 ({exc})") from None
    # A Windows checkout may carry a BOM or CRLF; outputs are always LF without BOM.
    return text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")


def _parse_toml(text: str, label: str) -> dict:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise BuildError(f"{label}: invalid TOML: {exc}") from None


def _read_toml(path: Path, label: str) -> dict:
    return _parse_toml(_read_text(path, label), label)


def _value_line(text: str, key: str) -> int:
    """File line where the value of a top-level `key = '''...` multi-line string starts."""
    match = re.search(rf"^[ \t]*{re.escape(key)}[ \t]*=[ \t]*('''|\"\"\")?(\n)?", text, re.M)
    if not match:
        return 1
    return text.count("\n", 0, match.start()) + 1 + (1 if match.group(1) and match.group(2) else 0)


def _check_keys(table, label: str, required, optional=()) -> None:
    if not isinstance(table, dict):
        raise BuildError(f"{label}: must be a table")
    missing = [key for key in required if key not in table]
    if missing:
        raise BuildError(f"{label}: missing required key(s): {', '.join(missing)}")
    unknown = sorted(set(table) - set(required) - set(optional))
    if unknown:
        raise BuildError(f"{label}: unknown key(s): {', '.join(unknown)}")


def _line(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BuildError(f"{label}: must be a non-empty string")
    if value != value.strip() or LINE_UNSAFE.search(value):
        raise BuildError(f"{label}: must be one line without control characters or surrounding spaces")
    if "{{" in value or "<!--" in value:
        raise BuildError(f"{label}: one-line values are not rendered, so they cannot use {{{{...}}}} tokens "
                         "or <!-- --> markers")
    return value


def _kebab(value, label: str) -> str:
    if not isinstance(value, str) or not KEBAB.fullmatch(value):
        raise BuildError(f"{label}: {value!r} is not kebab-case")
    return value


def _strings(value, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise BuildError(f"{label}: must be a non-empty list of strings")
    items = tuple(_line(item, label) for item in value)
    if len(set(items)) != len(items):
        raise BuildError(f"{label}: duplicate entries")
    return items


def _platforms(value, label: str) -> tuple[str, ...]:
    items = _strings(value, label)
    unknown = [item for item in items if item not in PLATFORMS]
    if unknown:
        raise BuildError(f"{label}: unknown platform(s) {', '.join(unknown)} (expected {', '.join(PLATFORMS)})")
    return tuple(platform for platform in PLATFORMS if platform in items)


def load_source(src: Path) -> Source:
    """Parse and strictly validate src/manifest.toml, src/roles/*.toml and src/roles/_common.md."""
    src = Path(src)
    tag = src.name or str(src)
    manifest_path = src / "manifest.toml"
    ml = f"{tag}/manifest.toml"
    if not manifest_path.is_file():
        raise BuildError(f"{ml}: missing")
    manifest = _read_toml(manifest_path, ml)
    _check_keys(manifest, ml, MANIFEST_REQUIRED, MANIFEST_OPTIONAL)

    version = _line(manifest["version"], f"{ml}: version")
    if not VERSION.fullmatch(version):
        raise BuildError(f"{ml}: version {version!r} is not MAJOR.MINOR.PATCH")
    repository = _line(manifest["repository"], f"{ml}: repository")
    if not REPOSITORY.fullmatch(repository):
        raise BuildError(f"{ml}: repository {repository!r} must be 'owner/name'")
    skill_table = manifest["skill"]
    _check_keys(skill_table, f"{ml} [skill]", SKILL_KEYS)
    if skill_table["name"] != SKILL_NAME:
        raise BuildError(f"{ml} [skill] name must be {SKILL_NAME!r}: the generated roots and scripts/install.py "
                         "use that name")
    skill = {
        "name": _kebab(skill_table["name"], f"{ml} [skill] name"),
        "display_name": _line(skill_table["display_name"], f"{ml} [skill] display_name"),
        "short_description": _line(skill_table["short_description"], f"{ml} [skill] short_description"),
    }
    if "legacy" in manifest and not isinstance(manifest["legacy"], dict):
        raise BuildError(f"{ml}: [legacy] must be a table")

    packs_table = manifest["packs"]
    if not isinstance(packs_table, dict) or not packs_table:
        raise BuildError(f"{ml}: [packs] must define at least one pack")
    packs: dict[str, Pack] = {}
    plugins: dict[str, str] = {}
    for pack_id, table in packs_table.items():
        pl = f"{ml} [packs.{pack_id}]"
        _kebab(pack_id, pl)
        _check_keys(table, pl, PACK_REQUIRED, PACK_OPTIONAL)
        platforms = _platforms(table["platforms"], f"{pl} platforms")
        plugin = table.get("plugin")
        if plugin is not None:
            _kebab(plugin, f"{pl} plugin")
            if plugin in plugins:
                raise BuildError(f"{pl}: plugin {plugin!r} is already used by pack {plugins[plugin]!r}")
            plugins[plugin] = pack_id
        if "claude" in platforms and plugin is None:
            raise BuildError(f"{pl}: a pack built for claude needs a plugin name")
        color = table.get("color")
        if color is not None and color not in CLAUDE_COLORS:
            raise BuildError(f"{pl}: color {color!r} is not one of {', '.join(sorted(CLAUDE_COLORS))}")
        keywords = _strings(table["keywords"], f"{pl} keywords") if "keywords" in table else (pack_id,)
        packs[pack_id] = Pack(pack_id, _line(table["description"], f"{pl} description"), plugin,
                              platforms, color, keywords)
    if "core" not in packs or packs["core"].platforms != PLATFORMS:
        raise BuildError(f"{ml}: [packs.core] is required and must be built for {' and '.join(PLATFORMS)}")

    roles_dir = src / "roles"
    common_path = roles_dir / "_common.md"
    if not common_path.is_file():
        raise BuildError(f"{tag}/roles/_common.md: missing")
    common = _read_text(common_path, f"{tag}/roles/_common.md")
    if "'''" in common:
        raise BuildError(f"{tag}/roles/_common.md: must not contain ''' (it is embedded in TOML literal strings)")

    found: dict[str, Role] = {}
    for path in sorted(roles_dir.glob("*.toml"), key=lambda item: item.name):
        if path.name.startswith("_"):
            continue
        rl = f"{tag}/roles/{path.name}"
        text = _read_text(path, rl)
        data = _parse_toml(text, rl)
        _check_keys(data, rl, ROLE_REQUIRED, ROLE_OPTIONAL)
        role_id = _kebab(data["id"], f"{rl}: id")
        if role_id != path.stem:
            raise BuildError(f"{rl}: id {role_id!r} must equal the file stem {path.stem!r}")
        if role_id in found:
            raise BuildError(f"{rl}: duplicate role id {role_id!r}")
        pack_id = data["pack"]
        if not isinstance(pack_id, str) or pack_id not in packs:
            raise BuildError(f"{rl}: unknown pack {pack_id!r} (packs: {', '.join(packs)})")
        pack = packs[pack_id]
        access = data.get("access", "write")
        if access not in ACCESS_KINDS:
            raise BuildError(f"{rl}: access {access!r} must be one of {', '.join(ACCESS_KINDS)}")
        platforms = pack.platforms
        if "platforms" in data:
            platforms = _platforms(data["platforms"], f"{rl}: platforms")
            outside = [item for item in platforms if item not in pack.platforms]
            if outside:
                raise BuildError(f"{rl}: platform(s) {', '.join(outside)} are not built for pack {pack_id!r} "
                                 f"({', '.join(pack.platforms)})")
        instructions = data["instructions"]
        if not isinstance(instructions, str) or not instructions.strip():
            raise BuildError(f"{rl}: instructions must be a non-empty string")
        if "'''" in instructions:
            raise BuildError(f"{rl}: instructions must not contain ''' (Codex agents embed them in a TOML literal string)")
        description = _line(data["description"], f"{rl}: description")
        if len(description) > MAX_DESCRIPTION:
            raise BuildError(f"{rl}: description has {len(description)} characters; keep it to {MAX_DESCRIPTION} "
                             "(every installed agent's description is loaded into each session)")
        found[role_id] = Role(role_id, pack_id, description, access, platforms,
                              instructions.replace("\r\n", "\n"), rl, _value_line(text, "instructions"))

    order = {pack_id: index for index, pack_id in enumerate(packs)}
    roles = dict(sorted(found.items(), key=lambda item: (order[item[1].pack], item[0])))
    return Source(src, version, repository, _line(manifest["license"], f"{ml}: license"),
                  _line(manifest["author"], f"{ml}: author"), _kebab(manifest["marketplace"], f"{ml}: marketplace"),
                  _line(manifest["description"], f"{ml}: description") if "description" in manifest
                  else skill["short_description"],
                  _strings(manifest["keywords"], f"{ml}: keywords") if "keywords" in manifest else DEFAULT_KEYWORDS,
                  skill, packs, roles, common)


# --------------------------------------------------------------------------- template engine

def runtime_name(role: Role, platform: str) -> str:
    """Codex agent_type is snake_case; Claude Code uses the bare kebab-case id."""
    return role.id.replace("-", "_") if platform == "codex" else role.id


def plugin_agent(source: Source, role: Role) -> str:
    return f"{source.packs[role.pack].plugin}:{role.id}"


def render_text(text: str, platform: str, source: Source, label: str, *, catalog: bool = False,
                first_line: int = 1) -> str:
    """Apply platform blocks and {{...}} tokens to one Markdown/instructions text for `platform`.
    `first_line` is the file line of the text's first line, so errors point at the source file."""
    items: list = []
    block: tuple[str, int] | None = None  # (platform, line number) of the open block
    for number, line in enumerate(text.split("\n"), first_line):
        marker = MARKER.fullmatch(line)
        if marker:
            name = marker.group(1)
            if name == "end":
                if block is None:
                    raise BuildError(f"{label}:{number}: <!-- @end --> without an open platform block")
                block = None
            elif name in PLATFORMS:
                if block is not None:
                    raise BuildError(f"{label}:{number}: platform blocks cannot nest "
                                     f"(<!-- @{block[0]} --> opened on line {block[1]})")
                block = (name, number)
            else:
                raise BuildError(f"{label}:{number}: unknown platform block @{name} "
                                 f"(expected {', '.join('@' + item for item in PLATFORMS)} or @end)")
            items.append(_REMOVED)
        elif MARKER_ANYWHERE.search(line):
            raise BuildError(f"{label}:{number}: a platform block marker must be alone on its line")
        elif block is not None and block[0] != platform:
            items.append(_REMOVED)
        else:
            items.append(_render_tokens(line, number, platform, source, label, catalog))
    if block is not None:
        raise BuildError(f"{label}:{block[1]}: <!-- @{block[0]} --> block is never closed with <!-- @end -->")
    return "\n".join(_collapse(items))


def _render_tokens(line: str, number: int, platform: str, source: Source, label: str, catalog: bool) -> str:
    def replace(match: re.Match) -> str:
        token = match.group(1)
        if token in SCALAR_TOKENS:
            return getattr(source, token)
        if token == "role-catalog":
            if not catalog:
                raise BuildError(f"{label}:{number}: {{{{role-catalog}}}} is only allowed in skill/{CATALOG_SOURCE}")
            if line.rstrip() != match.group(0):
                raise BuildError(f"{label}:{number}: {{{{role-catalog}}}} must be alone on its line")
            return role_catalog(source, platform)
        if token.startswith("role:"):
            role = source.roles.get(token[5:])
            if role is None:
                raise BuildError(f"{label}:{number}: unknown role in {match.group(0)}")
            if platform not in role.platforms:
                raise BuildError(f"{label}:{number}: role {role.id!r} is not built for {platform}; put "
                                 f"{match.group(0)} inside a <!-- @{role.platforms[0]} --> block")
            return runtime_name(role, platform)
        raise BuildError(f"{label}:{number}: unknown template token {match.group(0)} (expected {{{{role:<id>}}}}, "
                         + ", ".join("{{" + name + "}}" for name in SCALAR_TOKENS) + " or {{role-catalog}})")

    return TOKEN.sub(replace, line)


def _collapse(items: list) -> list[str]:
    """Drop removed lines; a run of blank lines touching a removed block becomes one blank line
    (none at the start or end of the text). Blank lines elsewhere are kept as written."""
    out: list[str] = []
    index = 0
    while index < len(items):
        item = items[index]
        if item is not _REMOVED and item.strip():
            out.append(item)
            index += 1
            continue
        end, removed, blanks = index, False, []
        while end < len(items) and (items[end] is _REMOVED or not items[end].strip()):
            if items[end] is _REMOVED:
                removed = True
            else:
                blanks.append(items[end])
            end += 1
        if not removed:
            out.extend(blanks)
        elif blanks and out and end < len(items):
            out.append("")
        index = end
    return out


def _trim(text: str) -> str:
    """Strip leading blank lines and trailing whitespace."""
    return re.sub(r"\A(?:[ \t]*\n)+", "", text).rstrip()


def role_catalog(source: Source, platform: str) -> str:
    if platform == "codex":
        rows = ["| Role | agent_type | Pack | Access | Description |"]
    else:
        rows = ["| Role | Plugin agent | Pack | Access | Description |"]
    rows.append("| --- | --- | --- | --- | --- |")
    for role in source.roles_for(platform):
        name = runtime_name(role, "codex") if platform == "codex" else plugin_agent(source, role)
        description = role.description.replace("|", "\\|")
        rows.append(f"| [{role.id}](roles/{role.id}.md) | `{name}` | {role.pack} | {role.access} | {description} |")
    return "\n".join(rows)


# --------------------------------------------------------------------------- output formats

def _quote(value: str) -> str:
    """A double-quoted string valid as JSON, as a TOML basic string and as a YAML double-quoted
    scalar. Callers only pass values validated by _line (no control or line-separator characters)."""
    return json.dumps(value, ensure_ascii=False)


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def role_brief(source: Source, role: Role, platform: str, body: str) -> str:
    if platform == "codex":
        runtime = f"Runtime name: `{runtime_name(role, platform)}` (Codex `agent_type`)"
    else:
        runtime = (f"Runtime name: `{plugin_agent(source, role)}` with the plugin install, "
                   f"`{role.id}` when installed by install.py")
    access = f"Access: `{role.access}` - {ACCESS_NOTES[platform][role.access]}"
    return f"# {role.id}\n\n{role.description}\n\n{runtime}\n{access}\n\n{body}\n"


def codex_agent(role: Role, body: str) -> str:
    if "'''" in body or LITERAL_UNSAFE.search(body):
        raise BuildError(f"{role.label}: rendered instructions cannot be stored in a TOML literal string "
                         "(they contain ''' or a control character)")
    lines = [f"name = {_quote(runtime_name(role, 'codex'))}", f"description = {_quote(role.description)}"]
    sandbox = CODEX_SANDBOX[role.access]
    if sandbox:
        lines.append(f"sandbox_mode = {_quote(sandbox)}")
    lines.append(f"developer_instructions = '''\n{body}\n'''")
    return "\n".join(lines) + "\n"


def claude_agent(source: Source, role: Role, body: str) -> str:
    key, value = CLAUDE_ACCESS[role.access]
    lines = ["---", f"name: {role.id}", f"description: {_quote(role.description)}", f"{key}: {value}"]
    color = source.packs[role.pack].color
    if color:
        lines.append(f"color: {color}")
    lines += ["---", "", body]
    return "\n".join(lines) + "\n"


def openai_yaml(source: Source) -> str:
    skill = source.skill
    prompt = (f"Use ${skill['name']} to choose specialists and skills, adapt models to the work as it "
              "develops, coordinate peer review, and deliver a verified result.")
    return ("interface:\n"
            f"  display_name: {_quote(skill['display_name'])}\n"
            f"  short_description: {_quote(skill['short_description'])}\n"
            f"  default_prompt: {_quote(prompt)}\n")


def plugin_json(source: Source, pack: Pack) -> str:
    url = f"https://github.com/{source.repository}"
    return _json({
        "name": pack.plugin,
        "version": source.version,
        "description": pack.description,
        "author": {"name": source.author},
        "license": source.license,
        "homepage": url,
        "repository": url,
        "keywords": list(dict.fromkeys(source.keywords + pack.keywords)),
    })


def marketplace_json(source: Source) -> str:
    return _json({
        "name": source.marketplace,
        "owner": {"name": source.author},
        "metadata": {"description": source.description, "version": source.version},
        "plugins": [
            {"name": pack.plugin, "source": f"./plugins/{pack.plugin}",
             "description": pack.description, "version": source.version}
            for pack in source.plugin_packs()
        ],
    })


# --------------------------------------------------------------------------- render

def _skill_sources(source: Source) -> list[tuple[str, str]]:
    skill_dir = source.root / "skill"
    if not (skill_dir / "SKILL.md").is_file():
        raise BuildError(f"{source.root.name}/skill/SKILL.md: missing")
    files = []
    for path in skill_dir.rglob("*"):
        rel = path.relative_to(skill_dir).as_posix()
        if not path.is_file() or any(part.startswith(".") for part in rel.split("/")):
            continue
        label = source.label(path)
        if path.suffix != ".md":
            raise BuildError(f"{label}: only Markdown files belong in skill/ "
                             "(agents/openai.yaml is generated from the manifest)")
        if rel.startswith("references/roles/"):
            raise BuildError(f"{label}: references/roles/ is generated from src/roles")
        files.append((rel, _read_text(path, label)))
    return sorted(files)


def _workflow_sources(source: Source) -> list[tuple[str, str]]:
    workflows = source.root / "workflows"
    if not workflows.is_dir():
        return []
    files = []
    for path in sorted(workflows.iterdir(), key=lambda item: item.name):
        label = source.label(path)
        if path.name.startswith("."):
            continue
        if not path.is_file() or path.suffix != ".js":
            raise BuildError(f"{label}: only Workflow scripts (*.js files, no subdirectories) belong in workflows/")
        text = _read_text(path, label).rstrip("\n") + "\n"
        meta = WORKFLOW_META.match(text)
        if not meta or meta.group(2) != path.stem or not KEBAB.fullmatch(path.stem):
            raise BuildError(f"{label}: must start with `export const meta = {{ name: '{path.stem}'` "
                             "(meta.name first, equal to the kebab-case file stem)")
        files.append((path.name, text))
    return files


def render(src: Path) -> dict[str, bytes]:
    """Return every generated file as {repo-relative POSIX path: bytes}. Reads `src` only."""
    source = load_source(Path(src))
    outputs: dict[str, str] = {}

    def emit(path: str, text: str) -> None:
        if path in outputs:
            raise BuildError(f"two sources generate {path}")
        outputs[path] = text

    common_label = f"{source.root.name}/roles/_common.md"
    common = {platform: _trim(render_text(source.common, platform, source, common_label)) for platform in PLATFORMS}
    bodies: dict[tuple[str, str], str] = {}
    for role in source.roles.values():
        for platform in role.platforms:
            instructions = _trim(render_text(role.instructions, platform, source, role.label,
                                             first_line=role.instructions_line))
            if not instructions:
                raise BuildError(f"{role.label}: instructions render empty for {platform}")
            bodies[role.id, platform] = f"{instructions}\n\n{common[platform]}" if common[platform] else instructions

    core = source.packs["core"]
    skill_name = source.skill["name"]
    bases = {"codex": f"skills/{skill_name}", "claude": f"plugins/{core.plugin}/skills/{skill_name}"}
    skill_files = _skill_sources(source)
    for platform in PLATFORMS:
        for rel, text in skill_files:
            label = f"{source.root.name}/skill/{rel}"
            rendered = _trim(render_text(text, platform, source, label, catalog=rel == CATALOG_SOURCE))
            if rendered:  # a file wholly inside the other platform's block is not generated
                emit(f"{bases[platform]}/{rel}", rendered + "\n")
        for role in source.roles_for(platform):
            emit(f"{bases[platform]}/references/roles/{role.id}.md",
                 role_brief(source, role, platform, bodies[role.id, platform]))
    emit(f"{bases['codex']}/agents/openai.yaml", openai_yaml(source))

    for role in source.roles_for("codex"):
        emit(f"codex/agents/{role.id}.toml", codex_agent(role, bodies[role.id, "codex"]))
    for pack in source.plugin_packs():
        emit(f"plugins/{pack.plugin}/.claude-plugin/plugin.json", plugin_json(source, pack))
    for role in source.roles_for("claude"):
        emit(f"plugins/{source.packs[role.pack].plugin}/agents/{role.id}.md",
             claude_agent(source, role, bodies[role.id, "claude"]))
    for name, text in _workflow_sources(source):
        emit(f"plugins/{core.plugin}/workflows/{name}", text)
    emit(".claude-plugin/marketplace.json", marketplace_json(source))

    _check_paths(outputs)
    result = {}
    for path in sorted(outputs):
        text = outputs[path]
        if "\r" in text or text.startswith("\ufeff") or not text.endswith("\n") or text.endswith("\n\n"):
            raise BuildError(f"internal error: {path} is not LF text with one trailing newline")
        result[path] = text.encode("utf-8")
    return result


# --------------------------------------------------------------------------- write / check

def _check_paths(paths) -> None:
    for path in paths:
        if (not isinstance(path, str) or "\\" in path or ":" in path or path.startswith("/")
                or any(part in ("", ".", "..") for part in path.split("/"))
                or not any(path.startswith(root + "/") for root in GENERATED_ROOTS)):
            raise BuildError(f"refusing to manage {path!r}: outside the generated roots ({', '.join(GENERATED_ROOTS)})")


def _is_link(path: Path) -> bool:
    """A symlink or a Windows junction. os.path.isjunction exists only from Python 3.12, so read the
    reparse tag directly (the same test isjunction uses) to stay safe on 3.11."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    junction = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", None)
    return stat.S_ISLNK(info.st_mode) or (junction is not None
                                          and getattr(info, "st_reparse_tag", 0) == junction)


def _generated_files(root: Path) -> set[str]:
    """Every file (or link) currently inside the generated roots, as repo-relative POSIX paths."""
    found = set()
    for generated in GENERATED_ROOTS:
        base = root / generated
        if not base.is_dir() or _is_link(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            current = Path(dirpath)
            for name in list(dirnames):
                if _is_link(current / name):  # never descend into links; treat them as entries
                    dirnames.remove(name)
                    filenames.append(name)
            found.update((current / name).relative_to(root).as_posix() for name in filenames)
    return found


def _prune_empty_dirs(root: Path) -> None:
    for generated in GENERATED_ROOTS:
        base = root / generated
        if not base.is_dir() or _is_link(base):
            continue
        for dirpath, _dirnames, _filenames in os.walk(base, topdown=False):
            current = Path(dirpath)
            if current != base and not _is_link(current) and not any(current.iterdir()):
                current.rmdir()


def check(outputs: dict[str, bytes], root: Path) -> list[str]:
    """Paths that are missing, differ from `outputs`, or are stale inside the generated roots."""
    root = Path(root)
    _check_paths(outputs)
    drift = {path for path, data in outputs.items()
             if _is_link(root / path) or not (root / path).is_file() or (root / path).read_bytes() != data}
    drift |= _generated_files(root) - outputs.keys()
    return sorted(drift)


def write(outputs: dict[str, bytes], root: Path) -> list[str]:
    """Write changed outputs, delete stale files inside the generated roots only; return touched paths."""
    root = Path(root)
    _check_paths(outputs)
    changed = []
    for path in sorted(_generated_files(root) - outputs.keys()):
        (root / path).unlink()  # also removes a directory link itself, never its target
        changed.append(path)
    _prune_empty_dirs(root)
    for path, data in outputs.items():
        target = root / path
        if _is_link(target):
            target.unlink()
        elif target.is_file() and target.read_bytes() == data:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        changed.append(path)
    return sorted(changed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build.py", description="Generate platform files from src/ "
                                     "(see docs/architecture.md).")
    parser.add_argument("--check", action="store_true",
                        help="list generated files that differ from src/ and exit 1 if any do")
    parser.add_argument("--root", type=Path, default=REPO,
                        help="repository root containing src/ (default: this checkout)")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    root = args.root.resolve()
    try:
        outputs = render(root / "src")
        stale = _generated_files(root) - outputs.keys()  # files the build does not produce: it deletes them
        if args.check:
            drift = check(outputs, root)
            for path in drift:
                print(f"{path} (not generated from src/; build.py deletes it)" if path in stale else path)
            if drift:
                print(f"{len(drift)} generated file(s) differ from src/. Run: python scripts/build.py "
                      "(it deletes files marked as not generated; move any you need out of the generated "
                      "directories first)", file=sys.stderr)
                return 1
            print(f"Generated files are up to date ({len(outputs)} files).")
            return 0
        changed = write(outputs, root)
    except BuildError as exc:
        print(f"build.py: error: {exc}", file=sys.stderr)
        return 2
    for path in changed:
        print(f"{'deleted' if path in stale else 'updated'} {path}")
    print(f"{len(changed)} file(s) changed, {len(outputs)} generated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
