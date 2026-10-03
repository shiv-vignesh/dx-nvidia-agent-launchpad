"""F1 handoff draft + safety block, F2 read-back and sign-off.

The draft is assembled from ward records by plain rules, and every value carries the
record it came from. The agent layer (not built here) would later rewrite the prose
fields and do a semantic read-back comparison; the two spots are marked STUB.
"""
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import rows, one, write, audit
from ..clock import now, hhmm, rel, at, MIN
from ..events import emit

router = APIRouter(prefix="/handoffs", tags=["handoff"])

SECTIONS = ["illness", "patient", "action", "awareness", "synthesis"]


# ---------------------------------------------------------------- draft build

def _severity(pid):
    ab = rows("SELECT * FROM vitals WHERE patient_id=? AND abnormal=1 AND t>? ORDER BY t DESC",
              (pid, now() - 4 * 3600))
    if not ab:
        return "stable", "no abnormal vitals in the last 4 hours"
    trend = rows("SELECT * FROM vitals WHERE patient_id=? ORDER BY t DESC LIMIT 2", (pid,))
    worsening = len(trend) == 2 and trend[0]["spo2"] < trend[1]["spo2"]
    label = "unstable" if worsening and len(ab) >= 2 else "watcher"
    return label, f"{len(ab)} abnormal vitals since {hhmm(ab[-1]['t'])}"


def _field(hid, section, key, label, value, source, required=False):
    write("""INSERT INTO handoff_fields
             (handoff_id,section,key,label,value,source,required,filled_by,edited_by)
             VALUES (?,?,?,?,?,?,?,?,?)""",
          (hid, section, key, label, value, source, int(required), "rules", None))


def build_draft(pid, giver="N-01", receiver="N-02"):
    p = one("SELECT * FROM patients WHERE id=?", (pid,))
    if not p:
        raise HTTPException(404, f"no patient {pid}")
    hid = f"HO-{pid.split('-')[1]}-{uuid.uuid4().hex[:4]}"
    write("""INSERT INTO handoffs (id,patient_id,giver_id,receiver_id,status,created_at,ready_at)
             VALUES (?,?,?,?,?,?,?)""",
          (hid, pid, giver, receiver, "drafting", now(), None))

    sev, why = _severity(pid)
    _field(hid, "illness", "severity", "Illness severity", sev, f"vitals: {why}", True)

    v = one("SELECT * FROM vitals WHERE patient_id=? ORDER BY t DESC LIMIT 1", (pid,))
    from .directory import post_op_day
    pod = post_op_day(p["surgery_on"])
    _field(hid, "patient", "summary", "Patient summary",
           f"{p['age']}y {p['sex'] or ''}, {p['dx']}"
           + (f", post-op day {pod}" if pod is not None else "")
           + f", {p['unit'] or ''} bed {p['bed'] or p['room']}"
           + (f", MRN {p['mrn']}" if p["mrn"] else ""),
           f"patients/{pid}", True)
    _field(hid, "patient", "code_status", "Code status", p["code_status"], f"patients/{pid}", True)
    # 'no allergies recorded' is not 'no known allergies' — say which it is
    astat = p["allergies_status"] or "documented"
    _field(hid, "patient", "allergies", "Allergies",
           p["allergies"] + ("" if astat == "documented" else f"  [{astat}]"),
           f"patients/{pid}", True)
    if p["weight_kg"]:
        stale = (not p["weight_at"]) or (
            datetime.fromtimestamp(p["weight_at"]).date()
            < datetime.fromtimestamp(now()).date())
        _field(hid, "patient", "weight", "Weight",
               f"{p['weight_kg']} kg ({p['weight_source'] or 'source not recorded'})"
               + ("  [STALE — not weighed today]" if stale else ""),
               f"patients/{pid}", True)
    _field(hid, "patient", "vitals", "Latest vitals",
           (f"HR {v['hr']}, BP {v['bp']}, RR {v['rr']}, T {v['temp']}, SpO2 {v['spo2']}%"
            if v else None),
           f"vitals @ {hhmm(v['t'])}" if v else "no vitals recorded", True)
    labs = rows("SELECT * FROM labs WHERE patient_id=? AND status='resulted' ORDER BY resulted_at DESC", (pid,))
    _field(hid, "patient", "labs", "Recent labs",
           "; ".join(f"{l['name']} {l['value']}{' (' + l['flag'] + ')' if l['flag'] else ''}" for l in labs) or None,
           f"labs ({len(labs)} resulted)", True)
    meds_given = rows("SELECT * FROM meds WHERE patient_id=? AND status='given'", (pid,))
    _field(hid, "patient", "meds_given", "Meds given this shift",
           "; ".join(f"{m['name']} {m['dose']} at {hhmm(m['given_at'])}" for m in meds_given) or "none",
           f"MAR ({len(meds_given)} administered)")
    _field(hid, "patient", "sender_contact", "Sender contact",
           one("SELECT name FROM staff WHERE id=?", (giver,))["name"] + " · ext 4412",
           f"staff/{giver}", True)
    # Deliberately unsourced: shows the missing-field block (FR-1.3).
    _field(hid, "patient", "baseline_weight", "Today's weight", None,
           "not in records — enter manually", True)

    due = rows("SELECT * FROM meds WHERE patient_id=? AND status IN ('due','missed') ORDER BY due_at", (pid,))
    _field(hid, "action", "meds_due", "Meds due or missed",
           "; ".join(f"{m['name']} {m['dose']} {m['route']} {rel(m['due_at'])}"
                     f"{' — MISSED' if m['status'] == 'missed' else ''}" for m in due) or "none",
           f"MAR ({len(due)} outstanding)", True)
    orders = rows("SELECT * FROM orders WHERE patient_id=? AND status='open'", (pid,))
    _field(hid, "action", "open_orders", "Open orders",
           "; ".join(o["text"] for o in orders) or "none", f"orders ({len(orders)} open)")

    pending = rows("SELECT * FROM labs WHERE patient_id=? AND status='pending'", (pid,))
    conting = [f"{l['name']} result pending — chase it" for l in pending]
    if sev != "stable":
        conting.append(f"if {sev} worsens, escalate to the on-call provider")
    notes = rows("SELECT * FROM notes WHERE patient_id=? AND abnormal=1", (pid,))
    conting += [f"watch: {n['text']}" for n in notes]
    if (p["allergies_status"] or "documented") != "documented":
        conting.append("allergy history has NOT been taken — confirm before any new drug")
    vtc = rows("SELECT * FROM vent_settings WHERE patient_id=? ORDER BY t", (pid,))
    for a, bb in zip(vtc, vtc[1:]):
        if bb["peep"] != a["peep"] and "no provider contact" in (bb["note"] or ""):
            conting.append(f"PEEP raised {a['peep']}→{bb['peep']} at {hhmm(bb['t'])} "
                           "with no provider contact recorded — confirm on rounds")
    _field(hid, "awareness", "contingencies", "Situation awareness and contingencies",
           "; ".join(conting) or "none flagged", "pending labs, abnormal notes", True)

    _field(hid, "synthesis", "prompt", "Synthesis prompt",
           "Receiver reads back severity, the action list and the contingencies.", "I-PASS", True)

    _build_safety(hid, pid, p)
    _refresh_status(hid)
    emit("handoff", f"Draft built for {p['name']} ({p['room']}) — {hid}",
         handoff=hid, patient=pid, severity=sev)
    audit(giver, "handoff.draft", hid)
    return get(hid)


def _build_safety(hid, pid, p):
    _field(hid, "safety", "fall_risk", "Fall risk",
           f"Morse {p['fall_score']} — {'HIGH' if p['fall_score'] >= 13 else 'moderate' if p['fall_score'] >= 7 else 'low'}",
           f"patients/{pid}", True)
    _field(hid, "safety", "fall_interventions", "Fall interventions",
           p["fall_interventions"], f"patients/{pid}", True)
    _field(hid, "safety", "isolation", "Isolation", p["isolation"], f"patients/{pid}", True)
    al = rows("SELECT * FROM alarm_events WHERE patient_id=? ORDER BY t", (pid,))
    _field(hid, "safety", "alarm_changes", "Alarm changes this shift",
           "; ".join(f"{hhmm(a['t'])} {a['detail']} (by {a['actor']})" for a in al) or "none",
           f"monitor log ({len(al)} events)", True)
    if al:
        emit("safety", f"{len(al)} alarm changes pinned to {hid} — "
                       f"{al[-1]['detail']}", handoff=hid, count=len(al))

    # Restraints as events, not one value: a removal mid-shift has to carry over.
    rst = rows("SELECT * FROM restraint_events WHERE patient_id=? ORDER BY t", (pid,))
    if rst:
        last = rst[-1]
        _field(hid, "safety", "restraints", "Restraints this shift",
               "; ".join(f"{hhmm(r['t'])} {r['action']} ({r['kind']}) — {r['reason']} "
                         f"[{r['actor']}]" for r in rst)
               + f"  → currently {last['action'].upper()} since {hhmm(last['t'])}",
               f"restraint_events ({len(rst)} events)", True)
        emit("safety", f"{hid}: restraints {last['action']} at {hhmm(last['t'])} "
                       f"— carried into the handoff", handoff=hid)
    else:
        _field(hid, "safety", "restraints", "Restraints", p["restraints"],
               f"patients/{pid}", True)

    sed = rows("SELECT * FROM sedation WHERE patient_id=? ORDER BY t DESC LIMIT 1", (pid,))
    if sed:
        s0 = sed[0]
        _field(hid, "safety", "sedation", "Sedation",
               f"{s0['drug']} {s0['dose']}, RASS {s0['rass']} at {hhmm(s0['t'])}"
               + (f" — {s0['note']}" if s0["note"] else ""),
               "sedation log", True)

    dev = rows("""SELECT * FROM devices WHERE patient_id=? AND status='in situ'
                  ORDER BY kind""", (pid,))
    if dev:
        parts = []
        for d in dev:
            obs = rows("SELECT * FROM device_obs WHERE device_id=? ORDER BY t DESC LIMIT 1",
                       (d["id"],))
            parts.append(f"{d['kind'].replace('_', ' ')} ({d['site']}, placed "
                         f"{hhmm(d['inserted_at'])} by {d['inserted_by']})"
                         + (f": {obs[0]['detail']}" if obs else ""))
        _field(hid, "safety", "devices", "Lines, tubes and airway",
               "; ".join(parts), f"devices ({len(dev)} in situ)", True)

    vt = rows("SELECT * FROM vent_settings WHERE patient_id=? ORDER BY t", (pid,))
    if vt:
        cur = vt[-1]
        changes = [f"{hhmm(b['t'])} PEEP {a['peep']}→{b['peep']}"
                   for a, b in zip(vt, vt[1:]) if a["peep"] != b["peep"]]
        _field(hid, "safety", "ventilation", "Ventilation",
               f"{cur['mode']}, PEEP {cur['peep']}, FiO2 {cur['fio2']}%, "
               f"rate {cur['rate']}, Vt {cur['tidal_volume']}"
               + (f"  — CHANGED: {'; '.join(changes)}" if changes else ""),
               f"vent_settings ({len(vt)} rows)", True)
        if changes:
            emit("safety", f"{hid}: ventilator changed this shift — {'; '.join(changes)}",
                 handoff=hid)

    wd = rows("SELECT * FROM wounds WHERE patient_id=?", (pid,))
    if wd:
        _field(hid, "safety", "wounds", "Wounds and dressings",
               "; ".join(f"{w['site']}: {w['description']}, {w['dressing'] or 'no dressing'}"
                         f" (last changed {hhmm(w['last_changed_at'])} by {w['changed_by']})"
                         for w in wd), f"wounds ({len(wd)} sites)", True)


# ---------------------------------------------------------------- status rules

def missing_fields(hid):
    return [f["label"] for f in rows(
        "SELECT * FROM handoff_fields WHERE handoff_id=? AND required=1 AND (value IS NULL OR value='')",
        (hid,))]


def _refresh_status(hid):
    h = one("SELECT * FROM handoffs WHERE id=?", (hid,))
    if h["status"] in ("in_progress", "acknowledged", "closed"):
        return h["status"]
    miss = missing_fields(hid)
    status = "drafting" if miss else "ready"
    ready_at = h["ready_at"] or (now() if status == "ready" else None)
    write("UPDATE handoffs SET status=?, ready_at=? WHERE id=?", (status, ready_at, hid))
    if status == "ready" and not h["ready_at"]:
        emit("handoff", f"{hid} is READY — all required fields filled", handoff=hid)
    return status


# ---------------------------------------------------------------- read / edit

def get(hid):
    h = one("SELECT * FROM handoffs WHERE id=?", (hid,))
    if not h:
        raise HTTPException(404, f"no handoff {hid}")
    p = one("SELECT * FROM patients WHERE id=?", (h["patient_id"],))
    fields = rows("SELECT * FROM handoff_fields WHERE handoff_id=?", (hid,))
    by_section = {}
    for f in fields:
        by_section.setdefault(f["section"], []).append({
            "key": f["key"], "label": f["label"], "value": f["value"],
            "source": f["source"], "required": bool(f["required"]),
            "missing": f["required"] and not f["value"],
            "filled_by": f["edited_by"] or f["filled_by"],
        })
    from . import tasks as tasks_mod
    acks = rows("SELECT * FROM acks WHERE handoff_id=?", (hid,))
    return {
        "id": hid, "patient": {"id": p["id"], "name": p["name"], "room": p["room"]},
        "giver": h["giver_id"], "receiver": h["receiver_id"], "status": h["status"],
        "ward_time": hhmm(now()), "ready_at": hhmm(h["ready_at"]),
        "closed_at": hhmm(h["closed_at"]),
        "missing_required": missing_fields(hid),
        "safety_block": by_section.pop("safety", []),
        "ipass": {s: by_section.get(s, []) for s in SECTIONS},
        "action_list": tasks_mod.for_patient(h["patient_id"]),
        "acknowledged": [{"kind": a["kind"], "ref": a["ref"], "at": hhmm(a["t"])} for a in acks],
        "readback": h["readback"],
    }


class FieldEdit(BaseModel):
    value: str
    actor: str = "N-01"


@router.post("/{pid}/draft")
def post_draft(pid: str, giver: str = "N-01", receiver: str = "N-02"):
    return build_draft(pid, giver, receiver)


@router.get("")
def list_handoffs():
    out = []
    for h in rows("SELECT * FROM handoffs ORDER BY created_at"):
        p = one("SELECT * FROM patients WHERE id=?", (h["patient_id"],))
        out.append({"id": h["id"], "patient": p["name"], "room": p["room"],
                    "status": h["status"], "missing": missing_fields(h["id"])})
    return out


@router.get("/{hid}")
def get_handoff(hid: str):
    return get(hid)


@router.patch("/{hid}/fields/{key}")
def edit_field(hid: str, key: str, body: FieldEdit):
    f = one("SELECT * FROM handoff_fields WHERE handoff_id=? AND key=?", (hid, key))
    if not f:
        raise HTTPException(404, f"no field {key}")
    write("UPDATE handoff_fields SET value=?, edited_by=?, source=? WHERE id=?",
          (body.value, body.actor, f"entered by {body.actor}", f["id"]))
    emit("handoff", f"{hid}: {f['label']} set to \"{body.value}\" by {body.actor}",
         handoff=hid, field=key)
    audit(body.actor, "handoff.edit", f"{hid}/{key}")
    _refresh_status(hid)
    return get(hid)


# ---------------------------------------------------------------- read-back (F2)

class Readback(BaseModel):
    text: str
    actor: str = "N-02"


def _expected(hid):
    """What the receiver must say back: every action item plus each contingency."""
    h = one("SELECT * FROM handoffs WHERE id=?", (hid,))
    from . import tasks as tasks_mod
    items = [{"kind": "task", "ref": str(t["id"]), "text": t["text"]}
             for t in tasks_mod.for_patient(h["patient_id"], raw=True)]
    cf = one("SELECT * FROM handoff_fields WHERE handoff_id=? AND key='contingencies'", (hid,))
    if cf and cf["value"]:
        items += [{"kind": "contingency", "ref": f"c{i}", "text": c.strip()}
                  for i, c in enumerate(cf["value"].split(";")) if c.strip()]
    return items


# STUB — the agent layer replaces this with semantic comparison.
# Mock rule: an item counts as covered if a distinctive word from it appears in the read-back.
STOP = {"the", "and", "for", "with", "not", "yet", "due", "out", "any", "all", "its",
        "mg", "ml", "iv", "po", "sc", "min", "it", "in", "on", "to", "a", "an", "if"}


def _covered(item_text, said):
    said = said.lower()
    words = [w.strip(",.;:()%").lower() for w in item_text.split()]
    keys = [w for w in words if len(w) > 3 and w not in STOP]
    return any(k in said for k in keys[:6])


@router.post("/{hid}/readback")
def post_readback(hid: str, body: Readback):
    h = one("SELECT * FROM handoffs WHERE id=?", (hid,))
    if not h:
        raise HTTPException(404, f"no handoff {hid}")
    if h["status"] == "drafting":
        raise HTTPException(409, {"error": "handoff not ready", "missing": missing_fields(hid)})
    write("UPDATE handoffs SET status='in_progress', started_at=COALESCE(started_at,?), readback=? WHERE id=?",
          (now(), body.text, hid))
    exp = _expected(hid)
    gaps = [i for i in exp if not _covered(i["text"], body.text)]
    emit("handoff", f"{hid}: read-back from {body.actor} — {len(exp) - len(gaps)}/{len(exp)} items covered, "
                    f"{len(gaps)} gap(s)", handoff=hid, gaps=len(gaps))
    for g in gaps:
        emit("safety", f"GAP in {hid}: \"{g['text']}\" was not said back", handoff=hid, ref=g["ref"])
    audit(body.actor, "handoff.readback", f"{hid} gaps={len(gaps)}")
    return {"handoff": hid, "covered": [i for i in exp if i not in gaps], "gaps": gaps,
            "note": "mock keyword match — the agent layer does this semantically"}


class Ack(BaseModel):
    kind: str          # task | contingency | safety_block
    ref: str = "all"
    actor: str = "N-02"


@router.post("/{hid}/ack")
def post_ack(hid: str, body: Ack):
    write("INSERT INTO acks (handoff_id,kind,ref,actor,t) VALUES (?,?,?,?,?)",
          (hid, body.kind, body.ref, body.actor, now()))
    emit("handoff", f"{hid}: {body.actor} acknowledged {body.kind} {body.ref}", handoff=hid)
    audit(body.actor, "handoff.ack", f"{hid}/{body.kind}/{body.ref}")
    return _try_close(hid)


def _try_close(hid):
    """FR-2.3: close only when every action item, every contingency and the
    safety block are acknowledged, and no task is unowned (FR-3.3)."""
    h = one("SELECT * FROM handoffs WHERE id=?", (hid,))
    if h["status"] == "closed":
        return {"handoff": hid, "closed": True, "blockers": [],
                "closed_at": hhmm(h["closed_at"])}
    exp = _expected(hid)
    acked = {(a["kind"], a["ref"]) for a in rows("SELECT * FROM acks WHERE handoff_id=?", (hid,))}
    blockers = []
    if ("safety_block", "all") not in acked:
        blockers.append("safety block not acknowledged")
    for i in exp:
        if (i["kind"], i["ref"]) not in acked and (i["kind"], "all") not in acked:
            blockers.append(f"{i['kind']} not acknowledged: {i['text'][:48]}")
    from . import tasks as tasks_mod
    unowned = [t["text"] for t in tasks_mod.for_patient(h["patient_id"], raw=True) if not t["owner_id"]]
    blockers += [f"task has no owner: {t[:48]}" for t in unowned]

    if blockers:
        return {"handoff": hid, "closed": False, "blockers": blockers}
    write("UPDATE handoffs SET status='closed', closed_at=? WHERE id=?", (now(), hid))
    # tasks transfer to the receiver
    write("UPDATE tasks SET owner_id=? WHERE patient_id=? AND status='open'",
          (h["receiver_id"], h["patient_id"]))
    emit("handoff", f"{hid} CLOSED — care transferred {h['giver_id']} → {h['receiver_id']}",
         handoff=hid)
    audit(h["receiver_id"], "handoff.close", hid)
    return {"handoff": hid, "closed": True, "blockers": []}


@router.get("/{hid}/close-check")
def close_check(hid: str):
    return _try_close(hid)
