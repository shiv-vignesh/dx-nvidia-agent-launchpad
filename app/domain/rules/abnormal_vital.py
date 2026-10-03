from app.domain.models import Evidence, ExtractedHandoff, Flag, ShiftRecord


class AbnormalVitalOmitted:
    """Flag any abnormal vital that the handoff failed to mention (clinically critical)."""

    def check(self, handoff: ExtractedHandoff, records: ShiftRecord) -> list[Flag]:
        mentioned = {v.lower() for v in handoff.mentioned_vitals}
        flags: list[Flag] = []
        for vital in records.vitals:
            if vital.is_abnormal and vital.name.lower() not in mentioned:
                flags.append(
                    Flag(
                        kind="abnormal_vital_omitted",
                        severity="critical",
                        message=f"Abnormal {vital.name} ({vital.value}) was not mentioned in the handoff.",
                        evidence=Evidence(
                            ref=f"{records.patient_id}/vital/{vital.name}",
                            source="records",
                            detail=f"{vital.name}={vital.value} (abnormal)",
                        ),
                    )
                )
        return flags
