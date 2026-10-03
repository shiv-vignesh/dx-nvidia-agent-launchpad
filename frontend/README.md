# CareChart frontend

A responsive React + Vite implementation of the five supplied nurse-handoff screens. The screens are native components, not screenshot overlays.

## Run

Use Node 22.12+ (or 20.19+) and npm.

```sh
npm ci
npm run dev -- --host 127.0.0.1 --port 4173
```

Open http://127.0.0.1:4173. `npm run build` creates the production build. `npm test` runs handoff-state tests. `npm run format` formats source files.

## Try the flow

1. Select Bed 7 and choose **Start verbal report**.
2. **Start recording** uses browser speech recognition after sample-only consent and microphone permission. Interim words appear live; finalized text is saved per patient. Pause/resume or stop to edit the transcript. Unsupported browsers and denied permission show an actionable message; typed reports remain available.
3. **Stop and review** opens the report. Add, dismiss, or undo suggestions; inspect source records; edit notes or add an addendum.
4. **Deliver report to M. Chen** shows a reviewable confirmation. Delivery updates patient and assignment status.
5. **View as incoming nurse** opens the received report. Play sample narration, review items, save a clarification question, and acknowledge receipt. Open clinical follow-up tasks remain open.
6. Use **Log out**, then select the other nurse account and **Sign in**. Outgoing nurses sign and send; incoming nurses acknowledge from their separate dashboard. No in-session role switching. Sign-in is a local prototype, not real authentication. **Reset demo** restores sample reports.

Search, sorting, status filters, patient switching, overview, chart tabs, worklist, notes, modal focus management, empty states, toast feedback, and logout/demo re-entry work. Draft state is stored locally under `carechart-demo-v1`. Browser speech recognition may send audio to the browser vendor’s speech service. Use fictional speech only. Audio is not saved by this app.

## Scope

This is a frontend prototype, not a connected EHR. Browser-based live transcription is supported where SpeechRecognition is available. Automated chart comparison, identity/authentication, clinical task completion, messaging, and real delivery remain unconnected. Playback synthesizes the transcript; it is not a saved microphone recording. Times, connection state, and chart data are demo fixtures. Do not enter real patient data into this demo.

The supplied designs contain detailed data for Bed 7. Other patients support selection and handoff state without reusing Bed 7's clinical detail. The two below-the-fold review suggestions are illustrative demo content; exact source designs for them were not supplied. Source portrait and waveforms were extracted from the supplied SVGs, with local Inter fonts and Phosphor icons.

## Design and motion

The reference layout uses a 1440 × 1000 viewport, a 340 px patient rail, persistent identity, chart navigation, scrollable content, and anchored action/status bars. On smaller screens, the patient rail becomes horizontally scrollable and recording columns stack. Motion uses short transitions, waveform breathing, recording pulses, transcript entry, modal entry, progress feedback, and toast transitions. `prefers-reduced-motion` disables animations and smooth scrolling.

Reference-state preview URLs (these intentionally initialize a fresh fixture on load):
- `/?screen=home`
- `/?screen=prepare`
- `/?screen=recording`
- `/?screen=review`
- `/?screen=incoming`

Use `/` for the normal stateful flow. Clinical status and workflow state are deliberately separate: reviewing and acknowledging never complete clinical tasks. Counts are derived from state; the incoming fixture correctly shows 4 total reports received, 1 acknowledged, and 3 awaiting acknowledgement.

## Files

- `src/App.jsx`: connected screens and frontend state transitions
- `src/components.jsx`: shared controls, tabs, modal, narration player
- `src/model.js`: fixtures and handoff-state helpers
- `src/styles.css`: design tokens, layouts, responsive behavior, motion
- `tests/handoff.test.mjs`: isolation, transfer, counts, and acknowledgement tests
- `docs/verification.md`: verification summary and integration boundaries

### Live sample chart coverage
Bed 7 has seven sample chart items matched against its own live transcript. Provisional speech shows “Hearing…”; finalized phrase matches show “Mentioned” with evidence. Missing details or negation show “Needs clarification”. Explicit different-bed references block matching. These deterministic rules are not clinical inference and can miss paraphrases or ambiguity. Other beds show that detailed chart data is unavailable. Coverage remains visible during review and recalculates after transcript corrections.
