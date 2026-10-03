"""HeuristicAgent — a no-model AgentPort: case-insensitive name matching of on-record
meds/vitals against the handoff text. Lets the full app run end-to-end with zero inference
(instant, offline). The real model (OpenAIAgent → Ollama/vLLM) swaps in behind the same
interface; this is the demo-safe floor / fallback."""
from __future__ import annotations

from app.domain.models import ExtractedHandoff, ShiftRecord


class HeuristicAgent:
    def extract(self, handoff_text: str, records: ShiftRecord) -> ExtractedHandoff:
        text = handoff_text.lower()
        return ExtractedHandoff(
            mentioned_meds=[m.name for m in records.meds if m.name.lower() in text],
            mentioned_vitals=[v.name for v in records.vitals if v.name.lower() in text],
        )
