"""F7 bedside family summary and F9 speak-up / transfer / incident linking.
Thin by design — these are P1/P2 and only need to exist for the demo."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import rows, one, write, audit
from ..clock import now, hhmm
from ..events import emit

router = APIRouter(tags=["extras"])


# ------------------------------------------------------------------ F7 family

PLAIN = {
    "CHF exacerbation": "extra fluid around the heart and lungs",
    "post-op day 1, hip ORIF": "the first day after hip surgery",
    "pyelonephritis, sepsis watch": "a kidney infection we're watching closely",
}


@router.get("/family-summary/{pid}")
def family_summary(pid: str):
    """FR-7.1: plain-language plan. Template-based — the agent layer would write this."""
    p = one("SELECT * FROM patients WHERE id=?", (pid,))
    if not p:
        raise HTTPException(404, "no such patient")
    due = rows("SELECT * FROM meds WHERE patient_id=? AND status='due' ORDER BY due_at", (pid,))
    pend = rows("SELECT * FROM labs WHERE patient_id=? AND status='pending'", (pid,))
    lines = [f"{p['name']} is in room {p['room']} being treated for "
             f"{PLAIN.get(p['dx'], p['dx'])}."]
    if due:
        lines.append("Medicines coming up: " +
                     ", ".join(f"{m['name']} at {hhmm(m['due_at'])}" for m in due) + ".")
    if pend:
        lines.append("We are waiting on " + ", ".join(l["name"] for l in pend) +
                     ". We will share the results when they arrive.")
    lines.append(f"To keep {p['name'].split()[0]} safe we are using: {p['fall_interventions']}.")
    lines.append("Please tell the nurse anything that seems new or worse.")
    emit("extra", f"Family summary generated for {p['name']} ({p['language']})", patient=pid)
    return {"patient": p["name"], "language": p["language"],
            "reading_level": "~grade 6 (template)", "summary": " ".join(lines),
            "note": "template text — the agent layer writes and translates this"}


class Concern(BaseModel):
    patient_id: str | None = None
    body: str
    reporter_id: str = "N-02"
    anonymous: bool = False


@router.post("/family-concerns")
def family_concern(body: Concern):
    """FR-7.2: a family concern rides along until it is resolved."""
    write("INSERT INTO notes (patient_id,author,t,kind,text,abnormal) VALUES (?,?,?,?,?,?)",
          (body.patient_id, "family", now(), "family_concern", body.body, 1))
    emit("extra", f"Family concern on {body.patient_id}: \"{body.body[:52]}\" — "
                  f"carried into every handoff until resolved", patient=body.patient_id)
    return {"recorded_at": hhmm(now()), "carries_forward": True}


# ------------------------------------------------------------------ F9 speak-up

@router.post("/concerns")
def speak_up(body: Concern):
    """FR-9.1 / FR-9.2: CUS-worded concern, optional anonymity, routed and tracked."""
    charge = one("SELECT * FROM staff WHERE role='charge'")
    routed = "MANAGER" if charge and body.reporter_id == charge["id"] else (charge["id"] if charge else "MANAGER")
    cid = write("""INSERT INTO concerns (kind,body,anonymous,reporter_id,routed_to,state,opened_at)
                   VALUES (?,?,?,?,?,?,?)""",
                ("CUS", body.body, int(body.anonymous),
                 None if body.anonymous else body.reporter_id, routed, "open", now()))
    who = "anonymous" if body.anonymous else body.reporter_id
    emit("extra", f"Concern {cid} raised ({who}) → {routed}: \"{body.body[:48]}\"", concern=cid)
    audit(who, "concern.open", str(cid))
    return {"id": cid, "routed_to": routed, "state": "open", "opened_at": hhmm(now()),
            "template": "I am Concerned / Uncomfortable / this is a Safety issue"}


@router.post("/concerns/{cid}/close")
def close_concern(cid: int, actor: str = "C-01"):
    write("UPDATE concerns SET state='closed', closed_at=? WHERE id=?", (now(), cid))
    emit("extra", f"Concern {cid} closed by {actor}", concern=cid)
    return {"id": cid, "state": "closed", "closed_at": hhmm(now())}


@router.get("/concerns")
def list_concerns():
    return [{"id": c["id"], "state": c["state"], "routed_to": c["routed_to"],
             "anonymous": bool(c["anonymous"]), "body": c["body"],
             "opened": hhmm(c["opened_at"]), "closed": hhmm(c["closed_at"])}
            for c in rows("SELECT * FROM concerns ORDER BY id")]


class Transfer(BaseModel):
    patient_id: str
    from_unit: str = "ED"
    to_unit: str = "4 West"
    reason: str = "admission for IV antibiotics"
    lines_drains: str = "20g left forearm IV; no drains"
    pending_consults: str = "none"


@router.post("/transfers")
def transfer(body: Transfer):
    """FR-9.3 / FR-9.4: the F1 fields plus transfer-specific ones, both nurses sign."""
    from .handoff import build_draft, _field
    d = build_draft(body.patient_id, giver="N-01", receiver="N-02")
    hid = d["id"]
    _field(hid, "awareness", "transfer_reason", "Reason for transfer", body.reason,
           f"transfer {body.from_unit}→{body.to_unit}", True)
    _field(hid, "awareness", "lines_drains", "Lines and drains", body.lines_drains, "transfer form", True)
    _field(hid, "awareness", "pending_consults", "Pending consults", body.pending_consults, "transfer form", True)
    emit("extra", f"Transfer handoff {hid}: {body.from_unit} → {body.to_unit}, both nurses must sign",
         handoff=hid)
    from .handoff import get
    return get(hid)


class Incident(BaseModel):
    patient_id: str
    text: str


@router.post("/incidents")
def incident(body: Incident):
    """FR-9.5: link an incident to the nearest earlier handoff in one step."""
    h = one("""SELECT * FROM handoffs WHERE patient_id=? AND created_at<=?
               ORDER BY created_at DESC LIMIT 1""", (body.patient_id, now()))
    iid = write("INSERT INTO incidents (patient_id,text,t,handoff_id) VALUES (?,?,?,?)",
                (body.patient_id, body.text, now(), h["id"] if h else None))
    from .handoff import missing_fields
    gaps = missing_fields(h["id"]) if h else []
    emit("extra", f"Incident {iid} on {body.patient_id} linked to {h['id'] if h else 'no handoff'}"
                  f"{f' — that handoff was missing: {gaps}' if gaps else ''}", incident=iid)
    return {"id": iid, "linked_handoff": h["id"] if h else None,
            "handoff_gaps_at_the_time": gaps}


@router.get("/incidents")
def list_incidents():
    return [{"id": i["id"], "patient": i["patient_id"], "at": hhmm(i["t"]),
             "handoff": i["handoff_id"], "text": i["text"]}
            for i in rows("SELECT * FROM incidents ORDER BY id")]
