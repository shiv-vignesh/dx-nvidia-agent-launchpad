# agent/ — built on the day

**Intentionally empty of logic.** Hackathon rules: plans, scaffolds, and libraries are allowed beforehand, but
**the agent itself must be built on Saturday.** So this folder holds only notes and ideas tonight — no tools, no
prompts, no agent code. We write that live.

## What goes here tomorrow

The agent is **OpenClaw config + tools + skills**, not a from-scratch program. Expect:

- `openclaw.json` tweaks (model ref is already `inference.local`; add tool/skill config)
- 3–4 tool definitions (exec / read_file / write_file / web_fetch are built in — mostly we *describe* and *enable*)
- maybe one skill (a procedure + prompt snippet)
- the demo dataset lives in `/sandbox` (uploaded), not in git

## Decide BEFORE creating the sandbox (can't change live)

- **Which files the agent needs** — filesystem scope locks at sandbox creation (Landlock). Put demo data under `/sandbox`.
- **Which project** — see the three ideas in [../docs/onboarding/03-day-of-runbook.md](../docs/onboarding/03-day-of-runbook.md).
- **Which model** — [../configs/models.md](../configs/models.md).

Network policy and model choice *can* change mid-demo; filesystem and process can't.

## Design notes / ideas (fill in tonight)

- **Project pick:** _TBD (lean: invoice↔PO reconciliation or GPU-job triage — both have a clean "sandbox saves the day" beat)_
- **Tools (keep to 3–4):** _TBD_
- **Answer key / metric:** _TBD — build it in hour 1_
- **Hero demo moment:** injected exfil attempt denied live in `openshell term` while the agent still succeeds
- **Tool-output discipline:** return summaries, not 4,000 rows — agent loops are prefill-heavy (see [00](../docs/onboarding/00-agents-101.md))

## Guardrails for tomorrow

- Keep tools few and descriptions tight — fewer tools = better tool selection.
- Truncate/summarize tool outputs; rely on compaction.
- Don't point the agent at `/v1/responses` (skips the tool parser).
- Prove local-first on screen (`openshell term` → inference routed only to `inference.local`).
