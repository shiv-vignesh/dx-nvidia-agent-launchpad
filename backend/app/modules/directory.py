"""The registry: patients, RNs, and the assignment that links them.

Every other module keys off the two ids this module owns — `patient_id` and
`staff_id`. Nothing else crosses module boundaries, so a record can always be
traced back to a patient and to whoever touched it.
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime

from ..db import rows, one, write, audit
from ..clock import now, hhmm, at, HOUR
from ..events import emit
from ..schemas import (Patient, PatientIn, PatientPatch, PatientRecords, Staff, StaffIn,
                       Assignment, RnPanel, ROLE_PREFIX, check_patient_id, check_staff_id)

patients_router = APIRouter(prefix="/patients", tags=["registry"])
staff_router = APIRouter(prefix="/nurses", tags=["registry"])
meta_router = APIRouter(tags=["registry"])


# ------------------------------------------------------------------- helpers

def fall_risk(score):
    return "HIGH" if score >= 13 else "moderate" if score >= 7 else "low"


def on_shift(s) -> bool:
    """True if the ward clock sits inside this person's shift (handles overnight)."""
    t = datetime.fromtimestamp(now()).hour
    a = datetime.fromtimestamp(s["shift_start"]).hour
    b = datetime.fromtimestamp(s["shift_end"]).hour
    return a <= t < b if a < b else (t >= a or t < b)


def current_rn(pid):
    """The nurse holding this patient right now: the on-shift assignee, else any."""
    cands = rows("""SELECT a.staff_id, s.* FROM assignments a JOIN staff s ON s.id=a.staff_id
                    WHERE a.patient_id=? AND s.role='nurse'""", (pid,))
    for c in cands:
        if on_shift(c):
            return c
    return cands[0] if cands else None


def post_op_day(surgery_on):
    """Days since surgery, counting the operation as day 0."""
    if not surgery_on:
        return None
    try:
        d = datetime.strptime(surgery_on, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (datetime.fromtimestamp(now()).date() - d).days


def shape_patient(p) -> dict:
    rn = current_rn(p["id"])
    today = datetime.fromtimestamp(now()).date()
    w_at = p["weight_at"]
    return {**{k: p[k] for k in (
        "id", "mrn", "name", "sex", "age", "unit", "room", "bed", "dx",
        "admitted_on", "surgery_on", "code_status", "allergies", "allergies_status",
        "isolation", "restraints", "fall_score", "fall_interventions", "language",
        "weight_kg", "weight_source", "family_name", "family_relation", "family_phone")},
        "fall_risk": fall_risk(p["fall_score"]),
        "post_op_day": post_op_day(p["surgery_on"]),
        "weight_at": hhmm(w_at),
        # a recorded weight with no timestamp is as unreliable as an old one
        "weight_stale": bool(p["weight_kg"]) and (
            not w_at or datetime.fromtimestamp(w_at).date() < today),
        "family_updated_at": hhmm(p["family_updated_at"]),
        "rn_id": rn["id"] if rn else None,
        "rn_name": rn["name"] if rn else None}


def shape_staff(s) -> dict:
    return {"id": s["id"], "name": s["name"], "role": s["role"],
            "shift_start": hhmm(s["shift_start"]), "shift_end": hhmm(s["shift_end"]),
            "on_shift": on_shift(s), "backup_for": s["backup_for"]}


# ------------------------------------------------------------------ patients

@patients_router.get("", response_model=list[Patient], summary="List patients")
def list_patients(rn_id: str | None = None, room: str | None = None,
                  high_fall_risk: bool = False):
    """Filter by the RN holding them, by room, or to high fall risk only."""
    ps = [shape_patient(p) for p in rows("SELECT * FROM patients ORDER BY room")]
    if rn_id:
        ps = [p for p in ps if p["rn_id"] == rn_id]
    if room:
        ps = [p for p in ps if p["room"] == room]
    if high_fall_risk:
        ps = [p for p in ps if p["fall_risk"] == "HIGH"]
    return ps


@patients_router.post("", response_model=Patient, status_code=201, summary="Admit a patient")
def create_patient(body: PatientIn):
    if one("SELECT id FROM patients WHERE id=?", (body.id,)):
        raise HTTPException(409, f"{body.id} already exists")
    d = body.model_dump()
    cols = ",".join(d)
    write(f"INSERT INTO patients ({cols}) VALUES ({','.join('?' * len(d))})",
          tuple(d.values()))
    emit("extra", f"Admitted {body.id} {body.name} to {body.room} — {body.dx}", patient=body.id)
    audit("system", "patient.admit", body.id)
    return shape_patient(one("SELECT * FROM patients WHERE id=?", (body.id,)))


@patients_router.get("/{pid}", response_model=Patient, summary="One patient")
def get_patient(pid: str):
    p = one("SELECT * FROM patients WHERE id=?", (pid,))
    if not p:
        raise HTTPException(404, f"no patient {pid}")
    return shape_patient(p)


@patients_router.patch("/{pid}", response_model=Patient, summary="Update a patient")
def patch_patient(pid: str, body: PatientPatch):
    p = one("SELECT * FROM patients WHERE id=?", (pid,))
    if not p:
        raise HTTPException(404, f"no patient {pid}")
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(422, "nothing to update")
    write(f"UPDATE patients SET {','.join(k + '=?' for k in fields)} WHERE id=?",
          (*fields.values(), pid))
    emit("extra", f"{pid} updated: {', '.join(fields)}", patient=pid)
    audit("system", "patient.update", f"{pid}: {list(fields)}")
    return shape_patient(one("SELECT * FROM patients WHERE id=?", (pid,)))


@patients_router.get("/{pid}/records", response_model=PatientRecords,
                     summary="Every record for one patient")
def patient_records(pid: str):
    """The full join: vitals, meds, labs, orders, alarm changes and notes.
    Times are rendered HH:MM and internal row ids are not exposed."""
    p = one("SELECT * FROM patients WHERE id=?", (pid,))
    if not p:
        raise HTTPException(404, f"no patient {pid}")
    v = [{"at": hhmm(r["t"]), "hr": r["hr"], "bp": r["bp"], "rr": r["rr"],
          "temp": r["temp"], "spo2": r["spo2"], "abnormal": bool(r["abnormal"])}
         for r in rows("SELECT * FROM vitals WHERE patient_id=? ORDER BY t", (pid,))]
    m = [{"name": r["name"], "dose": r["dose"], "route": r["route"],
          "due_at": hhmm(r["due_at"]), "given_at": hhmm(r["given_at"]), "status": r["status"]}
         for r in rows("SELECT * FROM meds WHERE patient_id=? ORDER BY due_at", (pid,))]
    l = [{"name": r["name"], "value": r["value"], "unit": r["unit"], "status": r["status"],
          "flag": r["flag"], "resulted_at": hhmm(r["resulted_at"])}
         for r in rows("SELECT * FROM labs WHERE patient_id=?", (pid,))]
    o = [{"text": r["text"], "status": r["status"]}
         for r in rows("SELECT * FROM orders WHERE patient_id=?", (pid,))]
    a = [{"at": hhmm(r["t"]), "kind": r["kind"], "detail": r["detail"], "actor": r["actor"]}
         for r in rows("SELECT * FROM alarm_events WHERE patient_id=? ORDER BY t", (pid,))]
    n = [{"at": hhmm(r["t"]), "author": r["author"], "kind": r["kind"],
          "text": r["text"], "abnormal": bool(r["abnormal"])}
         for r in rows("SELECT * FROM notes WHERE patient_id=? ORDER BY t", (pid,))]
    dv = []
    for r in rows("SELECT * FROM devices WHERE patient_id=? ORDER BY inserted_at", (pid,)):
        dv.append({"id": r["id"], "kind": r["kind"], "site": r["site"],
                   "detail": r["detail"], "inserted_at": hhmm(r["inserted_at"]),
                   "inserted_by": r["inserted_by"], "status": r["status"],
                   "observations": [{"at": hhmm(o_["t"]), "detail": o_["detail"],
                                     "actor": o_["actor"]}
                                    for o_ in rows("""SELECT * FROM device_obs
                                                      WHERE device_id=? ORDER BY t""",
                                                   (r["id"],))]})
    w = [{"site": r["site"], "description": r["description"], "dressing": r["dressing"],
          "last_changed_at": hhmm(r["last_changed_at"]), "changed_by": r["changed_by"],
          "status": r["status"]}
         for r in rows("SELECT * FROM wounds WHERE patient_id=?", (pid,))]
    vt = [{"at": hhmm(r["t"]), "mode": r["mode"], "peep": r["peep"], "fio2": r["fio2"],
           "rate": r["rate"], "tidal_volume": r["tidal_volume"],
           "changed_by": r["changed_by"], "note": r["note"]}
          for r in rows("SELECT * FROM vent_settings WHERE patient_id=? ORDER BY t", (pid,))]
    sd = [{"at": hhmm(r["t"]), "drug": r["drug"], "dose": r["dose"], "rass": r["rass"],
           "note": r["note"]}
          for r in rows("SELECT * FROM sedation WHERE patient_id=? ORDER BY t", (pid,))]
    re_ = [{"at": hhmm(r["t"]), "action": r["action"], "kind": r["kind"],
            "reason": r["reason"], "actor": r["actor"]}
           for r in rows("SELECT * FROM restraint_events WHERE patient_id=? ORDER BY t", (pid,))]
    return {"patient": shape_patient(p), "vitals": v, "meds": m, "labs": l,
            "orders": o, "alarms": a, "notes": n, "devices": dv, "wounds": w,
            "vent": vt, "sedation": sd, "restraints": re_,
            "counts": {"vitals": len(v), "meds": len(m), "labs": len(l),
                       "orders": len(o), "alarms": len(a), "notes": len(n),
                       "devices": len(dv), "wounds": len(w), "vent_changes": len(vt),
                       "sedation": len(sd), "restraint_events": len(re_)}}


# --------------------------------------------------------------------- staff

@staff_router.get("", response_model=list[Staff], summary="Staff roster")
def list_staff(role: str | None = None, on_shift_only: bool = False):
    """Defaults to everyone. `role=nurse` gives the RNs."""
    ss = [shape_staff(s) for s in rows("SELECT * FROM staff ORDER BY role, id")]
    if role:
        ss = [s for s in ss if s["role"] == role]
    if on_shift_only:
        ss = [s for s in ss if s["on_shift"]]
    return ss


@staff_router.post("", response_model=Staff, status_code=201, summary="Add a caregiver")
def create_staff(body: StaffIn):
    want = ROLE_PREFIX[body.role]
    if body.id[0] != want:
        raise HTTPException(422, f"role '{body.role}' needs an id starting '{want}-', "
                                 f"got '{body.id}'")
    if one("SELECT id FROM staff WHERE id=?", (body.id,)):
        raise HTTPException(409, f"{body.id} already exists")
    if body.backup_for and not one("SELECT id FROM staff WHERE id=?", (body.backup_for,)):
        raise HTTPException(422, f"backup_for '{body.backup_for}' does not exist")
    write("""INSERT INTO staff (id,name,role,shift_start,shift_end,backup_for)
             VALUES (?,?,?,?,?,?)""",
          (body.id, body.name, body.role, at(body.shift_start_hour),
           at(body.shift_end_hour), body.backup_for))
    emit("extra", f"Added {body.role} {body.id} {body.name} "
                  f"({body.shift_start_hour:02d}:00–{body.shift_end_hour:02d}:00)")
    audit("system", "staff.add", f"{body.id} {body.role}")
    return shape_staff(one("SELECT * FROM staff WHERE id=?", (body.id,)))


@staff_router.get("/{rn_id}", response_model=Staff, summary="One caregiver")
def get_staff(rn_id: str):
    s = one("SELECT * FROM staff WHERE id=?", (rn_id,))
    if not s:
        raise HTTPException(404, f"no staff {rn_id}")
    return shape_staff(s)


@staff_router.get("/{rn_id}/panel", response_model=RnPanel,
                  summary="One RN's whole workload")
def rn_panel(rn_id: str):
    """Assigned patients plus the counts that tell this nurse what needs doing."""
    s = one("SELECT * FROM staff WHERE id=?", (rn_id,))
    if not s:
        raise HTTPException(404, f"no staff {rn_id}")
    pids = [a["patient_id"] for a in
            rows("SELECT patient_id FROM assignments WHERE staff_id=?", (rn_id,))]
    ps = [shape_patient(one("SELECT * FROM patients WHERE id=?", (p,))) for p in pids
          if one("SELECT * FROM patients WHERE id=?", (p,))]
    ts = rows("SELECT * FROM tasks WHERE owner_id=? AND status!='done'", (rn_id,))
    ho = rows("""SELECT * FROM handoffs WHERE (giver_id=? OR receiver_id=?)
                 AND status!='closed'""", (rn_id, rn_id))
    unread = rows("""SELECT * FROM messages WHERE recipient_id=?
                     AND state IN ('sent','delivered')""", (rn_id,))
    return {"rn": shape_staff(s), "ward_time": hhmm(now()), "patients": ps,
            "open_tasks": len(ts),
            "overdue_tasks": sum(1 for t in ts if t["due_at"] < now()),
            "unowned_tasks": len(rows("""SELECT * FROM tasks WHERE owner_id IS NULL
                                         AND status!='done' AND patient_id IN
                                         (SELECT patient_id FROM assignments WHERE staff_id=?)""",
                                      (rn_id,))),
            "handoffs_outstanding": len(ho), "unread_messages": len(unread)}


# --------------------------------------------------------------- assignments

@meta_router.get("/assignments", response_model=list[Assignment], summary="Who holds whom")
def list_assignments(shift: str | None = None):
    a = [{"patient_id": r["patient_id"], "staff_id": r["staff_id"],
          "shift": r["shift"] or "day"}
         for r in rows("SELECT * FROM assignments ORDER BY patient_id")]
    return [x for x in a if x["shift"] == shift] if shift else a


@meta_router.post("/assignments", response_model=Assignment, status_code=201,
                  summary="Assign a patient to a caregiver")
def create_assignment(body: Assignment):
    if not one("SELECT id FROM patients WHERE id=?", (body.patient_id,)):
        raise HTTPException(422, f"no patient {body.patient_id}")
    if not one("SELECT id FROM staff WHERE id=?", (body.staff_id,)):
        raise HTTPException(422, f"no staff {body.staff_id}")
    if one("""SELECT * FROM assignments WHERE patient_id=? AND staff_id=? AND shift=?""",
           (body.patient_id, body.staff_id, body.shift)):
        raise HTTPException(409, "that assignment already exists")
    write("INSERT INTO assignments (patient_id,staff_id,shift,since) VALUES (?,?,?,?)",
          (body.patient_id, body.staff_id, body.shift, now()))
    emit("oversight", f"{body.patient_id} assigned to {body.staff_id} ({body.shift} shift)",
         patient=body.patient_id)
    audit("system", "assignment.add", f"{body.patient_id}->{body.staff_id}")
    return body


@meta_router.delete("/assignments", status_code=204, summary="Unassign")
def delete_assignment(patient_id: str, staff_id: str):
    if not one("SELECT * FROM assignments WHERE patient_id=? AND staff_id=?",
               (patient_id, staff_id)):
        raise HTTPException(404, "no such assignment")
    write("DELETE FROM assignments WHERE patient_id=? AND staff_id=?", (patient_id, staff_id))
    emit("oversight", f"{patient_id} unassigned from {staff_id}", patient=patient_id)


# -------------------------------------------------------------- data dictionary

SCHEMA_DOC = {
    "identifiers": {
        "patient_id": {"pattern": "P-###", "example": "P-101",
                       "description": "The subject of care. Unique, never reused."},
        "staff_id": {"pattern": "X-## where X is the role prefix", "example": "N-02",
                     "prefixes": {"N": "nurse (RN)", "A": "aide",
                                  "C": "charge nurse", "D": "provider"}},
        "handoff_id": {"pattern": "HO-<patient digits>-<4 hex>", "example": "HO-101-7b2d"},
    },
    "tables": {
        "patients": {"pk": "id (P-###)", "fk": [], "holds": "MRN, demographics, unit/room/bed, "
                     "admission and surgery dates, code status, allergies and whether a "
                     "history was taken, isolation, fall score, weight with an as-of, "
                     "family contact, preferred language"},
        "devices": {"fk": ["patient_id", "inserted_by → staff.id"],
                    "holds": "lines, Foley, drains, airway: site, when placed, by whom, status"},
        "device_obs": {"fk": ["device_id", "patient_id"],
                       "holds": "output and site checks against one device"},
        "wounds": {"fk": ["patient_id", "changed_by → staff.id"],
                   "holds": "site, description, dressing, when last changed"},
        "vent_settings": {"fk": ["patient_id", "changed_by → staff.id"],
                          "holds": "one row per CHANGE — mode, PEEP, FiO2, rate, Vt"},
        "sedation": {"fk": ["patient_id"], "holds": "drug, dose and RASS over time"},
        "restraint_events": {"fk": ["patient_id", "actor → staff.id"],
                             "holds": "applied / removed / reassessed, with the reason"},
        "staff": {"pk": "id (X-##)", "fk": ["backup_for → staff.id"],
                  "holds": "name, role, shift window, who they cover"},
        "assignments": {"pk": "rowid", "fk": ["patient_id → patients.id",
                                              "staff_id → staff.id"],
                        "holds": "which caregiver holds which patient, per shift"},
        "vitals": {"fk": ["patient_id"], "holds": "HR, BP, RR, temp, SpO2, abnormal flag"},
        "meds": {"fk": ["patient_id"], "holds": "drug, dose, route, due, given, status"},
        "labs": {"fk": ["patient_id"], "holds": "name, value, unit, status, HIGH/LOW flag"},
        "orders": {"fk": ["patient_id"], "holds": "order text and status"},
        "alarm_events": {"fk": ["patient_id", "actor → staff.id"],
                         "holds": "limit changes and silences, with who and when"},
        "notes": {"fk": ["patient_id", "author → staff.id"],
                  "holds": "shift notes, aide observations, family concerns"},
        "handoffs": {"pk": "id (HO-…)", "fk": ["patient_id", "giver_id → staff.id",
                                               "receiver_id → staff.id"],
                     "holds": "status, timings, the receiver's read-back"},
        "handoff_fields": {"fk": ["handoff_id"],
                           "holds": "one row per I-PASS field: value, its source, "
                                    "whether required, who edited it"},
        "acks": {"fk": ["handoff_id", "actor → staff.id"],
                 "holds": "per-item acknowledgements and agent proposals"},
        "tasks": {"fk": ["patient_id", "owner_id → staff.id", "handoff_id"],
                  "holds": "carry-over work: text, owner, due time, status, origin"},
        "messages": {"fk": ["patient_id", "sender_id → staff.id",
                            "recipient_id → staff.id"],
                     "holds": "SBAR fields, urgency, state, re-route time"},
        "message_events": {"fk": ["message_id"], "holds": "the state trail with timestamps"},
        "audit": {"fk": [], "holds": "append-only: who did what, when (NFR-4)"},
    },
    "notes": [
        "Every clinical table carries patient_id, so one patient's whole record is a "
        "single join (GET /patients/{id}/records).",
        "Every action table carries a staff_id, so any change traces to a person "
        "(GET /audit).",
        "Times are stored as ward-clock epoch floats and rendered HH:MM at the edge. "
        "Internal autoincrement ids are not exposed in the typed responses.",
        "SQLite with foreign_keys=OFF — this is a mock. The relationships are real but "
        "not enforced by the engine.",
        "Anything that CHANGES during a shift is an event table, not a column: "
        "vent_settings, restraint_events, alarm_events, sedation, message_events. A "
        "single column would record the current value and lose the change, which is "
        "exactly what a handoff needs to carry.",
        "post_op_day, fall_risk, weight_stale and rn_id are derived on read, never stored.",
    ],
}


@meta_router.get("/schema", tags=["registry"], summary="The data dictionary")
def data_schema():
    """Identifiers, tables and relationships. Pair with /openapi.json for field types."""
    return SCHEMA_DOC
