# Codex Team: multi-window launcher (optional, experimental)

> **Optional. Windows only. Codex only. Experimental.** The `orchestrate` skill does not need this launcher, and Claude Code users have no use for it. It is built on the experimental Codex App Server WebSocket interface (tested with Codex CLI 0.156.0) and may break when Codex changes.

The launcher starts a separate Codex App Server and a local MCP connection for each team, then shows the coordinator and every worker as a real Codex CLI window. `codex-team` and its `team_*` tools belong to this repository; they are not built-in Codex features, and the model settings below apply only to this launcher.

## Install and start

You need Windows, Node.js 22 or newer, Python 3.11 or newer, and the Codex CLI installed, signed in and on `PATH`. From the repository root:

```powershell
py -3 scripts/install.py --with-cli
codex-team start C:\projects\my-app
```

`--with-cli` copies the launcher to `$CODEX_HOME\tools\codex-team` and writes a `codex-team.cmd` shim to `%APPDATA%\npm` (change it with `--bin-dir`). Later installer runs keep the launcher; `--no-with-cli` removes it. Workers are Codex roles from `$CODEX_HOME\agents`, so install the packs your team needs, for example `--packs business` for `business_analyst` (`core` is always included, and `--packs` replaces the previous selection, so list every pack to keep).

The default team is a coordinator plus `frontend_developer`, `backend_developer` and `qa_engineer`. Starting a team only opens empty sessions; work begins when you type a request into the coordinator window, for example:

```text
Ask the frontend and backend developers to study the structure they will own.
Do not change files; combine their findings and propose an implementation order.
```

Once that works, ask for the actual change. For edits, the coordinator splits file ownership between workers:

```text
Implement editing of the user profile.
Settle the design first, then assign owned files to frontend and backend.
Use the routine model for plain implementation and the stronger model for complex analysis, then integrate after QA.
```

When a `codex_team` tool call or a command needs approval, approve or decline it in that window. The launcher never approves anything on your behalf.

## Commands

```powershell
codex-team start C:\projects\my-app --roles architect,frontend_developer,reviewer
codex-team start C:\projects\my-app --roles researcher,business_analyst,technical_writer
codex-team start C:\projects\my-app --models gpt-6-sol:medium,gpt-6-astra:high
codex-team roles
codex-team status
codex-team open
codex-team stop
```

| Command | Meaning |
|---|---|
| `start PROJECT` | Create a new team for the project folder and open its windows |
| `--roles a,b` | 1 to 6 workers, by Codex role name (snake_case); the coordinator is added automatically, so do not list `orchestrator` |
| `--models m:e,...` | Models for this team (see below); overrides `CODEX_TEAM_MODELS` |
| `roles` | List the roles registered in the Codex home |
| `status` | Show the latest team's workers, models and recent results |
| `open` | Reopen the latest team's windows; may open duplicates if windows are still open |
| `stop` | Stop the latest team's server, which also stops that team's running work |

With several teams, pass the `team.json` path that `start` printed to `status`, `open` or `stop`.

## Models

Team models are configuration. A model list is comma-separated `model:effort` entries, ordered from routine work to the most demanding work:

| Setting | Meaning | Default |
|---|---|---|
| `start --models LIST` | Models for this team | `CODEX_TEAM_MODELS` |
| `CODEX_TEAM_MODELS=LIST` | Models for new teams | `gpt-6-sol:medium,gpt-6-astra:high` |
| `CODEX_TEAM_COORDINATOR_MODEL` | Coordinator model: the name of a listed model, or `model:effort` for a coordinator-only model | the last listed model |

For example, in PowerShell before `codex-team start`:

```powershell
$env:CODEX_TEAM_MODELS = "gpt-6-sol:medium,gpt-6-astra:high"
$env:CODEX_TEAM_COORDINATOR_MODEL = "gpt-6-astra"
```

The first listed model is the worker default and the coordinator starts on the last one. Each model name may appear once. The resolved list is saved in the team's `team.json`, so later `status` and `team_dispatch` calls use the same models. Every dispatch must name a listed model, which runs at its listed effort. When a team starts, the launcher stops with an error if Codex did not apply the requested model and effort to a session; it never substitutes another model. A role file that pins its own `model` must use one of the team's models (this kit's roles pin none).

For every `team_dispatch` the coordinator picks `model` and `model_reason`:

```json
{
  "role": "backend_developer",
  "task": "Investigate the cause of the concurrency bug and report how to reproduce it.",
  "read_only": true,
  "model": "gpt-6-astra",
  "model_reason": "Requires analysing state changes across several requests"
}
```

The same worker can use another listed model for its next task. A worker that is still running does not accept new work; reassign after it completes or after an interruption you approved.

The coordinator's tools are `team_members`, `team_dispatch`, `team_wait`, `team_result` and `team_interrupt`. In this mode the coordinator sends work to the already connected workers and does not create extra built-in subagents.

## Files, sessions and sandboxes

Roles live in `$CODEX_HOME\agents`; team state and logs live in `$CODEX_HOME\teams`. `CODEX_HOME` defaults to `~\.codex`. The installed shim pins the Codex home and the Python interpreter chosen at install time.

The coordinator uses a registered `orchestrator` role when one exists (releases before 2.0 installed it) and a built-in coordinator brief otherwise.

Each worker is its own Codex session, so Codex's sandbox applies to it directly. Roles whose file sets `sandbox_mode = "read-only"` (for example `reviewer` or `architect`) run read-only, a dispatch with `read_only=true` runs under a read-only sandbox, and other work uses the session's workspace-write sandbox. Approvals stay on request. Unlike in a regular Codex session, read-only is enforced here: `reviewer` and `security_reviewer` can run commands, but tests or builds that write caches, coverage or build output fail or ask for approval, so give such checks to a writing role such as `qa_engineer`.

Workers share the project folder. Work that changes files must name `owned_paths`: relative files or directories inside the project, without globs and never the whole project root. A dispatch is refused while its paths overlap another worker's running task. The coordinator owns shared files. These reservations coordinate work; they are not per-file access control.

New installs and role updates apply to new teams. An existing team keeps the role instructions saved when it was created, so finish running work and start a new team.

## Troubleshooting

- **Command not found:** run the full path of `codex-team.cmd` printed by the installer, or add its directory to your user `PATH` and open a new terminal.
- **Role not found:** check that the installer installed the role's pack and that `--codex-home` points to the same Codex home. `codex-team roles` lists what is registered.
- **Model unavailable or not applied:** check that the Codex model picker offers every configured model, or change `CODEX_TEAM_MODELS` or `--models`.
- **Waiting for approval:** look for the approval request in that worker's Codex window.
- **Server connection failed:** read `server.log` in the team directory. A stopped team cannot be reconnected; start a new one.

## Limitations

- Windows only: other systems can install the `orchestrate` skill, but this launcher cannot open windows there.
- Codex only, and tied to the experimental App Server interface.
- File reservations are a coordination rule between workers, not isolation.
- The local server listens on `127.0.0.1` and is not meant to be exposed to a network.
