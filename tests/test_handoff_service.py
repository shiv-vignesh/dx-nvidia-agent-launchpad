from datetime import datetime

from app.domain.models import Med, Vital, ShiftRecord, ExtractedHandoff
from app.application.handoff_service import HandoffService


class FakeAgent:
    """Stand-in AgentPort: returns a pre-set extraction, no model/network."""

    def __init__(self, extracted: ExtractedHandoff):
        self._extracted = extracted

    def extract(self, handoff_text: str, records: ShiftRecord) -> ExtractedHandoff:
        return self._extracted


def _records():
    return ShiftRecord(
        patient_id="P1",
        meds=[Med(name="insulin", due_at=datetime(2026, 10, 3, 18, 0))],
        vitals=[Vital(name="SpO2", value=88, is_abnormal=True)],
    )


def test_service_flags_omissions_from_agent_extraction():
    # agent determines the outgoing nurse mentioned neither the med nor the vital
    agent = FakeAgent(ExtractedHandoff(mentioned_meds=[], mentioned_vitals=[]))

    flags = HandoffService(agent=agent).analyze("patient stable overnight", _records())

    kinds = {f.kind for f in flags}
    assert kinds == {"med_due_not_mentioned", "abnormal_vital_omitted"}
    # invariant: every flag cites a concrete record
    assert all(f.evidence.ref for f in flags)


def test_service_clean_handoff_no_flags():
    agent = FakeAgent(ExtractedHandoff(mentioned_meds=["insulin"], mentioned_vitals=["SpO2"]))

    flags = HandoffService(agent=agent).analyze("insulin given, SpO2 88 on 2L", _records())

    assert flags == []
