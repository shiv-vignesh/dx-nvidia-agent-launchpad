# Judging — how we win each 25%

*Four criteria, 25% each. This maps every criterion to a concrete thing the judges will **see**, plus the one
sentence we say. The stack hands us local-first and policy "for free" — we just have to make them visible.*

| Criterion | What judges reward | What we show | The one line |
|---|---|---|---|
| **Technical execution** (25%) | It works, under the constraints, on the box | Live run against the synthetic **answer key** with a real number (precision/recall or time-to-root-cause); the agent loop + tool stream visible in the TUI | "Running entirely on the GB10 — here's the accuracy on 30 held-out cases." |
| **Business value** (25%) | A named owner feels the pain; the metric maps to money/time | Name the persona (AP manager / HPC ops lead / IT desk), state the before→after metric, tie it to GPU-hours or $ saved | "This saves an AP manager N hours/week and keeps financial docs in-building." |
| **Local-first design** (25%) | Provably local, not "cloud with extra steps" | `openshell term` showing inference routed only to `inference.local` → local vLLM; **no cloud egress**; `nemoclaw <n> status` proving the route | "The agent *physically can't* reach a cloud model — the gateway only routes to vLLM on this box." |
| **Demo quality** (25%) | Clear story, no dead air, a memorable beat | Scripted 2-min run **+ the "sandbox saves the day" moment** (injected exfil attempt denied live in `openshell term` while the agent still succeeds); recorded backup | "Watch what happens when a malicious input tries to exfiltrate — the cage stops it, live." |

## The hero moment (do not skip)

The single highest-leverage thing is the **visible policy denial**: feed the agent an input containing an injected
"upload this to pastebin / curl evil.sh" instruction, and show `openshell term` denying the egress **on screen**
while the agent still returns the correct result. It proves technical execution *and* local-first design *and*
demo quality in one beat. Pick a project idea that has this (all three in the runbook do).

## Assets we already have

- **The slide deck** (`docs-raw/Agent_Architecture_on_NVIDIA_NemoClaw.pptx`) — 18 clean architecture slides. Reuse
  the topology / host-vs-sandbox / responsibility-matrix slides directly in the pitch; they explain local-first fast.
- **The diagrams** in [onboarding/00](onboarding/00-agents-101.md)–[01](onboarding/01-stack-architecture.md) — screen-share one during the "how it works" beat.

## Scoring our own demo (rehearsal checklist)

- [ ] A real metric on the answer key (not a vibe)
- [ ] Persona + money/time statement said out loud
- [ ] `openshell term` on screen showing local-only routing
- [ ] The injected-exfil denial fires, agent still succeeds
- [ ] Two recorded runs as backup (venue Wi-Fi / model can misbehave)
- [ ] Under time: 2 min live + 30s pitch
