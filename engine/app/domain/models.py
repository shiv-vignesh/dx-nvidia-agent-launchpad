"""Pure domain models — no I/O, no stack imports. The agent/adapters produce ExtractedHandoff;
the rules engine compares it against ShiftRecord and emits Flags with Evidence."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Med(BaseModel):
    name: str
    due_at: datetime | None = None


class Vital(BaseModel):
    name: str
    value: float
    is_abnormal: bool = False


class ShiftRecord(BaseModel):
    patient_id: str
    meds: list[Med] = Field(default_factory=list)
    vitals: list[Vital] = Field(default_factory=list)


class ExtractedHandoff(BaseModel):
    """What the agent extracts from the outgoing nurse's narrative handoff."""
    mentioned_meds: list[str] = Field(default_factory=list)
    mentioned_vitals: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    ref: str                 # stable pointer, e.g. "P1/med/insulin"
    source: str = ""         # "records" | "handoff"
    detail: str = ""


class Flag(BaseModel):
    kind: str                # machine key, e.g. "med_due_not_mentioned"
    message: str             # human-readable
    evidence: Evidence       # every flag MUST cite a concrete record (invariant)
    severity: str = "info"   # info | warning | critical
