from datetime import datetime

from app.domain.models import Med, ShiftRecord, ExtractedHandoff, Vital
from app.domain.rules.med_due import MedDueNotMentioned
from app.domain.rules.abnormal_vital import AbnormalVitalOmitted
from app.domain.engine import FlaggingEngine


def test_med_due_not_mentioned_is_flagged():
    records = ShiftRecord(
        patient_id="P1",
        meds=[Med(name="insulin", due_at=datetime(2026, 10, 3, 18, 0))],
    )
    handoff = ExtractedHandoff(mentioned_meds=[])

    flags = MedDueNotMentioned().check(handoff, records)

    assert len(flags) == 1
    assert flags[0].kind == "med_due_not_mentioned"
    assert "insulin" in flags[0].message.lower()
    assert flags[0].evidence.ref == "P1/med/insulin"


def test_med_mentioned_is_not_flagged():
    records = ShiftRecord(
        patient_id="P1",
        meds=[Med(name="insulin", due_at=datetime(2026, 10, 3, 18, 0))],
    )
    flags = MedDueNotMentioned().check(
        ExtractedHandoff(mentioned_meds=["insulin"]), records
    )
    assert flags == []


def test_abnormal_vital_omitted_is_flagged():
    records = ShiftRecord(
        patient_id="P1",
        vitals=[Vital(name="SpO2", value=88, is_abnormal=True)],
    )
    flags = AbnormalVitalOmitted().check(ExtractedHandoff(mentioned_vitals=[]), records)

    assert len(flags) == 1
    assert flags[0].kind == "abnormal_vital_omitted"
    assert flags[0].severity == "critical"
    assert flags[0].evidence.ref == "P1/vital/SpO2"


def test_normal_vital_is_not_flagged():
    records = ShiftRecord(
        patient_id="P1",
        vitals=[Vital(name="HR", value=72, is_abnormal=False)],
    )
    flags = AbnormalVitalOmitted().check(ExtractedHandoff(), records)
    assert flags == []


def test_engine_runs_all_rules_and_aggregates():
    records = ShiftRecord(
        patient_id="P1",
        meds=[Med(name="insulin", due_at=datetime(2026, 10, 3, 18, 0))],
        vitals=[Vital(name="SpO2", value=88, is_abnormal=True)],
    )
    handoff = ExtractedHandoff()  # outgoing nurse mentioned neither

    flags = FlaggingEngine().run(handoff, records)

    kinds = {f.kind for f in flags}
    assert kinds == {"med_due_not_mentioned", "abnormal_vital_omitted"}


def test_engine_clean_handoff_produces_no_flags():
    records = ShiftRecord(
        patient_id="P1",
        meds=[Med(name="insulin", due_at=datetime(2026, 10, 3, 18, 0))],
        vitals=[Vital(name="SpO2", value=88, is_abnormal=True)],
    )
    handoff = ExtractedHandoff(mentioned_meds=["insulin"], mentioned_vitals=["SpO2"])

    assert FlaggingEngine().run(handoff, records) == []
