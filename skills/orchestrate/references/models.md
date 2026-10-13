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

- **Delegation.** When the user invokes this skill directly (`$orchestrate`), they delegate the choice and later reassessment of each subagent's `model` and `reasoning_effort` to you; do not ask for approval of routine choices. Automatic selection of this skill is not that delegation: then set them only when the user or applicable higher-priority instructions allow it, and otherwise omit them. Explicit user pins, cost and usage limits and the current tool's restrictions still win. The delegation covers model and effort only, never a gated action such as a deployment or an external message.
- **`model` and `reasoning_effort`** on `spawn_agent` take only values from the tool's current model list and catalog. When tiers or successors are unclear and the choice matters, check current guidance with the `openai-docs` skill; if it stays unclear, use a model whose description is confirmed and say that you could not confirm it is the newest.
- **Omitting `model`** uses `[agents] default_subagent_model` (and `default_subagent_reasoning_effort`) when configured, otherwise the parent's model. Omission is therefore not always "inherit".
- **Role files:** a `model` set inside a registered role cannot be overridden at spawn time (the tool marks it "cannot be changed"). This kit's role files never set one; a project's own role might.
- **History:** follow the current spawn tool's schema. In the current v2 `collaboration.spawn_agent`, `fork_turns` accepts only `"none"` and `"all"`. With `"all"` or omission, the agent inherits the parent's model and reasoning effort; do not pass overrides. Use `"none"` with a self-contained assignment when setting supported `model` and `reasoning_effort` values. Use `"all"` only when the agent needs the whole parent conversation. v1 uses `fork_context` instead (v2 rejects it); it defaults to false, and v1 rejects `fork_context=true` together with `agent_type` because a full-history fork inherits the parent's agent type.
- **Peer messaging:** in v2 a child can message peers only when its model supports multi-agent v2. When an agent must exchange with peers directly, prefer such a model from the list, or plan to relay its messages yourself.
- `followup_task` and `send_input` are not model switches; they keep the agent's model.
- The optional codex-team launcher takes its models from its own configuration.
