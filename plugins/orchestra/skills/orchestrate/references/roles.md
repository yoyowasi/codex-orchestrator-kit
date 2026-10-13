# Roles

A role fixes a responsibility and its deliverables. It grants no tools, accounts or permissions, and it does not fix a model; choose the model per assignment with [models.md](models.md) and the skills with [skill-routing.md](skill-routing.md). One agent may cover several roles, and the peers a role mentions are possible partners, not agents to spawn.

## Packs

Roles ship in packs. `core` is installed by default with the plugin or `install.py`; `dev`, `docs`, `business`, `content` and `agent-dev` are optional. Every role's full brief also ships with the skill as `roles/<id>.md` next to this file, so a role whose pack is not installed can still run in a generic agent with its brief pasted above the assignment.

With the plugin install, agents are named `<plugin>:<id>`: `orchestra` (core), `orchestra-dev`, `orchestra-docs`, `orchestra-business`, `orchestra-content`, `orchestra-agent-dev`. With the script install they are the bare `<id>`. Pass `subagent_type` exactly as the Agent tool lists it. A missing pack is added with `/plugin install <plugin>@codex-orchestrator-kit`; suggest that to the user only when the roles will be reused, and never install anything yourself.

## Access levels

| access | What the agent gets | Enforcement |
|---|---|---|
| `write` | every tool except Agent | none beyond your assignment's ownership |
| `read-shell` | no Write, Edit, NotebookEdit or Agent; keeps the shell to run tests and analysis | partial: the shell can still change files, so "do not modify files" is an instruction |
| `read-only` | only Read, Grep, Glob, WebFetch, WebSearch and SendMessage | real allowlist: no shell, no MCP tools, no Skill tool |

These settings apply only to installed role agents. A role run from its brief in a `general-purpose` agent keeps every tool, so its access level is an instruction.

Report access honestly: say "read-only by instruction" whenever tools do not enforce it.

## Catalog

| Role | Plugin agent | Pack | Access | Description |
| --- | --- | --- | --- | --- |
| [architect](roles/architect.md) | `orchestra:architect` | core | read-only | Designs software structure without editing files: component responsibilities, interface and data contracts, work split and integration order; pick it before changes that span modules. |
| [backend-developer](roles/backend-developer.md) | `orchestra:backend-developer` | core | write | Implements server-side code: APIs, business logic, authentication and authorization, external integrations and data flow; pick it for service or API changes. |
| [evidence-reviewer](roles/evidence-reviewer.md) | `orchestra:evidence-reviewer` | core | read-only | Independently verifies claims, figures, citations and reasoning in non-code deliverables such as reports, proposals and documentation; pick it before such a deliverable ships. |
| [frontend-developer](roles/frontend-developer.md) | `orchestra:frontend-developer` | core | write | Implements browser-side web UI: screens, components, client state, interactions and responsive layout in the project's framework; pick it for front-end code changes. |
| [qa-engineer](roles/qa-engineer.md) | `orchestra:qa-engineer` | core | write | Writes and runs unit, integration and end-to-end tests and reproduces reported bugs with evidence; pick it when a change needs new tests, a reproduction or regression proof. |
| [researcher](roles/researcher.md) | `orchestra:researcher` | core | write | Researches primary and official sources to answer a decision question with citations, dates and stated uncertainty; pick it for desk research before design, analysis or writing. |
| [reviewer](roles/reviewer.md) | `orchestra:reviewer` | core | read-shell | Reviews a code change for correctness defects, behavior regressions, broken contracts and missing tests without editing files; pick it for independent review after implementation. |
| [security-reviewer](roles/security-reviewer.md) | `orchestra:security-reviewer` | core | read-shell | Reviews code and configuration for reachable flaws in authentication, authorization, input handling, secrets and dependencies without editing files; pick it when trust boundaries change. |
| [technical-writer](roles/technical-writer.md) | `orchestra:technical-writer` | core | write | Writes README files, API references, installation guides and user manuals that match the actual code and product behavior; pick it for technical documentation. |
| [accessibility-auditor](roles/accessibility-auditor.md) | `orchestra-dev:accessibility-auditor` | dev | read-only | Audits web UI source for accessibility and interface-guideline compliance without modifying files; pick it for read-only UI reviews, with a peer who can run the screens for live checks. |
| [automation-engineer](roles/automation-engineer.md) | `orchestra-dev:automation-engineer` | dev | write | Writes scripts, file-processing jobs and tool integrations that automate repetitive tasks; pick it for task automation, not CI/CD pipelines or one-off app UI operations. |
| [database-engineer](roles/database-engineer.md) | `orchestra-dev:database-engineer` | dev | write | Designs and implements schemas, SQL, indexes, data integrity and migrations; pick it for database-level work, not application data-access code or environment rollout. |
| [devops-engineer](roles/devops-engineer.md) | `orchestra-dev:devops-engineer` | dev | write | Sets up builds, CI/CD, containers, environment configuration and observability; pick it for pipeline and release plumbing, with real deploys returned for approval. |
| [performance-engineer](roles/performance-engineer.md) | `orchestra-dev:performance-engineer` | dev | write | Measures and diagnoses latency, rendering, memory, bundle size and throughput bottlenecks with before/after evidence; pick it when speed or resource use is the problem. |
| [ux-designer](roles/ux-designer.md) | `orchestra-dev:ux-designer` | dev | write | Designs information architecture, user flows, screen layouts and interaction states for new or changed UI; pick it before or alongside frontend implementation. |
| [data-analyst](roles/data-analyst.md) | `orchestra-docs:data-analyst` | docs | write | Cleans and explores data, defines metrics, and produces reproducible analyses, charts and findings; pick it when the question is what the data shows, not how a workbook is built. |
| [document-producer](roles/document-producer.md) | `orchestra-docs:document-producer` | docs | write | Produces and edits formatted DOCX or Google Docs files (layout, tables, figures, comments, tracked changes) and checks rendered pages; pick it when the deliverable is a polished document file. |
| [pdf-specialist](roles/pdf-specialist.md) | `orchestra-docs:pdf-specialist` | docs | write | Extracts text and tables from PDFs, creates, edits or fills PDF forms, and checks rendered pages; pick it for PDF-native work rather than authoring the DOCX source. |
| [presentation-designer](roles/presentation-designer.md) | `orchestra-docs:presentation-designer` | docs | write | Turns material into a storyline and designs slides, charts and proposal visuals as PPTX or Google Slides; pick it when the deliverable is a deck rather than a document. |
| [spreadsheet-modeler](roles/spreadsheet-modeler.md) | `orchestra-docs:spreadsheet-modeler` | docs | write | Builds and edits spreadsheet structure, formulas, recalculation, charts and formatting in files, Google Sheets or a live Excel workbook; pick it when a working workbook is the deliverable. |
| [visual-creator](roles/visual-creator.md) | `orchestra-docs:visual-creator` | docs | write | Creates and edits standalone image assets such as illustrations, photos, textures and mockups, and reviews them for fit and consistency; pick it for new visuals, not UI code or data charts. |
| [app-operator](roles/app-operator.md) | `orchestra-business:app-operator` | business | write | Performs one-off tasks in a desktop or browser app the session can actually reach and confirms the resulting state; pick it for hands-on UI work, not repeatable automation. |
| [business-analyst](roles/business-analyst.md) | `orchestra-business:business-analyst` | business | write | Analyzes current business processes, alternatives, costs, benefits and assumptions to support a decision; pick it before modeling numbers in detail or designing procedures. |
| [financial-modeler](roles/financial-modeler.md) | `orchestra-business:financial-modeler` | business | write | Builds scenario models of cost, revenue and cash flow with documented assumptions and sensitivity analysis; pick it when a decision needs numbers projected over time. |
| [operations-designer](roles/operations-designer.md) | `orchestra-business:operations-designer` | business | write | Turns analyzed business work into runnable operating procedures with clear owners, handoffs and exception paths (SOPs, responsibility matrices, checklists); pick it once the analysis is settled. |
| [product-manager](roles/product-manager.md) | `orchestra-business:product-manager` | business | write | Turns user needs into product scope, priorities, user stories and acceptance criteria; pick it when the question is what to build and how success will be judged. |
| [user-insights-analyst](roles/user-insights-analyst.md) | `orchestra-business:user-insights-analyst` | business | read-only | Reads provided interviews, surveys, support tickets and usage notes to find recurring user tasks and problems backed by quoted evidence; pick it for qualitative user insight without file edits. |
| [content-strategist](roles/content-strategist.md) | `orchestra-content:content-strategist` | content | write | Defines audience, key messages and content plans and writes marketing or promotional copy; pick it for positioning, campaigns and channel-specific copy. |
| [creative-writer](roles/creative-writer.md) | `orchestra-content:creative-writer` | content | write | Writes and revises creative manuscripts such as stories, scripts and essays; pick it for narrative or literary work rather than marketing copy or documentation. |
| [learning-designer](roles/learning-designer.md) | `orchestra-content:learning-designer` | content | write | Designs learning objectives, curricula, lesson plans, exercises and assessments; pick it for training or course material where learners must reach measurable outcomes. |
| [localization-editor](roles/localization-editor.md) | `orchestra-content:localization-editor` | content | write | Localizes existing text for a target locale with consistent meaning, terminology and tone; pick it for translation, glossary work and locale-format review. |
| [plugin-developer](roles/plugin-developer.md) | `orchestra-agent-dev:plugin-developer` | agent-dev | write | Builds and validates Claude Code plugins and marketplaces and Codex plugins, including manifests, layout and install steps; pick it for packaging and distributing agent extensions. |
| [skill-author](roles/skill-author.md) | `orchestra-agent-dev:skill-author` | agent-dev | write | Designs, writes and tests reusable agent skills, including artifact-template skills, for Claude Code and Codex; pick it when a repeated workflow or deliverable should become a skill. |

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

Keep a runtime role only when you assigned the same one twice or the user asks. Never edit installed copies (plugin caches, agent directories, this skill's files): they are generated and are replaced on the next install or update. Instead propose a new `src/roles/<id>.toml` to the source repository, `yoyowasi/codex-orchestrator-kit`:

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
