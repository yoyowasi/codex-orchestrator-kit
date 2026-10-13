# Model policy

Choose the model and effort for each assignment separately from its role. A role names a responsibility; the model and effort follow the difficulty of this particular piece of work.

## Tiers

Build the candidates for each tier from what the spawn tool offers right now: its model list, descriptions and effort values. Do not add models known only from documentation, memory or another tool, and never guess a model ID or an effort value.

| Tier | Fits | Effort |
|---|---|---|
| Light | narrow work that is easy to check: extraction, classification, summaries, format checks | the lowest level that is sufficient |
| General | routine implementation, documents and slides, research synthesis, data processing, process design | the default or a medium level |
| Frontier | complex architecture, conflicting evidence, defects without a known cause, high-impact verification | high levels |

Within a tier prefer the currently recommended, newest successor. Pick an older generation only for a stated reason: a user pin, reproducibility, compatibility, or measured cost, latency or usage limits. Do not infer capability, tier or price from a version number or a familiar name. A team does not need all three tiers, and mixing generations across tiers is fine.

## Selection

1. Decide by the work's uncertainty, failure impact, verifiability, and speed and cost needs, not by the role title. A researcher extracting tables can run on a light model; one reconciling conflicting sources needs a frontier model.
2. Start from the lightest combination that meets the quality bar.
3. User pins win. "Only this model", "do not change it", and stated quality, cost or usage limits are hard constraints. A model the user merely mentions is a preference: you may choose differently, with a one-line reason, and without asking for approval of routine choices.
4. If a pinned model is unavailable, hold that assignment, tell the user which supported models exist, and continue independent work.
5. Model diversity is not a goal. Different models that share the same wrong input do not verify each other; recompute, check the source or reproduce instead.
6. Use only models and providers the runtime already supports. Never install accounts, keys or services to diversify models. Image and audio generation tools are chosen separately from reasoning models.
7. Keep the main session's model. Change it only when the user asks, and only through a method that actually exists.

## Reassessment between stages

Reassess the next assignment when a stage ends or new evidence appears, not after every small edit.

- Unexpected complexity, repeated quality problems or conflicting key evidence: hand the work, with the failure evidence, to a stronger model or a higher effort.
- Structure and cause settled, and only checkable edits left: a lighter model can take the follow-up.
- Latency or usage pressure: keep strong models for the decisive judgments and lighten independent routine work. Do not claim prices or savings you have not measured.
- Give each change one sentence with the actual model, for example "frontier model to reconcile conflicting figures across sources". Keep a choice that still fits.

## Handoff on model change

Do not stop running work only to switch models. When work moves to another model, hand over the latest artifact and its version, the verification results, the failure evidence and the open issues, and record the change in the final report table. Resuming or following up an existing agent keeps its model; a different model needs a new agent.

## Never claim what was not applied

Report the model and effort you actually passed to the spawn tool. If you could not set them (no parameter, a role file or environment setting pins them, the value was rejected), say so. Writing a model name into the prompt sets nothing.

## Setting model and effort

- **`model`** on the Agent tool takes an alias the tool's schema lists, such as `haiku`, `sonnet`, `opus` or `fable` (a full model ID only where the schema accepts one). A usual mapping is `haiku` light, `sonnet` general, `opus` frontier; place any other alias by the description the tool or model picker gives, and let the current schema win over this list.
- **Order:** the `model` you pass wins, then the agent definition's `model`, then `CLAUDE_CODE_SUBAGENT_MODEL`, then the main session's model (inherit). This kit's roles set no model. With `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` every subagent runs on `CLAUDE_CODE_SUBAGENT_MODEL`, or on the main session's model when that is unset, and the `model` you pass is ignored; if it is active, report that you could not choose.
- **`effort`** takes the levels the schema lists (`low` to `max`) and needs Claude Code v2.1.292 or later; `CLAUDE_CODE_EFFORT_LEVEL` overrides it. Omit it to use the default. If the Agent tool offers no `effort` parameter, report effort as not applied.
- A fork inherits the main conversation, prompt and model, so never use one for a model assignment.
- This kit's Workflow scripts set no model per stage; each stage runs on the main session's model unless `CLAUDE_CODE_SUBAGENT_MODEL` is set. Report them that way.
- For current facts about Claude models, read the Agent tool schema and, if installed, the `claude-api` skill.
