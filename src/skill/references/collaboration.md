# Collaboration protocol

Use this when two or more agents hand artifacts to each other or run a review loop. Independent single assignments need only the assignment template. Model choice follows [models.md](models.md).

## Ownership

- Every mutable resource has exactly one owner at a time: a file, document, sheet, slide deck, branch or worktree, database object, or a browser tab or UI session whose state others share.
- When several people must contribute to one resource, split it (separate files, sections or drafts) and name one integrator who merges them.
- Reviewers send findings; the owner edits. Nobody overwrites or reverts another agent's changes.
- Only you transfer ownership, and explicitly. First confirm the previous owner has actually stopped (no tool call in flight), then hand over the latest version, unfinished changes and verification results. A sent message or an interrupt request does not prove a resource is free.
- Agents that only read a shared UI still coordinate with its owner when navigation or selection would disturb the owner's work.

## Dependencies

- Start dependent work only after its inputs are ready. Do not start follow-up work on a guessed prior result.
- Run in parallel whatever fixed interfaces, units, audiences or formats already allow.
- Work that must rely on an assumption states the assumption and what would need redoing if it fails.
- Do not spawn a reviewer early just to wait for a draft. Spawn early only for independent preparation, such as collecting acceptance criteria or sources.

## Direct exchange

Peers send questions, evidence, drafts and findings to each other directly; you do not need to relay everything. Keep each message to four parts:

```text
<artifact and version> | <finding or question> | <evidence and impact> | <requested action>
```

- Tell the orchestrator about scope, ownership or shared-contract changes and about unresolved conflicts; those are yours to decide.
- Do not stage discussions where no exchange is needed. Agreement counts and message volume are not evidence of quality.
- Without a messaging tool, relay messages yourself and keep their source and version. Without a spawning tool, perform the roles yourself in sequence and never claim that parallel work or expert dialogue happened.

## Write, review, fix, confirm

1. The author sends the reviewer the artifact location and version, its verification results and the points to check.
2. The reviewer checks against the done criteria and sends each finding with location, evidence, impact and fix direction straight to the author. No findings means no findings; do not invent any.
3. The author fixes accepted findings or rebuts them with evidence.
4. The author reports the new version and its verification results; the reviewer re-checks only the fixed points and what they affect.
5. You check the latest artifact and the real verification output, then integrate. A success report alone never completes the loop.

## Conflicts

Each side states the point in dispute, its evidence and how the question could be decided. Settle it with a test, a recomputation or a source check when one exists. Otherwise you decide by the user's requirements, the done criteria and cost, never by majority, job title or model size. Report important unresolved disagreements instead of hiding them.

## Stopping rules

- Stop when the done criteria are met and verified.
- At most two review rounds per artifact; a third needs your explicit decision or goes to the user as an open issue.
- At most two resumes or follow-ups per finished agent; after that, spawn a fresh agent with a handoff.
- End a debate when a round brings no new evidence.
- Stop agents whose work is no longer needed, and do not keep idle agents waiting for work that may never come.

## Concurrency

Start with two or three agents. Never spawn one agent per catalog role. Reuse an existing agent for a same-model follow-up when its context helps. Find the platform limit below and do not guess how finished or interrupted agents free capacity.

<!-- @claude -->
## Claude Code tools

| Need | Claude Code |
|---|---|
| Start a specialist | `Agent` with `subagent_type`, `name`, `prompt`, `model`, `effort`; `isolation: "worktree"` for parallel writers in a git repository |
| Message a peer | `SendMessage` to the peer's `name` (both agents must have been named at spawn) |
| Follow up with a finished agent | `SendMessage` to its name, or its agent ID if the name was reused; resumes it with its full history |
| See who can be messaged | `ListAgents` |
| Wait | nothing; completion notifications arrive on their own, so never poll |
| Stop an agent | the session's stop tool, such as `TaskStop`; the user can also stop agents from `/tasks` |
| Fixed-round pipeline | Workflow scripts `/orchestra:team-review` and `/orchestra:team-research` (`/team-review` and `/team-research` with the script install), only when the user asks |

- Give each agent its peers' names in the assignment. If a message cannot be delivered, relay it yourself with its source and version.
- Concurrent subagents are capped by `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` (default 20, Claude Code v2.1.217 or later). That is a ceiling, not a target.
- Parallel writers in worktrees start from the default branch, not your HEAD, and return their changes on separate branches or worktree paths; you merge them and resolve conflicts as the integrator.
- Workflow scripts take no user input once started but pause for agent permission prompts, set no per-stage model, and need workflows enabled and permitted in this Claude Code setup. Subagents cannot start them.
- Agent teams (only when `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is already set): named Agent calls become teammates with a shared task list and direct messages. They work only in interactive sessions, one team per session; teammates cannot create teams; token use is much higher. Treat teammates like named subagents under this protocol.
<!-- @end -->
<!-- @codex -->
## Codex tools

The session exposes v2 (`collaboration.*`) or v1 (`multi_agent_v1.*`) tools, decided by the root model's metadata or `features.multi_agent_v2`. Follow the schema the session actually shows.

| Need | v2 `collaboration.*` | v1 `multi_agent_v1.*` |
|---|---|---|
| Start a specialist | `spawn_agent` (`task_name`, `message`; optional `agent_type`, `fork_turns`, `model`, `reasoning_effort`) | `spawn_agent` (`message` or `items`; optional `agent_type`, `fork_context`, `model`, `reasoning_effort`) |
| Inform a peer | `send_message`; does not start a new turn on an idle agent | `send_input`; at the default depth only you have it |
| Give an idle agent new work, or a running one a follow-up | `followup_task` | `send_input` |
| Interrupt the current turn | `interrupt_agent`; does not revert changes, and the agent remains available | `send_input` with `interrupt=true` |
| Wait | `wait_agent` (`timeout_ms`); returns an update summary, not the content | `wait_agent` |
| List paths and status | `list_agents` (`path_prefix`); do not poll it | none |
| Close or reopen | none | `close_agent` frees the slot; `resume_agent` reopens a closed agent |

- Address peers by the agent path or ID that `spawn_agent` returned. Use the full path for an agent in another subtree; never guess one.
- Children message each other only when they have the tools: in v2 when the child's model supports multi-agent v2, in v1 only with `agents.max_depth` of 2 or more (which also lets children spawn). Otherwise each child reports to you and you relay.
- A finding that needs a fix goes to the author with `followup_task`, which starts a turn on an idle agent; `send_message` alone waits until something else starts one.
- In v1, close finished agents with `close_agent`; completed agents hold a concurrency slot until closed.
- Read the delivered messages and the final report after `wait_agent`; the summary alone is not the result. Wait only when nothing independent remains, in short waits (about a minute) so the user is not blocked.
- Concurrency limits and their configuration keys are listed in SKILL.md under Running the team.
- `mcp__codex_app__create_thread` (Codex app only) starts a separate user task, only on the user's explicit request; never use it for team members or to get around concurrency limits.
- codex-team tools (`team_members`, `team_dispatch`, `team_wait`, `team_result`, `team_interrupt`) belong to the optional codex-team launcher. Use them only when they are present; do not assume features from their names.
<!-- @end -->
