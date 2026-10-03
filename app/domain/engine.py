"""FlaggingEngine — runs a list of deterministic rules over (handoff, records) and
aggregates their Flags. Rules follow a simple Strategy protocol: a `.check(handoff, records)`
returning list[Flag]. New rule = new class in rules/, added to DEFAULT_RULES."""
from __future__ import annotations

from typing import Protocol

from app.domain.models import ExtractedHandoff, Flag, ShiftRecord
from app.domain.rules.abnormal_vital import AbnormalVitalOmitted
from app.domain.rules.med_due import MedDueNotMentioned


class Rule(Protocol):
    def check(self, handoff: ExtractedHandoff, records: ShiftRecord) -> list[Flag]: ...


DEFAULT_RULES: list[Rule] = [MedDueNotMentioned(), AbnormalVitalOmitted()]


class FlaggingEngine:
    def __init__(self, rules: list[Rule] | None = None) -> None:
        self.rules = rules if rules is not None else DEFAULT_RULES

    def run(self, handoff: ExtractedHandoff, records: ShiftRecord) -> list[Flag]:
        flags: list[Flag] = []
        for rule in self.rules:
            flags.extend(rule.check(handoff, records))
        return flags
