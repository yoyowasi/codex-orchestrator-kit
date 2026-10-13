# Claude Code guide

This guide covers installing, using and troubleshooting the kit in Claude Code. For an overview see the [README](../README.md); for Codex see [codex.md](codex.md).

## What gets installed

| Plugin | Contents |
|---|---|
| `orchestra` (core) | the `orchestrate` skill, the 9 core role agents, the `team-review` and `team-research` Workflow scripts, and a brief for every role so uninstalled roles can still run |
| `orchestra-dev`, `orchestra-docs`, `orchestra-business`, `orchestra-content`, `orchestra-agent-dev` | the role agents of that pack only |

The `codex-only` pack (openai-solution-designer, sites-builder) is not built for Claude Code. The pack contents are listed in the [README](../README.md#packs).

## Install with plugins (recommended)

In a Claude Code session:

```text
/plugin marketplace add yoyowasi/codex-orchestrator-kit
/plugin install orchestra@codex-orchestrator-kit
```

Add any packs you want, then load the new components with `/reload-plugins` (or start a new session):

```text
/plugin install orchestra-dev@codex-orchestrator-kit
/plugin install orchestra-docs@codex-orchestrator-kit
/plugin install orchestra-business@codex-orchestrator-kit
/plugin install orchestra-content@codex-orchestrator-kit
/plugin install orchestra-agent-dev@codex-orchestrator-kit
/reload-plugins
```

The same works from a terminal, where `--scope user|project|local` chooses where the plugin is enabled (`project` shares it with everyone who uses the repository's settings):

```sh
claude plugin marketplace add yoyowasi/codex-orchestrator-kit
claude plugin install orchestra@codex-orchestrator-kit
claude plugin install orchestra-dev@codex-orchestrator-kit --scope project
```

Install only the packs whose roles you reuse. Every installed agent's description is loaded into each session, and a role from a missing pack still runs as a general-purpose agent with that role's brief.

## Update

Plugins carry the release version, so an update arrives when a new version is published:

```sh
claude plugin marketplace update codex-orchestrator-kit
claude plugin update orchestra@codex-orchestrator-kit
claude plugin update orchestra-dev@codex-orchestrator-kit   # each pack you installed
```

Restart Claude Code (or run `/reload-plugins`) to apply the update.

## Uninstall

```sh
claude plugin uninstall orchestra-dev@codex-orchestrator-kit   # each pack you installed
claude plugin uninstall orchestra@codex-orchestrator-kit
claude plugin marketplace remove codex-orchestrator-kit       # also uninstalls its remaining plugins
```

## Script install (without plugins)

If you cannot use plugin marketplaces, the installer copies the same files into your Claude Code config directory (`CLAUDE_CONFIG_DIR`, otherwise `~/.claude`). It needs Python 3.11 or newer:

```sh
git clone https://github.com/yoyowasi/codex-orchestrator-kit.git
cd codex-orchestrator-kit
python scripts/install.py --target claude                  # skill, core roles, workflows
python scripts/install.py --target claude --packs dev,docs # core + these packs
python scripts/install.py --target claude --packs all      # every pack built for Claude Code
python scripts/install.py --target claude --uninstall      # remove what it installed
```

| What | Where |
|---|---|
| Skill | `~/.claude/skills/orchestrate/` |
| Role agents | `~/.claude/agents/<id>.md` |
| Workflow scripts | `~/.claude/workflows/` |
| Install manifest (file list with hashes) | `~/.claude/orchestrator-kit/install-manifest.json` |
| Backups of replaced or removed files | `~/.claude/agent-backups/orchestrator-kit-<time>/` with `restore-map.txt` |

`--packs` replaces the previous selection, so list every pack you want to keep; without `--packs` a rerun keeps the packs installed before. The installer stops when a file it did not install differs from the release; review the file, then rerun with `--force` to back it up and replace it. `--dry-run` shows the whole plan, including such conflicts, without writing. `--target all` installs for Codex and Claude Code in one run. The full option list is in [codex.md](codex.md#install-options).

If `~/.claude/agents` did not exist before, restart Claude Code once so it notices the new directory.

**Use either the plugins or the script install, never both.** Both register the same skill and roles, so with both you get `/orchestrate` and `/orchestra:orchestrate`, and every role twice (`reviewer` and `orchestra:reviewer`). To switch, uninstall one way first.

## Runtime names

| Component | Plugin install | Script install |
|---|---|---|
| Skill | `/orchestra:orchestrate` | `/orchestrate` |
| Core roles | `orchestra:<id>`, for example `orchestra:reviewer` | `<id>` |
| Pack roles | `orchestra-<pack>:<id>`, for example `orchestra-dev:database-engineer` | `<id>` |
| Workflows | `/orchestra:team-review`, `/orchestra:team-research` | `/team-review`, `/team-research` |

The skill tells the orchestrator to pass `subagent_type` exactly as the Agent tool lists the role, so both layouts work without configuration.

## Migrating from manually copied files

If you copied an earlier version's role files into `~/.claude/agents` or its skill into `~/.claude/skills/orchestrate` by hand, Claude Code keeps loading them next to the plugin, and every role appears twice. Back them up and remove them before installing.

1. Back up both locations outside the config directory (adjust the paths if you set `CLAUDE_CONFIG_DIR`):

   ```sh
   mkdir -p ~/orchestrator-kit-manual-backup
   cp -r ~/.claude/agents ~/orchestrator-kit-manual-backup/agents
   cp -r ~/.claude/skills/orchestrate ~/orchestrator-kit-manual-backup/orchestrate
   ```

   ```powershell
   New-Item -ItemType Directory -Force "$HOME\orchestrator-kit-manual-backup" | Out-Null
   Copy-Item -Recurse "$HOME\.claude\agents" "$HOME\orchestrator-kit-manual-backup\agents"
   Copy-Item -Recurse "$HOME\.claude\skills\orchestrate" "$HOME\orchestrator-kit-manual-backup\orchestrate"
   ```

2. Delete `~/.claude/skills/orchestrate`, and in `~/.claude/agents` delete only the files that came from this kit: the roles in the [catalog](../README.md#packs) plus `orchestrator`, `template-author`, `openai-solution-designer` and `sites-builder` (with either hyphens or underscores in the file name). Keep your own agents.
3. Install the plugins as above and run `/reload-plugins`, or restart.

With the script install instead, `python scripts/install.py --target claude --packs all --force --prune-legacy` backs up and replaces files that have a role's file name, and backs up and removes `orchestrator.md`, `template-author.md`, `openai-solution-designer.md`, `sites-builder.md` and untracked files in `~/.claude/skills/orchestrate`. Without `--prune-legacy` it only lists those files under `legacy_files`. It stops if another file declares one of the role names, for example a copy saved with underscores in its file name; rename or delete that file by hand.

## Invoking

Call the skill explicitly, or describe work that needs a team and let Claude pick the skill:

```text
/orchestra:orchestrate Add sign-up and login to this project. Pick the specialists and models, split file ownership, then implement, review and verify.
```

```text
/orchestra:orchestrate Review the payment refactor on this branch. Read-only: report findings with evidence, do not change files.
```

```text
Use a team of specialists to turn the attached interview notes into a product brief and a 10-slide deck, with someone checking every figure against the notes.
```

Before spawning, the orchestrator states the planned team and models in one line, and it asks first if that would exceed a cost or usage limit you set. When the work does not need a team, it says "Working solo" with a reason and does it itself.

## Collaboration modes

### Named subagents and SendMessage (default)

The orchestrator spawns each specialist with the Agent tool, giving it a unique `name` such as `backend-1` or `reviewer-1`. Agents that were named at spawn can message each other with SendMessage, so an author and a reviewer exchange findings directly while the orchestrator decides scope, ownership and conflicts. A SendMessage to a finished agent resumes it with its full history; the skill allows at most two resumes before handing the work to a fresh agent. Independent specialists are started together, and subagents normally run in the background and report back when they finish.

### Workflow scripts

The core plugin ships two fixed-round pipelines, used only when you ask for them. Once started they take no further input, but a run pauses for agent permission prompts; before a long run, add the tools the agents need (such as Read, Grep, Bash for read-only git commands, WebSearch and WebFetch) to your allow rules.

| Command | What it does | Input |
|---|---|---|
| `/orchestra:team-review` | Read-only code review: one agent scopes the change, then correctness, security and missing-test lenses run in parallel, and a fresh verifier tries to refute every finding. Returns only findings that survived, plus the dropped ones and any lens that failed. | a target, such as `the changes on this branch against main`, or JSON `{"target": "...", "focus": "..."}`; default is the uncommitted diff |
| `/orchestra:team-research` | Sourced research: plans 3 to 6 sub-questions, researches each, checks every claim against its cited source, then writes a cited answer with uncertainty and open questions. | a question, or JSON `{"question": "...", "depth": "quick"}` with depth `quick`, `standard` (default) or `deep` |

```text
/orchestra:team-review the changes on this branch against main
/orchestra:team-research {"question": "Which EU rules apply to storing customer voice recordings?", "depth": "quick"}
```

Each stage uses the installed role agent (`orchestra:<id>`, then `<id>`) and falls back to a general agent with a one-line role brief only when neither agent type exists; any other stage failure is reported as a failed stage, not rerun without the role. The scripts set no model per stage, so every stage runs on your session's model (or on `CLAUDE_CODE_SUBAGENT_MODEL` when you set it). The review stages are told not to change files; the reviewers' shell access means that is instruction-level. The research stages are told not to write files either, and the researcher role has write tools.

Workflows are available on paid plans. On Pro, enable "Dynamic workflows" in `/config`. `CLAUDE_CODE_DISABLE_WORKFLOWS=1` turns them off. Non-interactive runs (`claude -p`) need an allow rule in your permission settings: `Workflow` allows every workflow, and `Workflow(<name>)` allows one by name. Whether a plugin workflow's rule uses `team-review` or `orchestra:team-review` is not documented and has not been verified here; check it in your setup.

### Agent teams (experimental)

Agent teams are off by default. When you have set `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (in the shell or in the `env` of `settings.json`), an Agent call with a `name` starts a teammate instead of a subagent, unless it is a fork or passes `isolation`. Teammates share a task list and message each other directly. Teams work only in interactive sessions, one team per session, teammates cannot create teams, teammates do not get an agent definition's `skills`, and token use is much higher. The skill uses teams only when you have already enabled them and never enables them itself; it treats teammates like named subagents.

## Access levels and what is enforced

Every role has one access level. These are the generated agent settings and what they really do, confirmed with runtime probes in Claude Code:

| access | Roles | Agent setting | Enforcement |
|---|---|---|---|
| `write` | all others | `disallowedTools: Agent` | none beyond the ownership written into the assignment |
| `read-shell` | reviewer, security-reviewer | `disallowedTools: Write, Edit, NotebookEdit, Agent` | partial: Bash, PowerShell and MCP tools remain, so the agent can still change files through the shell. "Do not modify files" is an instruction. |
| `read-only` | architect, evidence-reviewer, accessibility-auditor, user-insights-analyst | `tools: Read, Grep, Glob, WebFetch, WebSearch, SendMessage` | real allowlist: no shell, no MCP tools, no Skill tool. Structured output for Workflow schemas still works. |

A general-purpose agent that runs a role from a missing pack has the general-purpose tool set, so its access level is instruction-level. Subagents also run under your session's permission mode; plugin agents cannot set their own. For hard read-only enforcement beyond this, use permission deny rules or a PreToolUse hook in your own Claude Code settings.

## Nesting

The Agent tool is removed from every role, so specialists cannot build their own teams; only the main session spawns agents. A general-purpose fallback agent keeps the Agent tool. By default subagents may nest up to three levels below the main session; set `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` to turn nesting off entirely.

## Worktree isolation

In a git repository, when several agents write code in parallel, the orchestrator passes `isolation: "worktree"` so each writer works in its own worktree. A worktree starts from your default branch, not your current HEAD, so the orchestrator commits what a writer depends on first or names the base commit in the assignment. The writers' changes come back on separate branches or worktree paths, and the orchestrator merges them and resolves conflicts as the integrator. With agent teams enabled, an isolated Agent call still starts a subagent, not a teammate.

## Model and effort

- The orchestrator picks a tier per assignment (light, general, frontier) from the models the Agent tool currently offers, and passes `model` as an alias the tool accepts, such as `haiku`, `sonnet`, `opus` or `fable`, plus `effort` from `low` to `max`. The per-call `effort` needs Claude Code v2.1.292 or later, and `CLAUDE_CODE_EFFORT_LEVEL` overrides it.
- Claude Code uses the `model` passed on the call, then the agent definition's model, then `CLAUDE_CODE_SUBAGENT_MODEL`, then the main session's model. The role agents set no model, so omitting `model` gives `CLAUDE_CODE_SUBAGENT_MODEL` when set, otherwise the main session's model. `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` makes the environment setting win over the passed model; the orchestrator reports that it could not choose when that is active.
- It never uses a fork for a model assignment, because a fork inherits the main conversation, prompt and model.
- Your pins win: "only use sonnet" or a cost limit is a hard constraint. The main session's model is never changed.
- The final report lists the model and effort actually passed for each agent.

## Cost

- Each subagent, workflow stage and teammate has its own context window, so a team costs several times a solo session. Agent teams cost the most.
- `/orchestra:team-review` runs one scope agent, three lens agents and one verifier per finding. `/orchestra:team-research` runs one planner, one researcher per sub-question (3 to 6), one verifier per claim (up to 9 for `quick`, 25 for `standard`, 48 for `deep`) and one writer.
- The orchestrator starts with two or three specialists, reuses agents when their context helps, and stops at two review rounds per artifact.
- Installing only the packs you use keeps agent descriptions out of every session's context.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/orchestra:orchestrate` or the role agents do not appear | Run `/reload-plugins` or start a new session. Check that `orchestra` is installed and enabled in `/plugin`. |
| Every role appears twice (`reviewer` and `orchestra:reviewer`) | Remove manually copied files or the script install; see [Migrating](#migrating-from-manually-copied-files). |
| A role from a pack is "not found" | Install that pack's plugin, or let the orchestrator use the general-purpose fallback with the role brief. |
| `/orchestra:team-review` is not available | Workflows are off: on Pro enable "Dynamic workflows" in `/config`, unset `CLAUDE_CODE_DISABLE_WORKFLOWS`, and for `claude -p` add a `Workflow(<name>)` allow rule. |
| A workflow logs that a role is not installed | Expected without the role agent; the stage runs as a general agent with a short brief. |
| Peers cannot message each other | Both agents must have been named at spawn, and names must be unique in the session. The orchestrator relays the message when delivery fails. |
| Named agents behave like teammates | `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is set; unset it to return to subagents. |
| A new version does not show up | Run `claude plugin marketplace update codex-orchestrator-kit`, then `claude plugin update` for each plugin, and restart. |
| Script install: "Existing files differ" | A file the installer did not write is in the way. `--dry-run` lists every such file. Review them, then rerun with `--force` (each is backed up first). |
| Script install: "Role X already exists in another file" | Another agent file declares one of the role names. Rename or remove it, then rerun. |
