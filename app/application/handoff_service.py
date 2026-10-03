"""HandoffService — the core use case: extract claims from the narrative (via the agent),
then run the deterministic flagging engine against the shift records."""
from __future__ import annotations

from app.application.ports import AgentPort
from app.domain.engine import FlaggingEngine
from app.domain.models import Flag, ShiftRecord


class HandoffService:
    def __init__(self, agent: AgentPort, engine: FlaggingEngine | None = None) -> None:
        self.agent = agent
        self.engine = engine or FlaggingEngine()

    def analyze(self, handoff_text: str, records: ShiftRecord) -> list[Flag]:
        extracted = self.agent.extract(handoff_text, records)
        return self.engine.run(extracted, records)
