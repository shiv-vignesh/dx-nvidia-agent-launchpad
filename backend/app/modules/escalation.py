"""F4 SBAR escalation composer. Background is filled from the records; the
Recommendation (the ask) is required and the nurse always presses send."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import rows, one, write, audit
from ..clock import now, hhmm
from ..events import emit

router = APIRouter(prefix="/escalations", tags=["escalation"])


def _background(pid):
    """FR-4.2: vitals trend, relevant labs, meds given — with their sources."""
    v = rows("SELECT * FROM vitals WHERE patient_id=? ORDER BY t DESC LIMIT 4", (pid,))
    trend = " → ".join(f"{hhmm(x['t'])} HR {x['hr']}/BP {x['bp']}/SpO2 {x['spo2']}%"
                       for x in reversed(v))
    labs = rows("""SELECT * FROM labs WHERE patient_id=? AND (flag IS NOT NULL OR status='pending')
                   ORDER BY resulted_at DESC LIMIT 4""", (pid,))
    lab_txt = "; ".join(
        f"{l['name']} {l['value'] or 'PENDING'}{' (' + l['flag'] + ')' if l['flag'] else ''}"
        for l in labs) or "none flagged"
    meds = rows("SELECT * FROM meds WHERE patient_id=? AND status='given' ORDER BY given_at DESC LIMIT 4", (pid,))
    med_txt = "; ".join(f"{m['name']} {m['dose']} at {hhmm(m['given_at'])}" for m in meds) or "none this shift"
    return (f"Vitals trend: {trend}. Labs: {lab_txt}. Meds given: {med_txt}."), {
        "vitals": f"{len(v)} readings", "labs": f"{len(labs)} rows", "meds": f"{len(meds)} administrations"}


class Draft(BaseModel):
    patient_id: str
    concern: str
    recommendation: str | None = None
    sender_id: str = "N-01"
    recipient_id: str = "D-01"
    urgency: str = "urgent"


@router.post("/draft")
def draft(body: Draft):
    """FR-4.3: no early-warning trigger required — 'I'm concerned' is reason enough."""
    p = one("SELECT * FROM patients WHERE id=?", (body.patient_id,))
    if not p:
        raise HTTPException(404, "no such patient")
    bg, sources = _background(body.patient_id)
    v = one("SELECT * FROM vitals WHERE patient_id=? ORDER BY t DESC LIMIT 1", (body.patient_id,))
    if not v:
        raise HTTPException(422, f"no vitals recorded for {body.patient_id} — "
                                 "an escalation needs data behind it")

    situation = (f"{p['name']}, {p['age']}y, room {p['room']}, {p['dx']}. "
                 f"{body.concern}")
    assessment = (f"Nurse concern, {'abnormal' if v['abnormal'] else 'stable'} latest vitals "
                  f"(HR {v['hr']}, BP {v['bp']}, SpO2 {v['spo2']}%). Code status {p['code_status']}.")

    mid = write("""INSERT INTO messages
        (patient_id,sender_id,recipient_id,urgency,situation,background,assessment,
         recommendation,state,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (body.patient_id, body.sender_id, body.recipient_id, body.urgency,
         situation, bg, assessment, body.recommendation, "draft", now()))

    emit("message", f"SBAR draft {mid} for {p['name']} → {body.recipient_id}"
                    f"{' (no Recommendation yet — cannot send)' if not body.recommendation else ''}",
         message=mid, patient=body.patient_id)
    audit(body.sender_id, "escalation.draft", f"{mid} {body.patient_id}")

    from .messaging import _shape
    out = _shape(one("SELECT * FROM messages WHERE id=?", (mid,)))
    out["sources"] = sources
    out["sendable"] = bool(body.recommendation)
    out["note"] = "Recommendation is required before send (FR-4.1); the nurse sends (FR-4.4)"
    return out


class SetAsk(BaseModel):
    recommendation: str
    actor: str = "N-01"


@router.patch("/{mid}/recommendation")
def set_ask(mid: int, body: SetAsk):
    m = one("SELECT * FROM messages WHERE id=?", (mid,))
    if not m:
        raise HTTPException(404, "no such message")
    write("UPDATE messages SET recommendation=? WHERE id=?", (body.recommendation, mid))
    emit("message", f"SBAR {mid}: ask set — \"{body.recommendation[:56]}\"", message=mid)
    audit(body.actor, "escalation.ask", str(mid))
    from .messaging import _shape
    out = _shape(one("SELECT * FROM messages WHERE id=?", (mid,)))
    out["sendable"] = True
    return out
