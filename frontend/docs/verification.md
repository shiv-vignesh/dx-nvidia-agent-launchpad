# Frontend verification and integration notes

This frontend was developed from the five CareChart screen designs. It is a standalone
React/Vite prototype alongside the repository's ShiftGuard Python app.

## Validation

- Production build: `npm run build`.
- Handoff state tests: `npm test` (5 tests).
- Static worker tests: `npm run test:sites`.
- The original local frontend was browser-checked at 1440 × 1000, 1024 × 768, and 390 × 844.
- Browser-checked flow: prepare → recording → pause/resume → review → save/resume → deliver
  → incoming review → acknowledge. Added/dismissed suggestions, undo, source modals,
  search, patient switching, sample narration, keyboard tabs, Escape, and focus restoration
  were also checked. Clinical tasks remain open after acknowledgement.

## Integration boundaries

- `src/model.js` owns the sample patient and chart data and state helpers.
- `src/App.jsx` owns local draft, report, delivery, and acknowledgement state.
- `src/components.jsx` contains shared controls and browser narration.
- Local storage key: `carechart-demo-v1`. Store no real patient data in this prototype.
- Recording and live transcription are simulated. No microphone capture is implemented.
- Delivery and questions are local demo state, not network requests.
- Browser speech synthesis reads the sample transcript; it is not captured report audio.
- No connection has been added to `engine/app/application/handoff_service.py` or an inference endpoint.
- The existing Python application, configuration, and deployment scripts are unchanged.

The team can replace the fixture/state boundary with an API adapter after agreeing on
patient, report, evidence, and acknowledgement contracts. No cloud service is required
for the current UI; fonts and image assets ship locally.
