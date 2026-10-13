"""Tests for scripts/build.py, the generator specified in docs/architecture.md."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("orchestrator_kit_build", REPO / "scripts/build.py")
build = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = build  # dataclasses resolve annotations through sys.modules
spec.loader.exec_module(build)

MANIFEST = """\
version = "9.8.7"
repository = "example/kit"
license = "MIT"
author = "tester"
marketplace = "kit-market"

[skill]
name = "orchestrate"
display_name = "Test Orchestrator"
short_description = "Coordinates test specialists."

[packs.core]
description = "Core pack."
plugin = "orchestra"
platforms = ["claude", "codex"]
color = "blue"

[packs.extra]
description = "Extra pack."
plugin = "orchestra-extra"
platforms = ["claude", "codex"]
color = "green"

[packs.codex-only]
description = "Codex only pack."
platforms = ["codex"]

[legacy]
codex_agents = ["old.toml"]
"""

COMMON = """\
## Working rules

- Shared rule.
<!-- @claude -->
- Message peers with SendMessage.
<!-- @end -->
<!-- @codex -->
- Message peers with send_message.
<!-- @end -->
- Report what you verified.
"""

SKILL = """\
---
name: orchestrate
description: Test skill version {{version}}.
---

# Orchestrate

Intro paragraph.

<!-- @claude -->
Claude paragraph: ask {{role:code-checker}} through the Agent tool.
<!-- @end -->
<!-- @codex -->
Codex paragraph: spawn {{role:code-checker}} or {{role:codex-helper}}.
<!-- @end -->

Closing paragraph.
"""

ROLES_MD = """\
# Roles

{{role-catalog}}

Pick the smallest team.
"""

CLAUDE_NOTES = """\
<!-- @claude -->
# Claude notes

Only for Claude Code.
<!-- @end -->
"""

WORKFLOW = "export const meta = { name: 'review' };\nconsole.log('{{not a token}}');\n"


def role_toml(role_id, pack, description, instructions, access=None, platforms=None):
    lines = [f'id = "{role_id}"', f'pack = "{pack}"', f"description = '{description}'"]
    if access:
        lines.append(f'access = "{access}"')
    if platforms:
        lines.append("platforms = [" + ", ".join(f'"{item}"' for item in platforms) + "]")
    lines.append(f"instructions = '''\n{instructions}'''")
    return "\n".join(lines) + "\n"


BASE_FILES = {
    "manifest.toml": MANIFEST,
    "roles/_common.md": COMMON,
    "roles/code-builder.toml": role_toml(
        "code-builder", "core", "Builds code; pick it for implementation.",
        "- Hand the result to {{role:code-checker}}.\n"
        "<!-- @codex -->\n- Ask {{role:codex-helper}} about OpenAI products.\n<!-- @end -->\n"
        "- Version {{version}}.\n"),
    "roles/code-checker.toml": role_toml(
        "code-checker", "core", 'Checks "quoted" paths like C:\\temp | naive text.',
        "- Run checks; never edit files.\n", access="read-shell"),
    "roles/doc-looker.toml": role_toml(
        "doc-looker", "extra", "Reads documents only.", "- Read and report.\n", access="read-only"),
    "roles/codex-helper.toml": role_toml(
        "codex-helper", "codex-only", "Knows Codex products.", "- Use Codex tools.\n"),
    "skill/SKILL.md": SKILL,
    "skill/references/roles.md": ROLES_MD,
    "skill/references/claude-notes.md": CLAUDE_NOTES,
}

ROLE_IDS = ("code-builder", "code-checker", "doc-looker", "codex-helper")
CLAUDE_ROLES = {"code-builder": "orchestra", "code-checker": "orchestra", "doc-looker": "orchestra-extra"}


def make_src(root, overrides=None):
    """Write the synthetic source tree to root/src; an override value of None removes a file."""
    files = dict(BASE_FILES)
    files.update(overrides or {})
    src = Path(root) / "src"
    for rel, text in files.items():
        if text is None:
            continue
        path = src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return src


def frontmatter(text):
    """Return (keys in order, {key: raw value}, body) of a Claude agent file."""
    if not text.startswith("---\n"):
        raise AssertionError("frontmatter must start on line 1")
    head, body = text[4:].split("\n---\n", 1)
    pairs = [line.split(": ", 1) for line in head.split("\n")]
    return [key for key, _ in pairs], dict(pairs), body


class BuildTestCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.counter = 0

    def render(self, overrides=None):
        self.counter += 1
        return build.render(make_src(self.root / f"case{self.counter}", overrides))

    def text(self, outputs, path):
        return outputs[path].decode("utf-8")


class TemplateTests(BuildTestCase):
    def test_platform_blocks_render_per_platform(self):
        outputs = self.render()
        codex = self.text(outputs, "skills/orchestrate/SKILL.md")
        claude = self.text(outputs, "plugins/orchestra/skills/orchestrate/SKILL.md")
        self.assertIn("Codex paragraph: spawn code_checker or codex_helper.", codex)
        self.assertNotIn("Claude paragraph", codex)
        self.assertIn("Claude paragraph: ask code-checker through the Agent tool.", claude)
        self.assertNotIn("Codex paragraph", claude)
        for text in (codex, claude):
            self.assertTrue(text.startswith("---\nname: orchestrate\ndescription: Test skill version 9.8.7.\n---\n"))
            self.assertNotIn("<!--", text)
            self.assertNotIn("\n\n\n", text)
            self.assertIn("Intro paragraph.\n\n", text)
            self.assertTrue(text.endswith("\n\nClosing paragraph.\n"))
        common_codex = self.text(outputs, "codex/agents/code-builder.toml")
        self.assertIn("- Shared rule.\n- Message peers with send_message.\n- Report what you verified.\n", common_codex)
        common_claude = self.text(outputs, "plugins/orchestra/agents/code-builder.md")
        self.assertIn("- Shared rule.\n- Message peers with SendMessage.\n- Report what you verified.\n", common_claude)

    def test_blank_lines_collapse_only_around_removed_blocks(self):
        outputs = self.render({"skill/references/extra.md": (
            "A\n\n\n\nB\n\n<!-- @claude -->\nC\n<!-- @end -->\n\n\nD\n")})
        self.assertEqual(self.text(outputs, "skills/orchestrate/references/extra.md"), "A\n\n\n\nB\n\nD\n")
        self.assertEqual(self.text(outputs, "plugins/orchestra/skills/orchestrate/references/extra.md"),
                         "A\n\n\n\nB\n\nC\n\nD\n")

    def test_file_wholly_inside_one_platform_block_is_generated_only_there(self):
        outputs = self.render()
        self.assertEqual(self.text(outputs, "plugins/orchestra/skills/orchestrate/references/claude-notes.md"),
                         "# Claude notes\n\nOnly for Claude Code.\n")
        self.assertNotIn("skills/orchestrate/references/claude-notes.md", outputs)

    def test_block_errors(self):
        cases = {
            "unclosed": "a\n<!-- @claude -->\nb\n",
            "nested": "<!-- @claude -->\n<!-- @codex -->\nx\n<!-- @end -->\n<!-- @end -->\n",
            "unknown platform": "<!-- @gemini -->\nx\n<!-- @end -->\n",
            "stray end": "x\n<!-- @end -->\n",
            "inline marker": "text <!-- @claude --> more\n",
        }
        for name, text in cases.items():
            with self.subTest(name), self.assertRaises(build.BuildError):
                self.render({"skill/references/bad.md": text})
        with self.subTest("role instructions"), self.assertRaises(build.BuildError):
            self.render({"roles/doc-looker.toml": role_toml(
                "doc-looker", "extra", "Reads.", "<!-- @codex -->\n- x\n", access="read-only")})

    def test_role_tokens_render_per_platform(self):
        outputs = self.render()
        codex = self.text(outputs, "codex/agents/code-builder.toml")
        claude = self.text(outputs, "plugins/orchestra/agents/code-builder.md")
        self.assertIn("- Hand the result to code_checker.\n- Ask codex_helper about OpenAI products.\n- Version 9.8.7.", codex)
        self.assertIn("- Hand the result to code-checker.\n- Version 9.8.7.", claude)
        self.assertNotIn("codex", claude.split("---", 2)[2].lower())

    def test_manifest_tokens_render_on_both_platforms(self):
        outputs = self.render({"skill/references/extra.md": (
            "Install `orchestra@{{marketplace}}` from {{repository}} at {{version}}.\n")})
        expected = "Install `orchestra@kit-market` from example/kit at 9.8.7.\n"
        self.assertEqual(self.text(outputs, "skills/orchestrate/references/extra.md"), expected)
        self.assertEqual(self.text(outputs, "plugins/orchestra/skills/orchestrate/references/extra.md"), expected)

    def test_token_errors(self):
        cases = {
            "unknown token": {"skill/SKILL.md": "x {{nope}}\n"},
            "spaced token": {"skill/SKILL.md": "x {{ role:code-checker }}\n"},
            "unknown role": {"skill/SKILL.md": "x {{role:ghost}}\n"},
            "role not built for the platform": {"skill/SKILL.md": "x {{role:codex-helper}}\n"},
            "catalog outside roles.md": {"skill/SKILL.md": "{{role-catalog}}\n"},
            "catalog not alone on its line": {"skill/references/roles.md": "see {{role-catalog}}\n"},
            "catalog in role instructions": {"roles/doc-looker.toml": role_toml(
                "doc-looker", "extra", "Reads.", "{{role-catalog}}\n", access="read-only")},
            "unknown role in common": {"roles/_common.md": "- ask {{role:ghost}}\n"},
        }
        for name, overrides in cases.items():
            with self.subTest(name), self.assertRaises(build.BuildError):
                self.render(overrides)

    def test_role_catalog_per_platform(self):
        outputs = self.render()
        codex = self.text(outputs, "skills/orchestrate/references/roles.md")
        claude = self.text(outputs, "plugins/orchestra/skills/orchestrate/references/roles.md")
        self.assertIn("| Role | agent_type | Pack | Access | Description |\n| --- | --- | --- | --- | --- |\n", codex)
        self.assertIn("| [code-checker](roles/code-checker.md) | `code_checker` | core | read-shell | "
                      "Checks \"quoted\" paths like C:\\temp \\| naive text. |", codex)
        self.assertIn("| [codex-helper](roles/codex-helper.md) | `codex_helper` | codex-only | write |", codex)
        self.assertIn("| Role | Plugin agent | Pack | Access | Description |", claude)
        self.assertIn("| [doc-looker](roles/doc-looker.md) | `orchestra-extra:doc-looker` | extra | read-only |", claude)
        self.assertNotIn("codex-helper", claude)
        rows = [line for line in codex.splitlines() if line.startswith("| [")]
        self.assertEqual([row.split("]")[0][3:] for row in rows],
                         ["code-builder", "code-checker", "doc-looker", "codex-helper"])  # pack order, then id
        self.assertTrue(codex.endswith("|\n\nPick the smallest team.\n"))


class OutputTests(BuildTestCase):
    def test_access_mapping_on_both_platforms(self):
        outputs = self.render()
        claude = {
            "code-builder": ("disallowedTools", "Agent"),
            "code-checker": ("disallowedTools", "Write, Edit, NotebookEdit, Agent"),
            "doc-looker": ("tools", "Read, Grep, Glob, WebFetch, WebSearch, SendMessage"),
        }
        for role_id, (key, value) in claude.items():
            keys, fields, _ = frontmatter(self.text(outputs, f"plugins/{CLAUDE_ROLES[role_id]}/agents/{role_id}.md"))
            self.assertEqual(fields[key], value)
            self.assertNotIn({"tools": "disallowedTools", "disallowedTools": "tools"}[key], keys)
        codex = {"code-builder": None, "code-checker": "read-only", "doc-looker": "read-only", "codex-helper": None}
        for role_id, sandbox in codex.items():
            data = tomllib.loads(self.text(outputs, f"codex/agents/{role_id}.toml"))
            self.assertEqual(data.get("sandbox_mode"), sandbox)

    def test_codex_only_role_is_absent_from_claude_outputs(self):
        outputs = self.render()
        self.assertIn("codex/agents/codex-helper.toml", outputs)
        self.assertIn("skills/orchestrate/references/roles/codex-helper.md", outputs)
        claude_paths = [path for path in outputs if not path.startswith(("skills/", "codex/"))]
        self.assertTrue(claude_paths)
        for path in claude_paths:
            self.assertNotIn("codex-helper", path)
            self.assertNotIn("codex-helper", self.text(outputs, path))
            self.assertNotIn("codex_helper", self.text(outputs, path))

    def test_codex_agent_toml_round_trips(self):
        outputs = self.render()
        common = ("## Working rules\n\n- Shared rule.\n- Message peers with send_message.\n"
                  "- Report what you verified.\n")
        for role_id in ROLE_IDS:
            text = self.text(outputs, f"codex/agents/{role_id}.toml")
            data = tomllib.loads(text)
            expected_keys = ["name", "description"] + (["sandbox_mode"] if "sandbox_mode" in data else [])
            self.assertEqual(list(data), expected_keys + ["developer_instructions"])
            self.assertEqual(data["name"], role_id.replace("-", "_"))
            self.assertTrue(data["developer_instructions"].endswith("\n\n" + common))
            self.assertNotIn("model", text)
        checker = tomllib.loads(self.text(outputs, "codex/agents/code-checker.toml"))
        self.assertEqual(checker["description"], 'Checks "quoted" paths like C:\\temp | naive text.')
        self.assertEqual(checker["developer_instructions"], "- Run checks; never edit files.\n\n" + common)

    def test_json_files(self):
        outputs = self.render()
        market = json.loads(self.text(outputs, ".claude-plugin/marketplace.json"))
        self.assertEqual(market, {
            "name": "kit-market",
            "owner": {"name": "tester"},
            "metadata": {"description": "Coordinates test specialists.", "version": "9.8.7"},
            "plugins": [
                {"name": "orchestra", "source": "./plugins/orchestra", "description": "Core pack.", "version": "9.8.7"},
                {"name": "orchestra-extra", "source": "./plugins/orchestra-extra", "description": "Extra pack.",
                 "version": "9.8.7"},
            ],
        })
        plugin_files = sorted(path for path in outputs if path.endswith("plugin.json"))
        self.assertEqual(plugin_files, ["plugins/orchestra-extra/.claude-plugin/plugin.json",
                                        "plugins/orchestra/.claude-plugin/plugin.json"])
        plugin = json.loads(self.text(outputs, "plugins/orchestra-extra/.claude-plugin/plugin.json"))
        self.assertEqual(list(plugin), ["name", "version", "description", "author", "license", "homepage",
                                        "repository", "keywords"])
        self.assertEqual(plugin["name"], "orchestra-extra")
        self.assertEqual(plugin["author"], {"name": "tester"})
        self.assertEqual(plugin["homepage"], "https://github.com/example/kit")
        self.assertEqual(plugin["repository"], "https://github.com/example/kit")
        self.assertIn("extra", plugin["keywords"])
        for path in plugin_files + [".claude-plugin/marketplace.json"]:
            text = self.text(outputs, path)
            self.assertEqual(text, json.dumps(json.loads(text), indent=2, ensure_ascii=False) + "\n")

    def test_claude_agent_frontmatter(self):
        outputs = self.render()
        for role_id, plugin in CLAUDE_ROLES.items():
            text = self.text(outputs, f"plugins/{plugin}/agents/{role_id}.md")
            keys, fields, body = frontmatter(text)
            self.assertEqual(keys[:2], ["name", "description"])
            self.assertEqual(keys[3:], ["color"])
            self.assertEqual(len(keys), 4)
            self.assertEqual(fields["name"], role_id)
            self.assertEqual(fields["color"], "blue" if plugin == "orchestra" else "green")
            self.assertIsInstance(json.loads(fields["description"]), str)
            self.assertTrue(body.startswith("\n- "))
            self.assertTrue(body.endswith("\n\n## Working rules\n\n- Shared rule.\n- Message peers with SendMessage.\n"
                                          "- Report what you verified.\n"))
        _, fields, _ = frontmatter(self.text(outputs, "plugins/orchestra/agents/code-checker.md"))
        self.assertEqual(json.loads(fields["description"]), 'Checks "quoted" paths like C:\\temp | naive text.')

    def test_role_briefs_and_codex_metadata(self):
        outputs = self.render()
        for role_id in ROLE_IDS:
            self.assertIn(f"skills/orchestrate/references/roles/{role_id}.md", outputs)
        claude_briefs = sorted(path for path in outputs if path.startswith("plugins/orchestra/skills/orchestrate/references/roles/"))
        self.assertEqual(claude_briefs, [f"plugins/orchestra/skills/orchestrate/references/roles/{role_id}.md"
                                         for role_id in sorted(CLAUDE_ROLES)])
        brief = self.text(outputs, "skills/orchestrate/references/roles/code-checker.md")
        self.assertTrue(brief.startswith("# code-checker\n\nChecks \"quoted\" paths like C:\\temp | naive text.\n\n"
                                         "Runtime name: `code_checker`"))
        self.assertIn("\nAccess: `read-shell` - ", brief)
        self.assertIn("- Run checks; never edit files.\n\n## Working rules\n", brief)
        claude_brief = self.text(outputs, "plugins/orchestra/skills/orchestrate/references/roles/doc-looker.md")
        self.assertIn("Runtime name: `orchestra-extra:doc-looker`", claude_brief)
        self.assertIn("SendMessage", claude_brief)
        self.assertNotIn("plugins/orchestra/skills/orchestrate/agents/openai.yaml", outputs)
        self.assertEqual(self.text(outputs, "skills/orchestrate/agents/openai.yaml"), (
            "interface:\n"
            '  display_name: "Test Orchestrator"\n'
            '  short_description: "Coordinates test specialists."\n'
            '  default_prompt: "Use $orchestrate to choose specialists and skills, adapt models to the work as it '
            'develops, coordinate peer review, and deliver a verified result."\n'))

    def test_workflows_are_copied_and_optional(self):
        outputs = self.render()
        self.assertFalse([path for path in outputs if "/workflows/" in path])
        outputs = self.render({"workflows/review.js": WORKFLOW, "workflows/.notes": "ignored\n"})
        self.assertEqual(outputs["plugins/orchestra/workflows/review.js"], WORKFLOW.encode("utf-8"))
        self.assertEqual([path for path in outputs if "/workflows/" in path], ["plugins/orchestra/workflows/review.js"])

    def test_invalid_workflows_are_rejected(self):
        cases = {
            "not a script": {"workflows/notes.txt": "notes\n"},
            "module script": {"workflows/review.mjs": WORKFLOW},
            "subdirectory": {"workflows/more/review.js": WORKFLOW},
            "name differs from the file stem": {"workflows/team-review.js": WORKFLOW},
            "meta not first": {"workflows/review.js": "// comment\n" + WORKFLOW},
        }
        for name, overrides in cases.items():
            with self.subTest(name), self.assertRaises(build.BuildError):
                self.render(overrides)

    def test_outputs_have_no_bom_or_crlf(self):
        lf = self.render({"workflows/review.js": WORKFLOW})
        windows = {rel: "\ufeff" + text.replace("\n", "\r\n") for rel, text in BASE_FILES.items()}
        windows["workflows/review.js"] = "\ufeff" + WORKFLOW.replace("\n", "\r\n")
        crlf = self.render(windows)
        self.assertEqual(crlf, lf)
        for path, data in crlf.items():
            with self.subTest(path):
                data.decode("utf-8")
                self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
                self.assertNotIn(b"\r", data)
                self.assertTrue(data.endswith(b"\n"))
                self.assertFalse(data.endswith(b"\n\n"))

    def test_render_is_deterministic(self):
        first = self.render()
        second = self.render()
        self.assertEqual(list(first), sorted(first))
        self.assertEqual(first, second)


class ValidationTests(BuildTestCase):
    def test_invalid_sources_are_rejected(self):
        cases = {
            "missing required key": {"roles/doc-looker.toml": 'id = "doc-looker"\npack = "extra"\ninstructions = "x"\n'},
            "unknown role key": {"roles/doc-looker.toml": role_toml("doc-looker", "extra", "Reads.", "- x\n")
                                 + 'model = "big"\n'},
            "id differs from file stem": {"roles/doc-looker.toml": role_toml("doc-reader", "extra", "Reads.", "- x\n")},
            "id not kebab-case": {"roles/Doc_Looker.toml": role_toml("Doc_Looker", "extra", "Reads.", "- x\n")},
            "unknown pack": {"roles/doc-looker.toml": role_toml("doc-looker", "nope", "Reads.", "- x\n")},
            "unknown access": {"roles/doc-looker.toml": role_toml("doc-looker", "extra", "Reads.", "- x\n",
                                                                  access="admin")},
            "platform outside the pack": {"roles/codex-helper.toml": role_toml(
                "codex-helper", "codex-only", "Knows.", "- x\n", platforms=["claude"])},
            "unknown platform": {"roles/doc-looker.toml": role_toml("doc-looker", "extra", "Reads.", "- x\n",
                                                                    platforms=["gemini"])},
            "triple quote in instructions": {"roles/doc-looker.toml": (
                'id = "doc-looker"\npack = "extra"\ndescription = "Reads."\ninstructions = "a \'\'\' b"\n')},
            "multi-line description": {"roles/doc-looker.toml": (
                'id = "doc-looker"\npack = "extra"\ndescription = "Reads.\\nMore."\ninstructions = "x"\n')},
            "invalid TOML": {"roles/doc-looker.toml": "id = \n"},
            "unknown manifest key": {"manifest.toml": 'extra_key = "x"\n' + MANIFEST},
            "unknown pack key": {"manifest.toml": MANIFEST.replace('color = "green"', 'colour = "green"')},
            "core pack not built for both platforms": {"manifest.toml": MANIFEST.replace(
                'plugin = "orchestra"\nplatforms = ["claude", "codex"]', 'plugin = "orchestra"\nplatforms = ["codex"]')},
            "duplicate plugin": {"manifest.toml": MANIFEST.replace('plugin = "orchestra-extra"', 'plugin = "orchestra"')},
            "claude pack without plugin": {"manifest.toml": MANIFEST.replace('plugin = "orchestra-extra"\n', "")},
            "missing common rules": {"roles/_common.md": None},
            "missing SKILL.md": {"skill/SKILL.md": None},
            "non-Markdown file in skill": {"skill/agents/openai.yaml": "interface: {}\n"},
            "hand-written role brief": {"skill/references/roles/doc-looker.md": "# doc-looker\n"},
            "token in a description": {"roles/doc-looker.toml": role_toml(
                "doc-looker", "extra", "Ask {{role:code-checker}} first.", "- x\n")},
            "marker in a description": {"roles/doc-looker.toml": role_toml(
                "doc-looker", "extra", "Reads <!-- @codex --> only.", "- x\n")},
            "description over 200 characters": {"roles/doc-looker.toml": role_toml(
                "doc-looker", "extra", "Reads " + "documents " * 20 + "today.", "- x\n")},
            "skill name other than orchestrate": {"manifest.toml": MANIFEST.replace(
                'name = "orchestrate"', 'name = "orchestra"')},
        }
        for name, overrides in cases.items():
            with self.subTest(name), self.assertRaises(build.BuildError):
                self.render(overrides)

    def test_role_instruction_errors_name_the_file_line(self):
        source = role_toml("doc-looker", "extra", "Reads.", "- Read.\n- Ask {{role:ghost}}.\n")
        line = source.splitlines().index("- Ask {{role:ghost}}.") + 1
        with self.assertRaisesRegex(build.BuildError, rf"roles/doc-looker\.toml:{line}: unknown role"):
            self.render({"roles/doc-looker.toml": source})

    def test_junctions_and_symlinks_count_as_links(self):
        target = self.root / "target"
        target.mkdir()
        (target / "precious.txt").write_bytes(b"keep\n")
        link = self.root / "link"
        if sys.platform == "win32":
            made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        else:
            link.symlink_to(target, target_is_directory=True)
            made = None
        if made is not None and made.returncode != 0:
            self.skipTest("cannot create a junction here")
        self.assertTrue(build._is_link(link))
        self.assertFalse(build._is_link(target))
        self.assertFalse(build._is_link(self.root / "missing"))

    def test_optional_fields_default(self):
        outputs = self.render({"roles/codex-helper.toml": role_toml(
            "codex-helper", "codex-only", "Knows.", "- x\n", platforms=["codex"])})
        self.assertIn("codex/agents/codex-helper.toml", outputs)
        builder = tomllib.loads(self.text(outputs, "codex/agents/code-builder.toml"))
        self.assertNotIn("sandbox_mode", builder)  # access defaults to write


class WriteCheckTests(BuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo = self.root / "repo"
        make_src(self.repo)
        self.outputs = build.render(self.repo / "src")

    def test_check_detects_drift_missing_and_stale_files(self):
        self.assertEqual(build.check(self.outputs, self.repo), sorted(self.outputs))
        build.write(self.outputs, self.repo)
        self.assertEqual(build.check(self.outputs, self.repo), [])
        edited = "codex/agents/code-builder.toml"
        missing = "plugins/orchestra/agents/code-checker.md"
        stale = ["plugins/orchestra/agents/retired.md", "skills/orchestrate/references/old.md",
                 ".claude-plugin/extra.json", "plugins/orchestra-gone/.claude-plugin/plugin.json"]
        (self.repo / edited).write_bytes(b"edited\n")
        (self.repo / missing).unlink()
        for path in stale:
            (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / path).write_bytes(b"old\n")
        self.assertEqual(build.check(self.outputs, self.repo), sorted([edited, missing] + stale))
        changed = build.write(self.outputs, self.repo)
        self.assertEqual(changed, sorted([edited, missing] + stale))
        self.assertEqual(build.check(self.outputs, self.repo), [])
        self.assertFalse((self.repo / "plugins/orchestra-gone").exists())  # emptied directories are pruned
        self.assertEqual(build.write(self.outputs, self.repo), [])

    def test_write_never_touches_files_outside_generated_roots(self):
        keep = ["README.md", "codex/config.toml", "skills/other-skill/SKILL.md", "pluginsextra/x.txt",
                "extras/codex-team/run.mjs", "src/notes.txt", ".claude/settings.json"]
        for path in keep:
            (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / path).write_bytes(b"keep " + path.encode() + b"\n")
        (self.repo / "codex/agents").mkdir(parents=True, exist_ok=True)
        (self.repo / "codex/agents/stale.toml").write_bytes(b"x\n")
        build.write(self.outputs, self.repo)
        self.assertFalse((self.repo / "codex/agents/stale.toml").exists())
        for path in keep:
            self.assertEqual((self.repo / path).read_bytes(), b"keep " + path.encode() + b"\n")
        self.assertEqual((self.repo / "src/manifest.toml").read_text(encoding="utf-8"), MANIFEST)
        self.assertEqual(build.check(self.outputs, self.repo), [])
        for bad in ({"README.md": b"x\n"}, {"plugins/../README.md": b"x\n"}, {"../outside.txt": b"x\n"},
                    {"/plugins/x": b"x\n"}, {"plugins\\x": b"x\n"}, {"plugins": b"x\n"}):
            with self.subTest(bad), self.assertRaises(build.BuildError):
                build.write(bad, self.repo)
            with self.subTest(bad), self.assertRaises(build.BuildError):
                build.check(bad, self.repo)
        self.assertEqual((self.repo / "README.md").read_bytes(), b"keep README.md\n")
        self.assertFalse((self.root / "outside.txt").exists())

    def test_cli(self):
        script = str(REPO / "scripts/build.py")

        def run(*args):
            return subprocess.run([sys.executable, script, "--root", str(self.repo), *args],
                                  capture_output=True, text=True, encoding="utf-8")

        result = run("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn(".claude-plugin/marketplace.json", result.stdout.splitlines())
        self.assertEqual(run().returncode, 0)
        result = run("--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        stray = self.repo / "plugins/orchestra/hooks/hooks.json"
        stray.parent.mkdir(parents=True)
        stray.write_bytes(b"{}\n")
        result = run("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("plugins/orchestra/hooks/hooks.json (not generated from src/; build.py deletes it)",
                      result.stdout.splitlines())
        result = run()
        self.assertIn("deleted plugins/orchestra/hooks/hooks.json", result.stdout.splitlines())
        (self.repo / "src/roles/doc-looker.toml").write_bytes(b"id = \n")
        result = run("--check")
        self.assertEqual(result.returncode, 2)
        self.assertIn("doc-looker.toml", result.stderr)


class RepositoryTests(unittest.TestCase):
    def test_generated_files_match_sources(self):
        outputs = build.render(REPO / "src")
        self.assertEqual(build.check(outputs, REPO), [], "run: python scripts/build.py")

    def test_gitattributes_keep_generated_outputs_lf(self):
        # --check compares bytes, so a CRLF checkout (core.autocrlf=true) must still get LF outputs.
        git = shutil.which("git")
        if not git or not (REPO / ".git").exists():
            self.skipTest("needs git and a git checkout")
        paths = sorted(build.render(REPO / "src"))
        result = subprocess.run([git, "check-attr", "eol", "--stdin"], capture_output=True, cwd=REPO,
                                input=("\n".join(paths) + "\n").encode("utf-8"))  # bytes: no CRLF translation
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.decode("utf-8").splitlines()
        self.assertEqual([line for line in lines if not line.endswith(": eol: lf")], [])
        self.assertEqual(len(lines), len(paths))


if __name__ == "__main__":
    unittest.main()
