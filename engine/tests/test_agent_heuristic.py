from datetime import datetime

from app.domain.models import Med, Vital, ShiftRecord
from app.adapters.agent_heuristic import HeuristicAgent


def test_heuristic_detects_mentions_by_name_match():
    records = ShiftRecord(
        patient_id="P1",
        meds=[Med(name="insulin", due_at=datetime(2026, 10, 3, 18, 0)),
              Med(name="heparin", due_at=datetime(2026, 10, 3, 20, 0))],
        vitals=[Vital(name="SpO2", value=88, is_abnormal=True)],
    )

    e = HeuristicAgent().extract("Gave Heparin around 2000. SpO2 looked fine.", records)

    assert "heparin" in [m.lower() for m in e.mentioned_meds]
    assert "insulin" not in [m.lower() for m in e.mentioned_meds]
    assert "spo2" in [v.lower() for v in e.mentioned_vitals]
