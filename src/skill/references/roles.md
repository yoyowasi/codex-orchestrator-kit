# Roles

A role fixes a responsibility and its deliverables. It grants no tools, accounts or permissions, and it does not fix a model; choose the model per assignment with [models.md](models.md) and the skills with [skill-routing.md](skill-routing.md). One agent may cover several roles, and the peers a role mentions are possible partners, not agents to spawn.

## Packs

Roles ship in packs. `core` is installed by default with the plugin or `install.py`; `dev`, `docs`, `business`, `content` and `agent-dev` are optional. Every role's full brief also ships with the skill as `roles/<id>.md` next to this file, so a role whose pack is not installed can still run in a generic agent with its brief pasted above the assignment.

<!-- @claude -->
With the plugin install, agents are named `<plugin>:<id>`: `orchestra` (core), `orchestra-dev`, `orchestra-docs`, `orchestra-business`, `orchestra-content`, `orchestra-agent-dev`. With the script install they are the bare `<id>`. Pass `subagent_type` exactly as the Agent tool lists it. A missing pack is added with `/plugin install <plugin>@{{marketplace}}`; suggest that to the user only when the roles will be reused, and never install anything yourself.
<!-- @end -->
<!-- @codex -->
A `$skill-installer` install registers no roles; every role then runs from its brief. Registered roles appear in `spawn_agent`'s "Available roles" list under their snake_case names. Only roles installed as custom agents (for example in `~/.codex/agents` or a project's `.codex/agents`) are registered; the briefs in this skill's `roles/` directory are not. A `codex-only` pack holds roles that depend on OpenAI-only products. A missing pack is added by rerunning `python scripts/install.py --packs <list>` from a clone of `{{repository}}`, listing every pack to keep; suggest that to the user only when the roles will be reused, and never install anything yourself.
<!-- @end -->

## Access levels

<!-- @claude -->
| access | What the agent gets | Enforcement |
|---|---|---|
| `write` | every tool except Agent | none beyond your assignment's ownership |
| `read-shell` | no Write, Edit, NotebookEdit or Agent; keeps the shell to run tests and analysis | partial: the shell can still change files, so "do not modify files" is an instruction |
| `read-only` | only Read, Grep, Glob, WebFetch, WebSearch and SendMessage | real allowlist: no shell, no MCP tools, no Skill tool |

These settings apply only to installed role agents. A role run from its brief in a `general-purpose` agent keeps every tool, so its access level is an instruction.
<!-- @end -->
<!-- @codex -->
| access | What the role file sets | Enforcement |
|---|---|---|
| `write` | nothing extra | none beyond your assignment's ownership |
| `read-shell` | `sandbox_mode = "read-only"`; the role may run tests and analysis | advisory: current Codex source makes spawned agents inherit the parent session's permissions |
| `read-only` | `sandbox_mode = "read-only"` | advisory, as above; treat "do not modify files" as an instruction unless verified on this Codex version |

Where `sandbox_mode` is applied, such as in the optional codex-team launcher, read-shell roles are truly read-only: tests or builds that write caches, coverage or build output fail or need approval. Assign that work to a write role, or run it yourself.
<!-- @end -->

Report access honestly: say "read-only by instruction" whenever tools do not enforce it.

## Catalog

{{role-catalog}}

## Runtime roles

When no role fits, do not force the nearest name. Define a runtime role in the assignment's Role field:

- a kebab-case name that does not clash with the catalog;
- scope and expertise, and what is out of scope;
- the deliverable and its format;
- verification criteria;
- the inputs it receives and the results it hands to which peers;
- access: read-only unless it must edit, plus the files it owns.

Spawn it as a generic agent and paste, above the assignment, the definition and the "Working rules" section of any brief in `roles/` (every brief carries the same working rules).

## Keeping a role

Keep a runtime role only when you assigned the same one twice or the user asks. Never edit installed copies (plugin caches, agent directories, this skill's files): they are generated and are replaced on the next install or update. Instead propose a new `src/roles/<id>.toml` to the source repository, `{{repository}}`:

```toml
id = "subject-expert"
pack = "content"
description = "One English sentence: what it does and when to pick it."
access = "read-only"
instructions = '''
- One rule per line; do not repeat the common working rules.
'''
```

Never set a model in a role file. If the user is working in a clone of the source repository and asks for it, add the file there, run `python scripts/build.py` and `python scripts/build.py --check`, and let the user reinstall; otherwise hand the TOML to the user to submit.
