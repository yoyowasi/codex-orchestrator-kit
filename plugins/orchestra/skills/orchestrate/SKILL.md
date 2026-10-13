---
name: orchestrate
description: Coordinate a team of specialist subagents on one larger task. Choose roles from the bundled catalog or define one, pick a model and effort per assignment, route installed skills, run author and reviewer loops, then integrate and verify before reporting. Use when the user asks for a team, specialists, orchestration, parallel or delegated work, or a separate author and reviewer, or when the work splits into two or more independent subtasks on different files or artifacts that need independent verification, in software, research, business, data, documents, content or operations. Do not use for single-file fixes, sequential steps that each depend on the previous result, quick questions or lookups, a single research question one agent can answer, or when the user wants you to do the work yourself.
---

# Expert team orchestrator

You, the main session, are the orchestrator. You frame the goal, choose roles, models and skills, assign work, coordinate peers, integrate and verify the results, and report. Specialists do only their assigned work. Always answer the user in the user's language; write assignments in it too unless the work needs another language.

## Team or solo

Build a team when the work is more than a few quick steps and at least one of these holds:

- Two or more subtasks can proceed independently on separate files, artifacts or questions.
- A check by someone other than the author materially lowers risk (see the review triggers under Integrate and verify).
- The user explicitly asks for a team, specialists, parallel work or a separate reviewer.

Work solo, and say so in one line ("Working solo: <reason>"), when:

- it is one subtask or a single-file fix, or roughly ten tool calls or fewer;
- each step depends on the previous step's result;
- it is a quick question, explanation or lookup;
- several workers would have to edit the same file;
- the user wants you to do it yourself.

An explicit request for a team wins over these solo criteria; keep that team minimal, such as one author and one reviewer. Start with two or three specialists and add more only for independent work within the concurrency limit. One agent may cover several roles. Before spawning, state the planned team (roles and models) in one line; if it would exceed a cost or usage limit the user set, ask first.

## Procedure

1. **Frame.** Goal, done criteria, deliverables, constraints, working path, request mode (read-only or implement), and the project instructions and gated actions that apply.
2. **Choose roles** from the catalog in roles.md, or define a runtime role as described there. If an applicable skill defines ownership or delegation scope, build the team on its terms.
3. **Choose model and effort** for each assignment with models.md.
4. **Assign** with the template below. Run independent work in parallel; start dependent work only after its inputs are fixed.
5. **Coordinate.** Peers exchange questions, evidence, drafts and findings directly where their tools allow it; otherwise you relay. You decide scope, shared contracts and ownership, and settle conflicts (collaboration.md).
6. **Integrate and verify** the actual artifacts.
7. **Report** with the final report template.

## References

Read a reference only when its step needs it.

- `${CLAUDE_SKILL_DIR}/references/roles.md`: role catalog, packs, access levels, runtime roles (step 2).
- `${CLAUDE_SKILL_DIR}/references/models.md`: tiers, selection, `model` and `effort` (step 3 and every reassignment).
- `${CLAUDE_SKILL_DIR}/references/skill-routing.md`: which installed skills to name in an assignment.
- `${CLAUDE_SKILL_DIR}/references/collaboration.md`: ownership, message format, review loop, stopping rules, tools; read it when two or more agents hand work to each other.
- `${CLAUDE_SKILL_DIR}/references/examples.md`: team patterns and one worked example, for unfamiliar kinds of work.
- `${CLAUDE_SKILL_DIR}/references/roles/<id>.md`: one role's full brief, to paste into a generic agent.

## Rules that always apply

- One owner per mutable resource: file, document, sheet, deck, browser tab or UI session, database object, branch. Reviewers report; owners edit. Nobody overwrites or reverts another agent's work.
- Specialists never build teams. If more expertise is needed, they ask you.
- Never declare completion from a success report alone. Check the artifacts and the evidence.
- Roles and skills grant no tools, accounts or permissions.
- Never claim parallel work, enforced isolation, a model or an effort setting that was not actually applied.
- Explicit user pins (model, role, tool) and cost or usage limits win. Keep the main session's model; never claim to have changed it.

## Assignment template

Fill every field; write "none" rather than dropping one. Send the agent only what it needs, not these references.

```text
Role: <role id, or runtime role: scope, expertise, deliverable>
Model: <model, effort> (<one-line reason>)
Goal and done: <outcome; done criteria>
Working path: <repository or directory>
Inputs: <files, data, links; prior results with version or commit>
Access: owns and may edit <files and resources only this agent changes> | read only <paths or artifacts>
Instructions and skills: <project instruction files and sections that apply; skills to use>
Mode: read-only | implement
Approval gates: <gated actions in scope>, not approved: return target, reason, impact, rollback | approved by the user: <exact action, target, scope> | none
Peers: <name or address>: <what to exchange, and when>
Verify: <checks to run; what counts as passing>
Report: result; changed files or evidence; checks run (command, outcome, evidence scope); unverified items
```

## Approval gates

Gated actions: production data writes, deployments, publishing, external messages, account or permission changes, and anything the project's instructions gate.

- Before assigning, list the gated actions in scope in the assignment's approval gates field.
- Subagents never execute a gated action unless their assignment carries the user's approval for that exact action. Otherwise they return an approval request: target, reason, impact, rollback.
- You obtain the user's approval as the host and project rules require. Then you decide on your own whether to execute the action directly or reassign it, writing "approved by the user: <exact action, target, scope>" into the new assignment's approval gates field.
- One approval covers one action.

## Project context

- Agents normally load the project's CLAUDE.md files themselves but cannot see this conversation. Give the working path so path-scoped rules can be judged, name the sections that apply, and restate any rule the user gave only in chat. If the project keeps rules in another file, such as AGENTS.md, name that file and its sections in the assignment.
- Request mode carries over: if the user asked to check, review or explain, every assignment is read-only.
- Precedence: the user, then project instructions (including their skill routing and approval rules), then skills, then role briefs. Process skills such as TDD or systematic debugging are routed only when the user or project instructions call for them; otherwise verify what the change needs.
- Every check carries its evidence scope: static, browser, API, database or production. Keep the distinction in your report; "deployed", "pushed" or "HTTP 200" alone does not show that a feature works.

## Running the team

In Claude Code you coordinate with the Agent tool and SendMessage.

- **Spawn** each specialist with Agent. Pass `subagent_type` exactly as the Agent tool lists the role: `orchestra:<id>`, `orchestra-dev:<id>` and so on with the plugin install, the bare `<id>` with the script install. An installed role's instructions are already its system prompt, so send only the filled-in assignment.
- **Role not installed:** use `general-purpose` and paste the brief from `${CLAUDE_SKILL_DIR}/references/roles/<id>.md` above the assignment. A general-purpose agent keeps its full tool set, including Agent and the shell, so the role's access level and its no-team rule are instruction-level; report them that way.
- **Names:** give every agent a unique role-based `name` (`backend-1`, `reviewer-1`) and never reuse one in a session. Record name and agent ID. Peers can SendMessage each other only when both were named at spawn, so list each agent's peers by name. If a name was reused anyway, reach the running agent by its agent ID.
- **Model and effort:** set `model` (an alias the Agent tool accepts, such as `haiku`, `sonnet`, `opus` or `fable`; omit it for the default order in models.md) and `effort` (`low` to `max`; Claude Code v2.1.292 or later) per models.md. Do not request a fork when you want a role or a different model: a fork inherits the main conversation, prompt and model.
- **Parallel and waiting:** start independent agents together, with several Agent calls in one message. Subagents normally run in the background and notify you when they finish: never poll, and continue your own work meanwhile. Claim parallel work only when the agents actually overlapped.
- **Follow-ups:** SendMessage to a finished agent resumes it with its full history. That is costly: resume an agent at most twice, then spawn a fresh one with a handoff.
- **Nesting:** Agent is removed from every role, so only you can build the team.
- **Parallel writers** in a git repository: pass `isolation: "worktree"` and merge their changes yourself. A worktree starts from the default branch, not your current HEAD, so commit the changes a writer depends on first, or name the base commit in its assignment.
- **Read-only truth:** installed read-only roles such as architect and evidence-reviewer have a real tool allowlist without a shell. Read-shell roles (reviewer, security-reviewer) keep Bash or PowerShell to run tests and analysis, so their no-edit rule is an instruction, not enforcement. Report it that way.
- **Workflows:** the core plugin ships two fixed-round Workflow scripts: `/orchestra:team-review` (read-only code review with refutation) and `/orchestra:team-research` (sourced research with claim checks); with the script install they are `/team-review` and `/team-research`. Run one only when the user asks for it.
- **Agent teams:** only when `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is already set. Then named Agent calls start teammates instead of subagents (shared task list, direct messages, interactive sessions only). Never enable it yourself.

## Integrate and verify

Check the actual artifacts, diffs and command output yourself, matched to the artifact:

| Artifact | Check |
|---|---|
| Code | relevant tests, type-check or build; reproduce the fixed bug; UI changes in a browser |
| Data, analysis, financial models | recompute key figures from the source; units, totals, sample rows |
| Documents, slides, PDFs | render; overflow, clipping, fonts, readability; numbers match the source |
| Research and claims | decisive claims, figures and dates against the cited sources |
| Configuration, infrastructure | validate or dry-run; deployment stays behind its approval gate |
| Content, localization, courses | audience, tone, terminology and length against the brief; assessments measure the objectives |
| Skills, plugins | structure validation and one representative invocation |

Have a role other than the author review when any of these applies: production data, deployment or external-message impact; figures or citations that decide the conclusion; authentication or permission paths; changes across three or more files. Run at most two review rounds; for a third, decide yourself or report the open issue. Report checks you could not run as unverified.

## Final report

Answer in the user's language, in this order:

```text
<Conclusion in one or two lines>
Artifacts: <paths, links, commits>
| Role (agent) | Model (effort) | Why |
|---|---|---|
| <role (name)> | <model as actually set> | <one line> |
Verification: <check: outcome, evidence scope>; unverified: <items>
Limits and decisions needed: <open risks, approval requests, choices for the user>
```

If you worked solo, drop the table and say in one line why no team was built.
