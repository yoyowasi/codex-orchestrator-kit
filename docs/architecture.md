# Architecture and contributor contract

This repository keeps **one source** (`src/`) and generates every platform-specific file from it with `scripts/build.py`. Generated files are committed because Claude Code plugin marketplaces and Codex `$skill-installer` install straight from the repository without a build step. CI runs `python scripts/build.py --check` and fails when generated files drift from the source.

**Never edit generated files by hand.** Edit `src/`, run `python scripts/build.py`, commit both.

## Layout

```text
src/                          SOURCE (edit here)
  manifest.toml               version, repository, packs, legacy file names ([skill] name is fixed: orchestrate)
  skill/
    SKILL.md                  skill entry point (platform blocks allowed)
    references/*.md           models, collaboration, skill routing, examples
  roles/
    _common.md                rules appended to every role (platform blocks allowed)
    <id>.toml                 one file per role (files starting with _ are not roles)
  workflows/
    <name>.js                 Claude Code Workflow scripts (core plugin only)

skills/orchestrate/           GENERATED  Codex skill ($skill-installer path, ~/.agents/skills)
codex/agents/<id>.toml        GENERATED  Codex custom agents (~/.codex/agents)
plugins/<plugin>/             GENERATED  Claude Code plugins (one per pack)
.claude-plugin/marketplace.json  GENERATED  Claude Code marketplace

scripts/build.py              generator (Python 3.11+, standard library only)
scripts/install.py            installer for Codex and for Claude Code without plugins
extras/codex-team/            optional Windows multi-window launcher (Codex only)
tests/                        unit tests (build, install, workflow scripts); launcher tests live in extras/codex-team
```

## Role source schema (`src/roles/<id>.toml`)

```toml
id = "evidence-reviewer"        # required. kebab-case, equals the file stem, unique
pack = "core"                   # required. a key of [packs] in src/manifest.toml
description = "..."             # required. one English sentence, at most 200 characters: what it does + "pick it ..."
access = "read-only"            # optional. "write" (default) | "read-shell" | "read-only"
platforms = ["claude", "codex"] # optional. defaults to the pack's platforms
instructions = '''
Role-specific instructions in English, one rule per line or short bullet list.
Do not repeat anything that _common.md already says.
'''
```

`access` is the only permission knob. Generators map it as follows.

| access | Claude Code agent frontmatter | Codex agent TOML |
|---|---|---|
| `write` | `disallowedTools: Agent` | (nothing) |
| `read-shell` | `disallowedTools: Write, Edit, NotebookEdit, Agent` | `sandbox_mode = "read-only"` |
| `read-only` | `tools: Read, Grep, Glob, WebFetch, WebSearch, SendMessage` | `sandbox_mode = "read-only"` |

`SendMessage` must be listed explicitly in a `tools` allowlist, otherwise the subagent cannot message peers. A `tools` allowlist also drops MCP tools.

Limits that the docs must state honestly:

- Claude Code `read-shell` roles still have Bash/PowerShell, so "do not modify files" is an instruction, not enforcement.
- Codex documents `sandbox_mode` for custom agents, but current Codex source lets spawned agents inherit the parent session's permissions. Treat it as advisory until verified on your Codex version.
- `Agent` is removed from every Claude role so subagents cannot build nested teams.

## Template syntax (Markdown sources and `instructions`)

- Platform blocks keep their lines only for one platform. Marker lines are removed.

  ```text
  <!-- @claude -->
  Claude-only text
  <!-- @end -->
  <!-- @codex -->
  Codex-only text
  <!-- @end -->
  ```

  Blocks cannot nest. An unknown platform name or an unclosed block is a build error.
- `{{role:<id>}}` renders a role's runtime name: Codex uses snake_case (`evidence_reviewer`); Claude Code uses the bare kebab-case id (`evidence-reviewer`). An unknown id is a build error.
- `{{version}}`, `{{repository}}` and `{{marketplace}}` render the manifest values of the same name (for example `/plugin install orchestra@{{marketplace}}`).
- `{{role-catalog}}` (only in `src/skill/references/roles.md`) renders the generated role table for that platform.
- Only Markdown sources and role `instructions` are rendered. One-line values (descriptions, manifest strings) must not contain `{{` or `<!--`; the build rejects them.
- There is no escape for a literal `{{...}}` or a literal `<!-- @name -->` marker in rendered text: every `{{...}}` must be a known token. Rephrase such examples, or describe them in prose.
- Role-instruction errors report the line in the role file (`src/roles/<id>.toml:<line>`).
- In role instructions, refer to a skill as "the installed <capability> skill (see skill routing)"; the common working rules define what "see skill routing" means for an agent, and Codex-only or Claude-only skills go in platform blocks.

## Workflow scripts (`src/workflows/<name>.js`)

- Only `*.js` files, no subdirectories (dotfiles are ignored).
- Each file starts with `export const meta = { name: '<name>'`: `meta.name` comes first and equals the kebab-case file stem, because the script install copies the file by name and Claude Code runs a personal workflow as `/<meta.name>`. Names start with `team-` so they never become generic commands like `/review`.
- Copied verbatim (no template rendering) to `plugins/orchestra/workflows/`. `tests/workflows.test.mjs` compiles them and checks that every `/orchestra:<name>` in the docs exists.

### Claude Code runtime names

Plugin components are namespaced by plugin name. With the plugin install the skill is `/orchestra:orchestrate` and agents are `orchestra:reviewer`, `orchestra-dev:database-engineer`, and so on. With `install.py --target claude` (no plugin) they are `/orchestrate` and `reviewer`. Skill text therefore uses the bare id and tells the orchestrator to pass `subagent_type` exactly as the Agent tool lists it (`<plugin>:<id>` or `<id>`).

## Generated outputs

### Codex

- `skills/orchestrate/SKILL.md`, `agents/openai.yaml`, `references/*.md` rendered for `codex`.
- `skills/orchestrate/references/roles/<id>.md`: every Codex role's brief (description + instructions + common rules) so the orchestrator can inject a role into a generic agent when that role is not registered.
- `codex/agents/<id>.toml`: `name` (snake_case), `description`, optional `sandbox_mode`, `developer_instructions` (instructions + common rules). No `model` keys: the orchestrator chooses models per task.

### Claude Code

- `plugins/<packs.X.plugin>/.claude-plugin/plugin.json` for every pack built for `claude`.
- The core plugin also carries `skills/orchestrate/` (rendered for `claude`), including `references/roles/<id>.md` briefs for every Claude role, so roles from packs that are not installed can still be injected into a general-purpose agent.
- `plugins/<plugin>/agents/<id>.md`: frontmatter (`name`, `description`, access mapping, `color` from the pack) + instructions + common rules.
- `plugins/orchestra/workflows/*.js`: Claude Code Workflow scripts copied from `src/workflows/` (run as `/orchestra:<meta.name>`).
- `.claude-plugin/marketplace.json` lists every Claude plugin with a relative `./plugins/<plugin>` `source`; `plugin.json` and marketplace entries carry `manifest.version`.
- The Claude `SKILL.md` refers to bundled files as `${CLAUDE_SKILL_DIR}/references/...` (Claude Code substitutes it in the SKILL.md body only). Reference files and all Codex text use relative links, which the orchestrator resolves from the file it read.

### Generated `references/roles.md`

The role catalog table (id, runtime name, pack, access, description) is generated from role sources, so descriptions exist in exactly one place.

## Build and check

```sh
python scripts/build.py           # regenerate everything
python scripts/build.py --check   # exit 1 and list files that differ (CI)
```

Python API used by tests: `build.render(src: Path) -> dict[str, bytes]` (repo-relative POSIX path → file bytes, no I/O besides reading `src`), `build.write(outputs, root: Path)`, `build.check(outputs, root: Path) -> list[str]` (differing or stale paths).

Outputs are UTF-8 without BOM, LF line endings, one trailing newline. The build removes stale generated files it no longer produces, and only inside generated directories: `--check` marks them "not generated from src/; build.py deletes it", and a build prints `deleted <path>`. Never keep hand-made files inside the generated directories. Directory symlinks and Windows junctions at generated roots or along output paths are rejected before any writes or cleanup. Stale links inside generated directories are removed as entries without following their targets.
