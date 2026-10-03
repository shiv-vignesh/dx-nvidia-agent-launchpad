"""F8 unit oversight: charge-nurse board, shift-end nudges, aide observations."""
from fastapi import APIRouter
from pydantic import BaseModel

from ..db import rows, one, write, audit
from ..clock import now, hhmm, rel, MIN
from ..events import emit
from . import tasks as tasks_mod

router = APIRouter(prefix="/oversight", tags=["oversight"])

_nudged: set = set()      # (staff_id, minutes_before) — nudge once each


@router.get("/board")
def board():
    """FR-8.1 / FR-8.2: one row per patient, overdue handoffs highlighted."""
    out = []
    shift_end = one("SELECT * FROM staff WHERE id='N-01'")["shift_end"]
    for p in rows("SELECT * FROM patients ORDER BY room"):
        h = one("""SELECT * FROM handoffs WHERE patient_id=?
                   ORDER BY created_at DESC LIMIT 1""", (p["id"],))
        from .handoff import missing_fields
        tl = tasks_mod.for_patient(p["id"])
        row = {
            "room": p["room"], "patient": p["name"], "patient_id": p["id"],
            "handoff": h["id"] if h else None,
            "status": h["status"] if h else "not started",
            "giver": h["giver_id"] if h else None,
            "receiver": h["receiver_id"] if h else None,
            "missing_fields": missing_fields(h["id"]) if h else [],
            "open_tasks": len(tl),
            "unowned_tasks": sum(1 for t in tl if t["unowned"]),
            "overdue_tasks": sum(1 for t in tl if t["overdue"]),
            "overdue_handoff": bool(
                (not h or h["status"] != "closed") and now() > shift_end + 15 * MIN),
        }
        out.append(row)
    return {"ward_time": hhmm(now()), "shift_end": hhmm(shift_end), "rows": out}


@router.get("/report")
def report():
    """FR-8.3 / FR-8.5: completion rate, most-missed fields, late departures."""
    hs = rows("SELECT * FROM handoffs")
    closed = [h for h in hs if h["status"] == "closed"]
    from .handoff import missing_fields
    missed = {}
    for h in hs:
        for lbl in missing_fields(h["id"]):
            missed[lbl] = missed.get(lbl, 0) + 1
    shift_end = one("SELECT * FROM staff WHERE id='N-01'")["shift_end"]
    late = [{"handoff": h["id"], "closed": hhmm(h["closed_at"]),
             "minutes_late": round((h["closed_at"] - shift_end) / 60)}
            for h in closed if h["closed_at"] and h["closed_at"] > shift_end + 30 * MIN]
    return {
        "handoffs": len(hs), "closed": len(closed),
        "completion_rate": f"{(len(closed) / len(hs) * 100) if hs else 0:.0f}%",
        "most_missed_fields": sorted(missed.items(), key=lambda kv: -kv[1]),
        "late_departures": late,
        "audit_entries": len(rows("SELECT id FROM audit")),
    }


def check_nudges():
    """FR-8.4: nudge the outgoing nurse 60 and 30 min before shift end."""
    fired = 0
    for s in rows("SELECT * FROM staff WHERE role='nurse'"):
        left = (s["shift_end"] - now()) / MIN
        for mark in (60, 30):
            if mark - 1 < left <= mark and (s["id"], mark) not in _nudged:
                _nudged.add((s["id"], mark))
                pend = []
                for a in rows("SELECT patient_id FROM assignments WHERE staff_id=?", (s["id"],)):
                    h = one("""SELECT * FROM handoffs WHERE patient_id=? AND giver_id=?
                               ORDER BY created_at DESC LIMIT 1""", (a["patient_id"], s["id"]))
                    if not h:
                        pend.append(f"{a['patient_id']}: no draft yet")
                    elif h["status"] != "closed":
                        from .handoff import missing_fields
                        m = missing_fields(h["id"])
                        pend.append(f"{a['patient_id']}: {h['status']}" +
                                    (f", missing {len(m)}" if m else ""))
                emit("oversight", f"NUDGE {mark}m to shift end for {s['name']} — "
                                  f"{'; '.join(pend) if pend else 'all clear'}",
                     staff=s["id"], minutes=mark)
                fired += 1
    return fired


def check_draft_ready():
    """FR-1.5: a draft must exist 30 min before shift end — auto-create if not."""
    made = 0
    for s in rows("SELECT * FROM staff WHERE role='nurse'"):
        if not (0 < (s["shift_end"] - now()) / MIN <= 30):
            continue
        for a in rows("SELECT patient_id FROM assignments WHERE staff_id=?", (s["id"],)):
            h = one("""SELECT * FROM handoffs WHERE patient_id=? ORDER BY created_at DESC LIMIT 1""",
                    (a["patient_id"],))
            if not h:
                from .handoff import build_draft
                tasks_mod.derive(a["patient_id"])
                build_draft(a["patient_id"], s["id"], "N-02")
                emit("oversight", f"Auto-drafted handoff for {a['patient_id']} "
                                  f"(30-minute rule)", patient=a["patient_id"])
                made += 1
    return made


# ------------------------------------------------------------- aide observations

class Obs(BaseModel):
    patient_id: str
    text: str
    actor: str = "A-01"
    abnormal: bool = False


@router.post("/observations")
def add_obs(body: Obs):
    """FR-8.6 / FR-8.7: a quick aide log, into the nurse's feed and the next draft."""
    write("INSERT INTO notes (patient_id,author,t,kind,text,abnormal) VALUES (?,?,?,?,?,?)",
          (body.patient_id, body.actor, now(), "aide_obs", body.text, int(body.abnormal)))
    from .directory import current_rn
    rn = current_rn(body.patient_id)
    nurse = {"staff_id": rn["id"]} if rn else None
    tag = "ABNORMAL — " if body.abnormal else ""
    emit("oversight", f"{tag}{body.actor} logged on {body.patient_id}: \"{body.text[:52]}\" "
                      f"→ {nurse['staff_id'] if nurse else 'unassigned'}",
         patient=body.patient_id, abnormal=body.abnormal)
    audit(body.actor, "observation.add", body.patient_id)
    return {"patient": body.patient_id, "logged_at": hhmm(now()),
            "routed_to": nurse["staff_id"] if nurse else None,
            "in_next_handoff": True}


@router.get("/feed/{staff_id}")
def feed(staff_id: str):
    pids = [a["patient_id"] for a in rows("SELECT patient_id FROM assignments WHERE staff_id=?", (staff_id,))]
    if not pids:
        return []
    q = ",".join("?" * len(pids))
    return [{"patient": n["patient_id"], "at": hhmm(n["t"]), "by": n["author"],
             "kind": n["kind"], "text": n["text"], "abnormal": bool(n["abnormal"])}
            for n in rows(f"SELECT * FROM notes WHERE patient_id IN ({q}) ORDER BY t DESC",
                          tuple(pids))]
