# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 2.0.0 - 2026-10-13

A rewrite for both Codex and Claude Code. Upgrade steps are in the README under "Upgrading from v1".

### Added

- Claude Code support through the `codex-orchestrator-kit` plugin marketplace: the core plugin `orchestra` (skill `/orchestra:orchestrate`, core roles, Workflow scripts) and one plugin per optional pack (`orchestra-dev`, `orchestra-docs`, `orchestra-business`, `orchestra-content`, `orchestra-agent-dev`).
- Claude Code Workflow scripts `/orchestra:team-review` (read-only review through correctness, security and missing-test lenses, with an independent refutation attempt per finding) and `/orchestra:team-research` (sourced research with a per-claim source check). Each stage uses the installed role agent and falls back to a general agent with a role brief.
- Claude Code coordination in the skill: named subagents that message each other with SendMessage, worktree isolation for parallel writers, and agent teams only when the user has already enabled them.
- Role packs `core`, `dev`, `docs`, `business`, `content`, `agent-dev` and `codex-only`, with `core` installed by default.
- An access level per role (`write`, `read-shell`, `read-only`), mapped to Claude Code tool settings and Codex `sandbox_mode`, with documentation of what each level really enforces on each platform.
- A single source in `src/` and the `scripts/build.py` generator, with `--check` for drift in CI. Generated files are committed; `docs/architecture.md` is the contract.
- A brief for every role in the skill (`references/roles/<id>.md`), so a role that is not installed can run in a generic agent.
- Solo-versus-team criteria, an assignment template, a final report template and approval-gate rules in `SKILL.md`, plus team patterns and a worked example in `references/examples.md`.
- Installer options `--target codex|claude|all`, `--packs`, `--claude-home`, `--uninstall`, `--prune-legacy` and `--no-with-cli`; an install manifest with SHA-256 hashes in `<home>/orchestrator-kit/install-manifest.json`; notes for unmanaged role files, files and a launcher left by earlier releases (`unmanaged_roles`, `legacy_files`).
- `--dry-run` reports the whole plan, including conflicts, without needing `--force`; reruns keep the `--skills-dir` and `--bin-dir` of the previous install; uninstall removes the directories the installs created once they are empty.
- Configurable models for the codex-team launcher: `start --models`, `CODEX_TEAM_MODELS` and `CODEX_TEAM_COORDINATOR_MODEL`. The launcher uses a built-in coordinator brief when no `orchestrator` role is installed.
- `README.ko.md`, `docs/claude-code.md`, `docs/codex.md`, `LICENSE` (MIT) and this changelog.
- CI steps for the generated-file check and the workflow scripts, on Ubuntu and Windows with Python 3.11 and 3.12.

### Changed

- Skill text, role instructions, launcher messages and the README are in English. The orchestrator still answers in the user's language.
- 35 roles (33 on Claude Code). Role descriptions exist in one place, and the role catalog in `references/roles.md` is generated from them.
- The Codex installer installs only the `core` roles unless `--packs` selects more, and later runs reuse the installed packs and launcher choice.
- Codex model policy: a direct invocation of the skill (`$orchestrate`) delegates the choice and later reassessment of subagent model and effort to the orchestrator, without approval for routine choices; automatic selection of the skill does not. Explicit user pins, cost limits and the tool's current restrictions still win, and the delegation never approves a gated action. Omitting `model` uses `[agents] default_subagent_model` when it is set; role files never pin a model.
- Codex collaboration guidance covers both v2 (`collaboration.*`) and v1 (`multi_agent_v1.*`) tools, uses registered roles through `agent_type`, and explains which concurrency keys include the main agent.
- Process skills (test-driven development, systematic debugging, verification-before-completion, brainstorming) are routed only when the user or project instructions call for them.
- Specialists return an approval request (target, reason, impact, rollback) for gated actions instead of executing them. An approval covers the actions, targets and scope the user approved, is not asked for again within them, and does not extend beyond them.
- `tools/codex-team` moved to `extras/codex-team` as an optional, Windows-only, Codex-only experimental launcher. `docs/cli-team.md` became `extras/codex-team/README.md`, and the launcher tests moved to `extras/codex-team/team.test.mjs`.
- `.gitattributes` keeps every generated text type at LF line endings.

### Removed

- The `orchestrator` role. The main session is the orchestrator, and its rules live in `SKILL.md`.
- The `template-author` role, merged into `skill-author`.
- Role TOML files inside the skill (`references/roles/*.toml`) and `references/workflows.md`.
- The hard-coded `gpt-6-sol` and `gpt-6-astra` models in the launcher code. They remain the default configuration.

### Fixed

- Access claims match enforcement: Claude Code `read-only` roles use a real tool allowlist without a shell, `read-shell` roles keep a shell so their no-edit rule is an instruction, and Codex `sandbox_mode` is advisory because current Codex source gives spawned agents the parent session's permissions.
- Specialists may carry out a gated action only when their assignment states the user's approval for that exact action; otherwise they return an approval request.
- `fork_turns` guidance matches the current Codex behavior: only `"none"` and `"all"`, omission means `"all"`, and a full-history fork inherits the parent's model and effort, so model and effort are set only with `"none"`.
- The build rejects directory links and Windows junctions at generated roots or along output paths before it writes or deletes anything.
- The installer refuses to change `--skills-dir` while modified files remain in the previous skills directory, and refuses to remove files whose path resolves outside the installation location through a directory link.
- `/orchestra:team-research` treats a `partial` verdict without a nonempty corrected claim as unverified: the claim leaves the verified, citable claims and reaches the synthesis only in the list of claims that failed verification.
- Registered Codex roles no longer get their instructions pasted a second time.
- Role names are rendered for each platform (snake_case in Codex, kebab-case in Claude Code) instead of being mixed.
- Skill routing no longer assumes Codex-only skills on Claude Code.
- Updates and uninstalls change only files the installer recorded and that are unchanged since install, and refuse install-manifest entries outside the places the installer writes.
- The `codex-team.cmd` launcher shim is written in the console code page, so paths with non-ASCII characters (for example a Korean user name) work.
- `codex-team start --roles` without a value and `codex-team status` before any team was started print a clear error.

## 1.x - 2026-09-23 to 2026-10-01

Untagged releases on `main`: Codex only, with Korean skill and role text. Summarized from the commit history.

- 2026-10-01 (`1828ebe`): model selection builds light, general and frontier candidates from the models the spawn tool currently offers instead of fixed model names.
- 2026-09-27 (`d61b92a`): the installer sets `[agents] max_concurrent_threads_per_session = 12` when no limit is configured, keeps an existing limit, and adds `--max-subagents`.
- 2026-09-24 (`c1baabf`): skill routing separates live Excel workbooks from spreadsheet files and Google Sheets, and the app-operator role prefers an app's own skill or connector before UI or browser automation.
- 2026-09-24 (`4752ca9`): 37 roles; model, collaboration, skill-routing and workflow references; model and effort chosen per assignment.
- 2026-09-23 (`f623486`): first release with the `$orchestrate` Codex skill, 20 roles, `scripts/install.py` and the Windows `codex-team` multi-window launcher.
