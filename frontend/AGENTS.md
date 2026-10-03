# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

Recording must transcribe actual microphone speech where supported, with visible interim text and patient-specific saved final text. Do not substitute timer-driven sample text or claim automatic clinical coverage. Provide clear consent for browser speech services and unsupported/permission-denied states.

Outgoing and incoming nurses must use separate sign-in sessions. No perspective switch or incoming acknowledgement controls in the outgoing workspace. Outgoing signs/sends, logs out, then incoming signs in to acknowledge from her dashboard. Signed outgoing handoffs are read-only.

Live coverage may use clearly labelled prototype phrase matching against the selected patient’s sample chart. Show evidence and provisional vs finalized matches; never imply clinical verification or silently switch patients.
