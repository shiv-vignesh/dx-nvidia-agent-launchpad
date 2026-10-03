# Frontend verification and integration notes

This frontend was developed from the five CareChart screen designs. It is a standalone
React/Vite prototype alongside the repository's ShiftGuard Python app.

## Validation

- Production build: `npm run build`.
- Handoff, speech, and coverage tests: `npm test` (13 tests).
- Static worker tests: `npm run test:sites` (4 tests, after build).
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
- Live microphone transcription uses browser SpeechRecognition after consent. Audio is not stored; the browser may use an external speech service.
- Delivery and questions are local demo state, not network requests.
- Browser speech synthesis reads report text; it is not captured microphone audio.
- No connection has been added to `app/application/handoff_service.py` or an inference endpoint.
- The existing Python application, configuration, and deployment scripts are unchanged.

The team can replace the fixture/state boundary with an API adapter after agreeing on
patient, report, evidence, and acknowledgement contracts. Fonts and image assets ship locally. Browser speech recognition may require a network service.

## Live transcription update
Browser SpeechRecognition now streams interim text and saves finalized text per patient. Thirteen unit tests pass, including result deduplication, final results after stopping, and permission failure handling. Build passes. Consent controls and rendering checked in the local browser with no console errors. The user confirmed live transcription works; service availability depends on the browser. Audio is not stored and browser recognition may use an external service. Backend chart comparison remains unconnected. Bed 7 uses labelled prototype phrase matching with evidence, provisional results, and patient-mismatch handling. Nurse sessions are separated through demo sign-in; this is not real authentication.
