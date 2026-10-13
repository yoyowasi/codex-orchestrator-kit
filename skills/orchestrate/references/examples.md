# Team examples

Take only the parts a task needs; none of these teams has to run in full or all at once. Each author fixes their own artifact after review. Roles are in [roles.md](roles.md), the exchange rules in [collaboration.md](collaboration.md), model choice in [models.md](models.md).

## Team patterns

| Work | Team | Key exchange | Done when |
|---|---|---|---|
| Sourced research report | researcher + evidence_reviewer | researcher sends claims with source, date and uncertainty; reviewer marks what each source actually supports | the question is answered with direct sources and the remaining uncertainty |
| Business options and financial scenarios | business_analyst + financial_modeler; spreadsheet_modeler owns the workbook | period, currency, units and assumptions agreed before modeling | assumptions are stated, totals and scenarios recomputed |
| Report and slide deck | document_producer + presentation_designer as separate owners; evidence_reviewer for decisive figures | message order, figures and terms aligned across both | both rendered and checked for overflow, clipping and consistent numbers |
| Creative text and localization | creative_writer + localization_editor | intent and must-keep phrases; alternatives compared sentence by sentence | final text per locale, glossary and wording decisions |
| Course and assessment | learning_designer + a runtime subject-expert role | expert flags misconceptions, prerequisites and difficulty | timed lesson plan, exercises, items with answers mapped to objectives |
| Operations and automation | operations_designer + automation_engineer; app_operator as the single owner of any shared UI session | inputs, outputs and exception rules | runs on samples and exceptions, safe to re-run; system changes stay behind approval gates |
| Web feature | architect fixes contracts, then frontend_developer + backend_developer, then qa_engineer; accessibility_auditor or reviewer when triggered | contract changes go to the peer and to the orchestrator | integrated feature, scenario tests run, open issues listed |
| Skill or plugin | skill_author, plus plugin_developer only for a plugin; evidence_reviewer | claimed tools, parameters and permissions checked against the real runtime | structure validated, one representative run, actual install state reported |
| Sites work | the site-owning agent as sites_builder; helpers return bounded assets or research only | assets and findings handed to the owner | site built and previewed; publishing approved separately |

## Worked example

**User request:** "Add per-key rate limiting (100 requests per minute) to our public REST API and have someone check it for security before I merge. Don't deploy anything."

**Team or solo.** A team: the change touches a public, authentication-adjacent path, which triggers an independent review, and the user asked for a separate checker. Two agents are enough. One service changes, the middleware pattern is clear (no architect), and the implementer's tests cover the scenarios (no QA). The security reviewer is spawned once the implementation passes its tests, not earlier to wait. Announced as: "Team: backend developer (general tier) implements, security reviewer (frontier tier) reviews; I integrate and run the tests."

Each agent is named after its role, which is unique here: `backend_developer` and `security_reviewer`.

**Assignment 1**

```text
Role: backend_developer
Model: general tier, medium effort (well-understood middleware change with tests to check it)
Goal and done: per-API-key limit of 100 requests/minute on all /v1 routes; HTTP 429 with Retry-After when exceeded; limit configurable; existing and new tests pass
Working path: services/api (paths below are relative to it)
Inputs: src/middleware/, src/config.ts, the Redis client in src/lib/redis.ts; main at commit a1b2c3d
Access: owns and may edit src/middleware/rate-limit.ts (new), src/app.ts, src/config.ts, tests/rate-limit.test.ts | read only everything else
Instructions and skills: the project instruction file, sections "Testing" and "Configuration"; no stack skill applies
Mode: implement
Approval gates: deployment, changes to production Redis or production config, not approved: return target, reason, impact, rollback
Peers: security_reviewer: when tests pass and it contacts you, answer its questions; fix its findings and reply with the new commit
Verify: npm test and npm run lint pass; new tests cover the limit, the reset window and per-key isolation
Report: result; changed files; checks run (command, outcome, evidence scope); unverified items
```

**Assignment 2** (spawned after the implementer reports passing tests)

```text
Role: security_reviewer
Model: frontier tier, high effort (a bypass on a public path is high impact and easy to miss)
Goal and done: find exploitable weaknesses in the rate-limit change, or state that none were found and what was not checked
Working path: services/api (paths below are relative to it)
Inputs: commit d4e5f6a from backend_developer and its test output
Access: read only, whole repository; owns nothing; may run tests and static analysis; do not modify files (an instruction, not enforced by tools)
Instructions and skills: the project instruction file, section "Security"; security-best-practices if installed
Mode: read-only
Approval gates: none in scope; do not send traffic to staging or production
Peers: backend_developer: send each finding as artifact and version | finding | evidence and impact | requested fix; confirm the fixes
Verify: client-supplied headers used as the key (X-Forwarded-For), missing or invalid keys, races in counter increments, behavior when Redis is down
Report: findings with severity, file and line, evidence and fix direction; checks run with evidence scope; what was not checked
```

Spawned with `spawn_agent(task_name: "backend_developer", agent_type: "backend_developer", model: <general-tier model from the tool's list>, reasoning_effort: "medium", fork_turns: "none", message: <assignment 1>)` and later the same call for `security_reviewer` with a frontier-tier model and `reasoning_effort: "high"`. If a role is missing from "Available roles", omit `agent_type` and paste references/roles/<id>.md above the assignment. Each agent gets the other's returned path; the reviewer's findings reach the idle implementer through `followup_task`, sent by the reviewer when its model gives it the collaboration tools and otherwise relayed by you.

**Coordination.** The reviewer found one issue: for unauthenticated requests the key fell back to the client-controlled X-Forwarded-For header. The implementer fixed it in commit e7f8a9b and added a test; the reviewer re-checked the changed lines. One review round was enough. The orchestrator then ran the test suite and lint itself.

**Final report** (sent in the user's language)

```text
Rate limiting is implemented and passed an independent security review after one fix; nothing was deployed.

Artifacts: src/middleware/rate-limit.ts, src/app.ts, src/config.ts, tests/rate-limit.test.ts (commit e7f8a9b)
```

| Role (agent) | Model (effort) | Why |
|---|---|---|
| backend_developer | <general-tier model ID> (medium) | routine middleware change with tests to check it |
| security_reviewer | <frontier-tier model ID> (high) | a bypass on a public path is high impact |

```text
Verification:
- npm test: 214 passed, including 7 new rate-limit tests (static: local unit tests)
- npm run lint: clean (static)
- Security review: 1 finding (spoofable header used as the key) fixed and re-checked (static)
- Unverified: no run against a real Redis instance or staging (no API or production evidence)

Limits and decisions needed:
- When Redis is unreachable the limiter fails open. Decide whether it should fail closed.
- Deployment is an approval gate: when you approve, name the target environment; rollback is reverting e7f8a9b.
```
