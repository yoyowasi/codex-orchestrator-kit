# Skill routing

A role sets responsibility; a skill sets how a specific kind of work is done. Name a skill in an assignment's "Instructions and skills" field only when the work matches that skill's own trigger, never because of the role title alone.

## Precedence

1. The user's instructions.
2. Project instructions (CLAUDE.md, AGENTS.md), including any skill routing and approval rules they define.
3. The applicable skill's own SKILL.md.
4. The examples below and skill mentions in role briefs.

A matching skill grants no tools, accounts or permissions. Creating a file is not publishing, sending or changing an account; those stay behind approval gates. Stack-specific skills (React, Postgres and so on) apply only when the project uses that stack and its instructions do not name a different skill.

## Process skills

Test-driven development, systematic debugging, verification-before-completion and brainstorming are routed only when the user or the project instructions call for them. The default is to verify what the change needs: the relevant tests, a type-check, a render, a recomputation. Never impose a process skill on a clear fix, a configuration change or a lookup.

## Examples by capability

These are examples, not an allowlist. Check the installed skill catalog in the current session for the exact name before you name a skill. If no skill fits, the role can still do the work with its own tools.

<!-- @claude -->
| Capability | Example skills (Claude Code) | Boundary |
|---|---|---|
| Word documents | `anthropic-skills:docx` | render and check layout before handing over |
| PDF | `anthropic-skills:pdf` | reading, creating, forms; edit DOCX sources with the document skill |
| Presentations | `anthropic-skills:pptx`, `slides` | `slides` only if installed |
| Spreadsheets | `anthropic-skills:xlsx`, `spreadsheet` | `spreadsheet` only if installed |
| Google Docs, Sheets, Slides | `anthropic-skills:google-workspace` | creating or changing a file in the user's connected Google Drive only |
| Charts and data visualization | `dataviz` | if installed |
| Marketing and web copy | `copywriting` | if installed |
| New UI or a new visual direction | `frontend-design` | not for reviewing existing UI |
| UI review and accessibility | `web-design-guidelines` | reviewing existing UI code |
| Testing a local web app in a browser | `webapp-testing`, `agent-browser` | local or permitted sites only |
| React and Next.js | `vercel-react-best-practices`, `vercel-composition-patterns` | only for that stack |
| Postgres schema, SQL, migrations | `supabase-postgres-best-practices` | any Postgres, not only Supabase |
| Security review | `security-best-practices` | only when a security review is requested |
| Desktop app control | `anthropic-skills:computer-use` | only with granted screen and app access |
| Operating a website in a browser | `anthropic-skills:chrome-browser`, `anthropic-skills:built-in-browser` | read the matching skill before the first browser step; one agent per browser session |
| Multi-source research report | `anthropic-skills:deep-research` | it runs its own research subagents: use it instead of a research team, not inside one |
| Co-writing a document with the user | `doc-coauthoring` | if installed |
| Agent skills | `anthropic-skills:skill-creator` | reusable skills, not one-off documents |
| Claude Code Workflow scripts | `workflow-authoring` | writing a script does not authorize running one |
| Claude API and model facts | `claude-api` | |
| Process skills | `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:brainstorming` | only as described under Process skills |
| Bitmap image generation; packaging Claude Code plugins | no verified skill | ask the user or follow official documentation; `plugin-authoring` changes Claude's own interface and does not package plugins |

Agents that have the Skill tool load a skill by name. Read-only roles have a tool allowlist without the Skill tool: give them the path of the skill's SKILL.md to read, or put the few rules they need into the assignment.
<!-- @end -->
<!-- @codex -->
| Capability | Example skills (Codex) | Boundary |
|---|---|---|
| Word documents | `documents:documents` (plugin) | plugin skills appear only when the plugin is enabled; enabling it is the user's decision |
| PDF | `pdf` | reading, creating, forms; the `pdf:pdf` plugin may be disabled |
| Presentations | `presentations:Presentations` (plugin) | as for plugins above |
| Spreadsheet files | `spreadsheets:Spreadsheets` (plugin) | not for a live, open Excel workbook |
| A live Excel workbook | `spreadsheets:excel-live-control` (plugin) | only when the request names Excel Desktop or an open workbook |
| Google Docs, Sheets, Slides | `google-drive:google-docs`, `google-drive:google-sheets`, `google-drive:google-slides` | the user's connected account only |
| Interactive visualization in chat | `visualize:visualize` (plugin) | publication charts use standard plotting tools |
| Bitmap images | `imagegen` | not for SVG, icon sets or HTML and canvas graphics |
| New UI or a new visual direction | `frontend-design` | not for reviewing existing UI |
| UI review and accessibility | `web-design-guidelines` | reviewing existing UI code |
| Testing a local web app in a browser | `webapp-testing`, `agent-browser` | local or permitted sites only |
| React and Next.js | `vercel-react-best-practices`, `vercel-composition-patterns` | only for that stack |
| Postgres schema, SQL, migrations | `supabase-postgres-best-practices` | any Postgres, not only Supabase |
| Security review | `security-best-practices` | only when a security review is requested |
| Desktop app control | `computer-use:computer-use` | only with granted screen and app access |
| Co-writing a document with the user | `doc-coauthoring` | if installed |
| OpenAI and Codex product facts | `openai-docs` | not merely because an app mentions OpenAI |
| Agent skills | `skill-creator`; `skill-installer` to install one | install only on the user's request |
| Plugins | `plugin-management:plugin-management` | discovery, connection and removal on request; never assume uninstalled plugins or account access |
| Artifact templates | `template-creator:template-creator` (plugin) | reusable templates, not one-off artifacts |
| Sites | `sites:sites` | the site-owning agent ({{role:sites-builder}}) does checkout, Sites tools and handoff; subagents get only bounded assets or research; publishing is an approval gate |
| Process skills | `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:brainstorming` | only as described under Process skills |

Name the skill, and its path from the session's skill list, in the assignment; the spawned agent reads the skill itself.
<!-- @end -->
