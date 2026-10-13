# Codex guide

This guide covers installing, using and troubleshooting the kit in Codex. For an overview see the [README](../README.md); for Claude Code see [claude-code.md](claude-code.md).

## Install options

There are two ways to install the skill. Pick one.

**`$skill-installer` (skill only).** Ask Codex:

```text
$skill-installer install https://github.com/yoyowasi/codex-orchestrator-kit/tree/main/skills/orchestrate
```

This installs the `orchestrate` skill with every role's brief into `$CODEX_HOME/skills/orchestrate` (default `~/.codex/skills`). It registers no custom agents and does not touch `config.toml`. Restart Codex if the skill does not appear. To update it, delete that folder and run the same request again (`$skill-installer` stops when the folder exists), or switch to `install.py`.

`install.py` writes the skill to `~/.agents/skills/orchestrate` instead and does not see a `$skill-installer` copy, so using both registers the skill twice. When you switch, delete `~/.codex/skills/orchestrate` first, or keep that location with `--skills-dir ~/.codex/skills`.

**`scripts/install.py` (skill, registered roles, concurrency limit, optional launcher).** Needs Python 3.11 or newer. On Windows use `py -3` and on macOS/Linux `python3` if `python` is older.

```sh
git clone https://github.com/yoyowasi/codex-orchestrator-kit.git
cd codex-orchestrator-kit
python scripts/install.py --dry-run            # preview the plan, including conflicts
python scripts/install.py                      # skill + core roles
python scripts/install.py --packs dev,docs     # core + dev + docs
python scripts/install.py --packs all          # every pack, including codex-only
python scripts/install.py --uninstall          # remove what it installed
```

| Option | Default | Effect |
|---|---|---|
| `--target codex\|claude\|all` | `codex` | Where to install. `claude` is the [script install for Claude Code](claude-code.md#script-install-without-plugins); `all` does both. |
| `--packs LIST` | the packs installed before, otherwise `core` | Comma-separated pack names, or `all`. `core` is always included. The list replaces the previous selection, so name every pack to keep; roles of packs you drop are removed if unchanged. |
| `--codex-home PATH` | `CODEX_HOME`, otherwise `~/.codex` | Codex home for roles, `config.toml`, the install manifest, backups and the launcher. |
| `--skills-dir PATH` | as installed before, otherwise `~/.agents/skills` | Directory that receives the `orchestrate` skill folder. |
| `--claude-home PATH` | `CLAUDE_CONFIG_DIR`, otherwise `~/.claude` | Claude Code config directory, for `--target claude` or `all`. |
| `--with-cli` / `--no-with-cli` | as installed before (off for a new install) | Install or remove the optional Windows launcher from [extras/codex-team](../extras/codex-team/README.md). Needs Windows, Node.js 22+ and the Codex CLI on `PATH`. |
| `--bin-dir PATH` | as installed before, otherwise `%APPDATA%\npm` | Where the launcher's `codex-team.cmd` shim goes. |
| `--max-subagents N` | keep the existing limit, otherwise 12 | Set the per-session subagent limit in `config.toml` (positive integer). |
| `--force` | off | Back up and replace files that differ from the release and were not installed by this tool; with `--uninstall`, also back up and remove files changed since install. |
| `--dry-run` | off | Print the plan without writing: the files it would write (`would_write`), conflicts, removals, unmanaged roles and leftovers from earlier releases. It exits normally even when a real run would stop at conflicts. |
| `--uninstall` | off | Remove the files recorded in the install manifest that are unchanged since install. |
| `--prune-legacy` | off | Back up and remove files that releases before 2.0 installed: `orchestrator.toml` and `template-author.toml` in `agents/`, untracked files in the skill folder, and unmanaged role files of packs that are not selected. Without it, the installer lists such files under `legacy_files` and leaves them. |

`--with-cli` and `--max-subagents` apply only to the `codex` target.

What a Codex install writes:

| What | Where |
|---|---|
| Skill | `~/.agents/skills/orchestrate/` |
| Roles of the selected packs | `$CODEX_HOME/agents/<id>.toml` (kebab-case file, snake_case `name`) |
| Subagent limit | `$CODEX_HOME/config.toml`, edited in place |
| Install manifest (file list with hashes) | `$CODEX_HOME/orchestrator-kit/install-manifest.json` |
| Backups | `$CODEX_HOME/agent-backups/orchestrator-kit-<time>/`, with `restore-map.txt` mapping each copy to its original path |
| Launcher (with `--with-cli`) | `$CODEX_HOME/tools/codex-team/` and `codex-team.cmd` in `--bin-dir` |

All checks run before the first write, including a path-length check on Windows without long-path support. A file the installer wrote and nobody changed is updated silently; any other differing file stops the run until you review it and pass `--force`. If an earlier version lived in `~/.codex/skills/orchestrate`, pass `--skills-dir ~/.codex/skills` so the skill is not registered twice; later runs remember the directory.

## Invoking

```text
$orchestrate Add sign-up and login to this project. Pick the specialists and models, split file ownership, then implement, review and verify.
```

```text
$orchestrate Turn the attached customer feedback and cost data into a business proposal. Split user insights, financial scenarios and the document, and have someone check every figure.
```

You can also describe the work without `$orchestrate`; Codex picks the skill when the request matches its description. The orchestrator states the planned team and models in one line before spawning, or says "Working solo" with a reason.

## Packs and `agent_type`

Packs are listed in the [README](../README.md#packs). `core` is always installed; `--packs all` adds `dev`, `docs`, `business`, `content`, `agent-dev` and `codex-only`.

Every installed role is a Codex custom agent. Registered roles appear in `spawn_agent`'s "Available roles" list under their snake_case names (`evidence_reviewer`, `backend_developer`). For those, the orchestrator passes `agent_type` and sends only the filled-in assignment, because the role's instructions are already applied. Roles in a project's own `.codex/agents` are registered too.

### Roles that are not registered

Every role's brief ships inside the skill as `references/roles/<id>.md` (description, instructions and the common working rules). When a role is not registered, for example after a `$skill-installer` install or when its pack is not installed, the orchestrator spawns a default agent and pastes that brief above the assignment. The result is the same role, without the advisory `sandbox_mode`. When no catalog role fits, the orchestrator defines a runtime role (scope, deliverable, verification, access) in the assignment instead of forcing the nearest name.

## Collaboration tools

The orchestrator follows whatever multi-agent schema the session shows:

| Need | v2 (`collaboration.*`) | v1 (`multi_agent_v1.*`) |
|---|---|---|
| Start a specialist | `spawn_agent` with `task_name`, `message`, optional `agent_type`, `fork_turns`, `model`, `reasoning_effort` | `spawn_agent` with `message`, optional `agent_type`, `fork_context`, `model`, `reasoning_effort` |
| Inform a peer | `send_message` (does not start a turn on an idle agent) | `send_input`; at the default depth only the orchestrator has it |
| New work or a follow-up | `followup_task` (starts a turn on an idle agent) | `send_input` |
| Wait | `wait_agent` (returns a summary; the orchestrator then reads the delivered messages and final report) | `wait_agent` (a completed status may include the final message); finished agents hold a slot until `close_agent` |

In v2 the orchestrator passes `fork_turns="none"` with a self-contained assignment unless the agent needs the whole parent conversation. Peers are addressed by the agent path or ID that `spawn_agent` returned. Without any multi-agent tool, the orchestrator performs the roles itself in sequence and says that no agents ran.

Direct peer messages need the tools in the child, not only in the main session. In current Codex source, a v2 child gets the collaboration tools only when its model supports multi-agent v2, and a v1 child gets no agent tools at the default `agents.max_depth = 1`. A child without them reports to the orchestrator, which relays the message; the role instructions tell agents to do this.

## Model policy

- **Model choice follows the current tool's restrictions.** The orchestrator sets `model` and `reasoning_effort` only when the user's explicit delegation or applicable higher-priority instructions permit it; automatically selecting this skill is not explicit user delegation. When permitted, it chooses from the tool's current model list by tier (light, general, frontier) and by the difficulty of that piece of work, not by the role title.
- **Your pins and limits win.** "Only this model", "do not change it" and cost or usage limits are hard constraints. A model you merely mention is a preference.
- **Omitting `model` is not always "inherit".** When `[agents] default_subagent_model` (and `default_subagent_reasoning_effort`) is set in `config.toml`, a spawn without `model` uses it; otherwise it uses the parent's model.
- **Role files never pin a model.** A `model` inside a registered role file cannot be overridden at spawn time, so this kit's roles set none. A project's own role file might; the orchestrator then reports that it could not choose.
- `followup_task` and `send_input` keep the agent's model; a different model needs a new agent. The final report lists the model and effort actually passed.

## Concurrency

When `config.toml` has no limit, the installer adds:

```toml
[agents]
max_concurrent_threads_per_session = 12
```

This counts subagents only; the main agent is excluded. An existing `max_concurrent_threads_per_session`, or the legacy alias `max_threads`, is kept unless you pass `--max-subagents N`, which writes `N` (renaming a legacy `max_threads`). Changing an existing `config.toml` counts as a conflict: when the file needs a change (no limit yet, or a new `--max-subagents` value), the run stops until you pass `--force`, and the file is backed up first. The installer edits only that key, keeps comments and other settings, and supports a regular `[agents]` table or root `agents.<key>` assignments. With an inline table such as `agents = { ... }` it stops before writing; convert it to an `[agents]` table and rerun.

How Codex counts:

| Setting | Meaning |
|---|---|
| `[agents] max_concurrent_threads_per_session = N` (alias `max_threads`) | N subagents, main agent excluded, for v1 and v2 |
| `[features.multi_agent_v2] max_concurrent_threads_per_session = N` | v2 only: N threads including the main agent; takes precedence over `[agents]` |
| unset, v2 tools | 3 subagents |
| unset, v1 tools | 6 subagents; nesting depth `agents.max_depth` (default 1) |

The installer looks only at `[agents]`. If you set a limit under `[features.multi_agent_v2]`, that value still wins in v2 sessions.

The limit is a ceiling, not a team size; the orchestrator starts with two or three specialists. v2 has no depth limit, so "specialists never build teams" is an instruction there. Open a new session or restart Codex if a changed limit does not show. The optional launcher's window count is not affected by this setting.

## `sandbox_mode` is advisory

Role files with `access = "read-only"` or `"read-shell"` (architect, evidence-reviewer, accessibility-auditor, user-insights-analyst, openai-solution-designer, reviewer, security-reviewer) set `sandbox_mode = "read-only"`. Codex documents this key for custom agents, but in the Codex source current at this release, a spawned agent inherits the parent session's permissions and the role's `sandbox_mode` is not applied. Treat "read-only" as an instruction unless you have verified it on your Codex version. For real enforcement, run the parent session itself in Codex's read-only sandbox.

Where the setting is applied, such as in the optional codex-team launcher, it is real: the read-shell roles (reviewer, security-reviewer) may still run commands, but tests or builds that write caches, coverage or build output fail or ask for approval there. Give such checks to a write role or run them in the main session.

## Upgrading from v1

v1 installed all 37 roles, its skill files and optionally the launcher, without an install manifest. The 2.0 installer does not know those files, so it reports them as conflicts or as unmanaged roles. Run one of these once from a 2.0 checkout:

| Goal | Command | Result |
|---|---|---|
| Keep every role | `python scripts/install.py --packs all --force` | v1 files are backed up and replaced by 2.0 files, which are tracked from now on. `orchestrator.toml`, `template-author.toml` and the old `references/roles/*.toml` and `references/workflows.md` in the skill folder stay; the installer lists them under `legacy_files`. |
| Keep every role and clean up (recommended) | `python scripts/install.py --packs all --force --prune-legacy` | As above, and those leftover files are backed up and removed. |
| Keep only core | `python scripts/install.py --force --prune-legacy` | Core roles are replaced; the other v1 role files and the leftovers are backed up and removed. |

Run `python scripts/install.py --dry-run --packs all` first to see the whole plan. Add `--with-cli` if you installed the v1 launcher; otherwise its files in `$CODEX_HOME/tools/codex-team` stay as they were, and the installer notes that it found them. The v1 launcher needs the `orchestrator` role, so it stops working once `--prune-legacy` removes that role. Without `--prune-legacy`, Codex keeps listing the old `orchestrator` and `template_author` roles.

### Unmanaged role warning

On a later run, if `$CODEX_HOME/agents` contains files named after 2.0 roles outside the selected packs that no install manifest tracks (typically a v1 install, or copies made by hand), the installer lists them under `unmanaged_roles` and leaves them alone, with a note: rerun with `--packs all --force` to replace them with this release, or with `--prune-legacy` to back them up and remove them. They may be outdated, and Codex still registers them.

## Uninstall

```sh
python scripts/install.py --uninstall
python scripts/install.py --uninstall --force   # also back up and remove files you changed
```

Uninstall reads `$CODEX_HOME/orchestrator-kit/install-manifest.json` and removes only the files it recorded that are unchanged since install, then the manifest and the directories the installs created, once they are empty. Files you modified are kept and listed unless you add `--force`. The subagent limit in `config.toml` is left as it is; remove it yourself if you no longer want it.

A v1 install has no manifest, so `--uninstall` finds nothing to remove. Take it over first, then uninstall:

```sh
python scripts/install.py --packs all --force --prune-legacy
python scripts/install.py --uninstall
```

Or delete the files by hand: the role files in `$CODEX_HOME/agents`, the skill folder and, if installed, `$CODEX_HOME/tools/codex-team` and `codex-team.cmd`.

## Optional launcher

[extras/codex-team](../extras/codex-team/README.md) opens the coordinator and each worker as separate Codex CLI windows. It is optional, Windows-only and experimental, and its `team_*` tools are not built-in Codex features. Its models come from its own configuration, not from this skill's model policy.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Install failed: Existing files differ ...` | The listed files were not written by this installer, or `config.toml` needs the limit added. Review them, then rerun with `--force`; each is backed up first. Use `--dry-run` to preview. |
| `... is UTF-16` or `... is not valid UTF-8` | The named TOML file was saved in another encoding (PowerShell 5.1 `>` writes UTF-16). Re-save it as UTF-8 and rerun. |
| `These paths are too long for Windows ...` | Long-path support is off. Use shorter `--codex-home` or `--skills-dir` paths, or enable `LongPathsEnabled`. |
| `... resolves outside ...` | A directory on the way, such as `agents`, is a link to another place. Pass the real directory with `--codex-home`, `--skills-dir` or `--claude-home`. |
| `Cannot safely edit the agents setting in config.toml` | `[agents]` is an inline table or another layout the installer cannot edit safely. Rewrite it as a regular `[agents]` table and rerun. |
| `Role X already exists in another file` | Another file in `$CODEX_HOME/agents` uses one of the role names. Rename or remove it, then rerun. |
| `Unknown pack` or `Pack X is not built for claude` | Use the pack names from the README; `codex-only` exists only for Codex. |
| `Install manifest is not valid JSON` | Fix or remove `$CODEX_HOME/orchestrator-kit/install-manifest.json`; without it the installer treats existing files as unmanaged. |
| The skill appears twice | An older copy is in another skills directory (for example `~/.codex/skills/orchestrate`). Remove it, or install with `--skills-dir` pointing there. |
| A role is missing from "Available roles" | Its pack is not installed, or `--codex-home` pointed elsewhere. The orchestrator falls back to the role brief; rerun the installer with the pack to register it. |
| The orchestrator says it could not set a model | A role file (for example a project's own) pins `model`, the value is not in the tool's model list, or `default_subagent_model` applied because `model` was omitted. |
| `spawn_agent` fails with a limit error | The concurrency limit is reached. Check the real limit in `config.toml` (see [Concurrency](#concurrency)) and raise it with `--max-subagents N --force`, or ask for a smaller team. |
| `--with-cli currently supports Windows only` / Node.js or Codex CLI errors | The launcher needs Windows, Node.js 22+ and a signed-in Codex CLI on `PATH`. The skill itself works without it. |
