from app.domain.models import Evidence, ExtractedHandoff, Flag, ShiftRecord


class MedDueNotMentioned:
    """Flag any med that is due this shift but absent from the handoff."""

    def check(self, handoff: ExtractedHandoff, records: ShiftRecord) -> list[Flag]:
        mentioned = {m.lower() for m in handoff.mentioned_meds}
        flags: list[Flag] = []
        for med in records.meds:
            if med.due_at is not None and med.name.lower() not in mentioned:
                flags.append(
                    Flag(
                        kind="med_due_not_mentioned",
                        message=f"{med.name} is due but was not mentioned in the handoff.",
                        evidence=Evidence(
                            ref=f"{records.patient_id}/med/{med.name}",
                            source="records",
                            detail=f"due_at={med.due_at.isoformat()}",
                        ),
                    )
                )
        return flags
