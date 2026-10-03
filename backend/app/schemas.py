"""Typed schemas for the patient and staff registry.

Every clinical record in this backend hangs off two identifiers:

    PATIENT_ID   P-###     e.g. P-101    — the subject of care
    STAFF_ID     X-##      e.g. N-02     — the person acting
                 where X is the role: N nurse (RN), A aide,
                 C charge nurse, D provider (doctor)

Those two are the only keys that cross module boundaries. Everything else
(vitals, meds, labs, tasks, handoffs, messages, notes) carries one or both,
so any record can be traced to a patient and to whoever touched it.
"""
import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator

PATIENT_ID = re.compile(r"^P-\d{3}$")
STAFF_ID = re.compile(r"^[NACD]-\d{2}$")
ROLE_PREFIX = {"nurse": "N", "aide": "A", "charge": "C", "provider": "D"}

Role = Literal["nurse", "aide", "charge", "provider"]
Shift = Literal["day", "night"]


def check_patient_id(v: str) -> str:
    if not PATIENT_ID.match(v):
        raise ValueError(f"patient id must look like P-101, got '{v}'")
    return v


def check_staff_id(v: str) -> str:
    if not STAFF_ID.match(v):
        raise ValueError(f"staff id must look like N-02 (N/A/C/D + 2 digits), got '{v}'")
    return v


# --------------------------------------------------------------------- patients

class PatientIn(BaseModel):
    """A patient to admit to the synthetic ward."""
    id: str = Field(examples=["P-204"], description="P-### — unique, never reused")
    name: str = Field(examples=["Alma Whitfield"])
    room: str = Field(examples=["412-A"])
    age: int = Field(ge=0, le=120, examples=[78])
    dx: str = Field(description="Working diagnosis", examples=["CHF exacerbation"])
    code_status: str = Field("Full code", examples=["DNR"])
    allergies: str = Field("none known", examples=["penicillin, shellfish"])
    isolation: str = Field("none", examples=["contact"])
    restraints: str = Field("none")
    fall_score: int = Field(0, ge=0, le=125, description="Morse scale; 13+ is high risk")
    fall_interventions: str = Field("standard precautions")
    language: str = Field("English", description="Preferred language for family summaries")
    mrn: str | None = Field(None, examples=["MRN-77-00412"], description="Medical record number")
    sex: str | None = Field(None, examples=["F"])
    unit: str | None = Field("4 West")
    bed: str | None = Field(None, examples=["7"])
    admitted_on: str | None = Field(None, examples=["2026-09-29"], description="YYYY-MM-DD")
    surgery_on: str | None = Field(None, description="YYYY-MM-DD; post-op day is derived from it")
    allergies_status: str | None = Field(
        "documented",
        description="Whether an allergy history was actually taken. 'none recorded' is "
                    "not the same as 'no known allergies'.")
    weight_kg: float | None = Field(None, ge=0, le=500)
    weight_source: str | None = Field(None, examples=["bed scale"])
    family_name: str | None = None
    family_relation: str | None = Field(None, examples=["daughter"])
    family_phone: str | None = None

    _vid = field_validator("id")(check_patient_id)


class PatientPatch(BaseModel):
    """Any subset of a patient's attributes. Omitted fields are left alone."""
    name: str | None = None
    room: str | None = None
    dx: str | None = None
    code_status: str | None = None
    allergies: str | None = None
    isolation: str | None = None
    restraints: str | None = None
    fall_score: int | None = Field(None, ge=0, le=125)
    fall_interventions: str | None = None
    language: str | None = None


class Patient(PatientIn):
    """A patient as stored, plus what is derived: fall risk, post-op day, the RN on shift."""
    fall_risk: str = Field(description="low | moderate | HIGH, derived from fall_score")
    post_op_day: int | None = Field(None, description="Derived from surgery_on")
    weight_at: str | None = Field(None, description="When the weight was taken, HH:MM")
    weight_stale: bool = Field(False, description="True if the weight predates today")
    family_updated_at: str | None = None
    rn_id: str | None = Field(None, description="RN on shift for this patient")
    rn_name: str | None = None


# ----------------------------------------------------------------------- staff

class StaffIn(BaseModel):
    """A caregiver. The id prefix must match the role: nurse→N, aide→A, charge→C, provider→D."""
    id: str = Field(examples=["N-03"], description="X-## where X is the role prefix")
    name: str = Field(examples=["Marcus Hale"])
    role: Role = Field(examples=["nurse"])
    shift_start_hour: int = Field(ge=0, le=23, examples=[19], description="Local hour, 0-23")
    shift_end_hour: int = Field(ge=0, le=23, examples=[7])
    backup_for: str | None = Field(None, description="Staff id this person covers when unreachable")

    _vid = field_validator("id")(check_staff_id)

    @field_validator("backup_for")
    @classmethod
    def _vbackup(cls, v):
        return check_staff_id(v) if v else v


class Staff(BaseModel):
    """A caregiver as stored, with shift times resolved against the ward clock."""
    id: str
    name: str
    role: Role
    shift_start: str = Field(description="HH:MM")
    shift_end: str = Field(description="HH:MM")
    on_shift: bool = Field(description="True if the ward clock is inside this shift")
    backup_for: str | None = None


class Assignment(BaseModel):
    """Which caregiver holds which patient, for which shift."""
    patient_id: str
    staff_id: str
    shift: Shift = "day"

    _vp = field_validator("patient_id")(check_patient_id)
    _vs = field_validator("staff_id")(check_staff_id)


# ------------------------------------------------------------ clinical records

class Vital(BaseModel):
    at: str
    hr: int
    bp: str
    rr: int
    temp: float
    spo2: int
    abnormal: bool


class Med(BaseModel):
    name: str
    dose: str
    route: str
    due_at: str
    given_at: str | None = None
    status: Literal["due", "given", "missed", "held"]


class Lab(BaseModel):
    name: str
    value: str | None = None
    unit: str | None = None
    status: Literal["pending", "resulted"]
    flag: str | None = Field(None, description="HIGH | LOW | CRITICAL, or null if normal")
    resulted_at: str | None = None


class Order(BaseModel):
    text: str
    status: Literal["active", "open", "complete"]


class AlarmEvent(BaseModel):
    at: str
    kind: Literal["limit_changed", "silenced", "disabled"]
    detail: str
    actor: str = Field(description="Staff id who made the change")


class Note(BaseModel):
    at: str
    author: str = Field(description="Staff id, or 'family'")
    kind: Literal["shift_note", "aide_obs", "family_concern"]
    text: str
    abnormal: bool


class Device(BaseModel):
    """A line, tube or airway. Status tracks removal."""
    id: int
    kind: Literal["peripheral_iv", "central_line", "foley", "drain", "airway", "ng_tube"]
    site: str
    detail: str | None = None
    inserted_at: str
    inserted_by: str
    status: str
    observations: list[dict] = Field(default_factory=list,
                                     description="Output or site checks, newest last")


class Wound(BaseModel):
    site: str
    description: str
    dressing: str | None = None
    last_changed_at: str | None = None
    changed_by: str | None = None
    status: str


class VentSetting(BaseModel):
    """One row per CHANGE, so a PEEP rise is two rows and the change is visible."""
    at: str
    mode: str
    peep: int
    fio2: int
    rate: int | None = None
    tidal_volume: int | None = None
    changed_by: str
    note: str | None = None


class Sedation(BaseModel):
    at: str
    drug: str
    dose: str
    rass: int = Field(ge=-5, le=4, description="Richmond Agitation-Sedation Scale")
    note: str | None = None


class RestraintEvent(BaseModel):
    at: str
    action: Literal["applied", "removed", "reassessed"]
    kind: str
    reason: str
    actor: str


class PatientRecords(BaseModel):
    """Everything recorded against one patient. This is the join the agent reads."""
    patient: Patient
    vitals: list[Vital]
    meds: list[Med]
    labs: list[Lab]
    orders: list[Order]
    alarms: list[AlarmEvent]
    notes: list[Note]
    devices: list[Device] = []
    wounds: list[Wound] = []
    vent: list[VentSetting] = []
    sedation: list[Sedation] = []
    restraints: list[RestraintEvent] = []
    counts: dict[str, int] = Field(description="Row count per record type")


class RnPanel(BaseModel):
    """One RN's whole workload — the view a nurse opens at the start of a shift."""
    rn: Staff
    ward_time: str
    patients: list[Patient]
    open_tasks: int
    overdue_tasks: int
    unowned_tasks: int
    handoffs_outstanding: int
    unread_messages: int
