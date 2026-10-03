"""F5 closed-loop messaging (sent → delivered → read → responded, with re-route)
and F6 focus mode (non-urgent messages held during a handoff or med pass)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import rows, one, write, audit
from ..clock import now, hhmm, rel, MIN
from ..events import emit

router = APIRouter(prefix="/messages", tags=["messaging"])

REROUTE_MIN = 10          # FR-5.2, unit-configurable
STATES = ["draft", "sent", "delivered", "read", "responded", "rerouted"]


def _event(mid, state, actor):
    write("INSERT INTO message_events (message_id,state,t,actor) VALUES (?,?,?,?)",
          (mid, state, now(), actor))
    write("UPDATE messages SET state=? WHERE id=?", (state, mid))


def _shape(m):
    ev = rows("SELECT * FROM message_events WHERE message_id=? ORDER BY t", (m["id"],))
    return {
        "id": m["id"], "patient": m["patient_id"], "from": m["sender_id"],
        "to": m["recipient_id"], "urgency": m["urgency"], "state": m["state"],
        "sbar": {"situation": m["situation"], "background": m["background"],
                 "assessment": m["assessment"], "recommendation": m["recommendation"]}
        if m["situation"] else None,
        "body": m["body"],
        "reroute_at": hhmm(m["reroute_at"]), "reroute_rel": rel(m["reroute_at"]),
        "rerouted_to": m["rerouted_to"], "reply_to": m["reply_to"],
        "trail": [{"state": e["state"], "at": hhmm(e["t"]), "by": e["actor"]} for e in ev],
    }


class Send(BaseModel):
    message_id: int
    actor: str = "N-01"


class Plain(BaseModel):
    patient_id: str | None = None
    sender_id: str = "N-01"
    recipient_id: str = "N-02"
    body: str
    urgency: str = "routine"     # routine | urgent | code


def create_plain(b: "Plain"):
    mid = write("""INSERT INTO messages
        (patient_id,sender_id,recipient_id,urgency,state,created_at,body)
        VALUES (?,?,?,?,?,?,?)""",
        (b.patient_id, b.sender_id, b.recipient_id, b.urgency, "draft", now(), b.body))
    return mid


@router.post("")
def new_message(body: Plain):
    mid = create_plain(body)
    emit("message", f"Draft {mid} to {body.recipient_id} ({body.urgency})", message=mid)
    return _shape(one("SELECT * FROM messages WHERE id=?", (mid,)))


@router.get("")
def list_messages(state: str | None = None, to: str | None = None):
    sql, args = "SELECT * FROM messages WHERE 1=1", []
    if state:
        sql += " AND state=?"; args.append(state)
    if to:
        sql += " AND recipient_id=?"; args.append(to)
    return [_shape(m) for m in rows(sql + " ORDER BY id", tuple(args))]


@router.get("/{mid}")
def get_message(mid: int):
    m = one("SELECT * FROM messages WHERE id=?", (mid,))
    if not m:
        raise HTTPException(404, "no such message")
    return _shape(m)


@router.post("/{mid}/send")
def send(mid: int, body: Send):
    """FR-4.4: a human always presses send. Nothing here sends on its own."""
    m = one("SELECT * FROM messages WHERE id=?", (mid,))
    if not m:
        raise HTTPException(404, "no such message")
    if m["state"] != "draft":
        raise HTTPException(409, f"already {m['state']}")
    if m["situation"] and not m["recommendation"]:
        raise HTTPException(422, "SBAR needs a Recommendation — the explicit ask (FR-4.1)")

    reroute = now() + REROUTE_MIN * MIN if m["urgency"] in ("urgent", "code") else None
    write("UPDATE messages SET sent_at=?, reroute_at=? WHERE id=?", (now(), reroute, mid))
    _event(mid, "sent", body.actor)
    audit(body.actor, "message.send", str(mid))

    # F6: hold non-urgent traffic if the recipient is in focus mode
    if m["urgency"] == "routine" and in_focus(m["recipient_id"]):
        write("INSERT INTO held (message_id,staff_id) VALUES (?,?)", (mid, m["recipient_id"]))
        emit("focus", f"Message {mid} HELD — {m['recipient_id']} is in focus mode",
             message=mid)
        return _shape(one("SELECT * FROM messages WHERE id=?", (mid,)))

    _event(mid, "delivered", "system")
    tag = "URGENT " if m["urgency"] != "routine" else ""
    extra = f", re-route {rel(reroute)}" if reroute else ""
    emit("message", f"{tag}message {mid} delivered to {m['recipient_id']}{extra}", message=mid)
    return _shape(one("SELECT * FROM messages WHERE id=?", (mid,)))


@router.post("/{mid}/read")
def mark_read(mid: int, actor: str = "D-01"):
    _event(mid, "read", actor)
    emit("message", f"Message {mid} READ by {actor}", message=mid)
    return _shape(one("SELECT * FROM messages WHERE id=?", (mid,)))


class Reply(BaseModel):
    body: str
    actor: str = "D-01"


@router.post("/{mid}/reply")
def reply(mid: int, body: Reply):
    m = one("SELECT * FROM messages WHERE id=?", (mid,))
    if not m:
        raise HTTPException(404, "no such message")
    rid = write("""INSERT INTO messages
        (patient_id,sender_id,recipient_id,urgency,state,created_at,body,reply_to)
        VALUES (?,?,?,?,?,?,?,?)""",
        (m["patient_id"], body.actor, m["sender_id"], "routine", "delivered",
         now(), body.body, mid))
    _event(rid, "delivered", body.actor)
    _event(mid, "responded", body.actor)
    write("UPDATE messages SET reroute_at=NULL WHERE id=?", (mid,))
    emit("message", f"{body.actor} responded to {mid}: \"{body.body[:48]}\"",
         message=mid, reply=rid)
    audit(body.actor, "message.reply", str(mid))
    return {"original": _shape(one("SELECT * FROM messages WHERE id=?", (mid,))),
            "reply": _shape(one("SELECT * FROM messages WHERE id=?", (rid,)))}


def check_reroute():
    """FR-5.2: unanswered urgent message → backup provider + charge nurse."""
    due = rows("""SELECT * FROM messages WHERE reroute_at IS NOT NULL AND reroute_at < ?
                  AND state IN ('sent','delivered','read')""", (now(),))
    for m in due:
        backup = one("SELECT * FROM staff WHERE backup_for=?", (m["recipient_id"],))
        to = backup["id"] if backup else "C-01"
        write("UPDATE messages SET rerouted_to=?, reroute_at=NULL, recipient_id=? WHERE id=?",
              (to, to, m["id"]))
        _event(m["id"], "rerouted", "system")
        _event(m["id"], "delivered", "system")
        emit("message", f"NO RESPONSE in {REROUTE_MIN}m — message {m['id']} re-routed "
                        f"{m['recipient_id']} → {to}, charge nurse alerted",
             message=m["id"], rerouted_to=to)
        audit("system", "message.reroute", f"{m['id']}->{to}")
    return len(due)


# ------------------------------------------------------------------ F6 focus mode

focus_router = APIRouter(prefix="/focus", tags=["focus"])


def in_focus(staff_id):
    return one("SELECT * FROM focus WHERE staff_id=? AND ended_at IS NULL", (staff_id,)) is not None


class FocusStart(BaseModel):
    staff_id: str
    reason: str = "handoff"       # handoff | med_pass


@focus_router.post("/start")
def start_focus(body: FocusStart):
    if in_focus(body.staff_id):
        raise HTTPException(409, "already in focus mode")
    write("INSERT INTO focus (staff_id,reason,started_at) VALUES (?,?,?)",
          (body.staff_id, body.reason, now()))
    emit("focus", f"{body.staff_id} entered FOCUS MODE ({body.reason}) — "
                  f"routine messages held, urgent and code break through", staff=body.staff_id)
    audit(body.staff_id, "focus.start", body.reason)
    return {"staff": body.staff_id, "focus": body.reason, "since": hhmm(now())}


@focus_router.post("/end")
def end_focus(staff_id: str):
    f = one("SELECT * FROM focus WHERE staff_id=? AND ended_at IS NULL", (staff_id,))
    if not f:
        raise HTTPException(404, "not in focus mode")
    write("UPDATE focus SET ended_at=? WHERE id=?", (now(), f["id"]))
    heldm = rows("""SELECT h.message_id FROM held h WHERE h.staff_id=? AND h.released=0""",
                 (staff_id,))
    digest = []
    for h in heldm:
        _event(h["message_id"], "delivered", "system")
        write("UPDATE held SET released=1 WHERE message_id=?", (h["message_id"],))
        m = one("SELECT * FROM messages WHERE id=?", (h["message_id"],))
        digest.append({"id": m["id"], "from": m["sender_id"], "body": m["body"]})
    emit("focus", f"{staff_id} left focus mode — digest of {len(digest)} held message(s) delivered",
         staff=staff_id, count=len(digest))
    audit(staff_id, "focus.end", f"digest={len(digest)}")
    return {"staff": staff_id, "digest": digest}


@focus_router.get("")
def focus_status():
    return [{"staff": f["staff_id"], "reason": f["reason"], "since": hhmm(f["started_at"])}
            for f in rows("SELECT * FROM focus WHERE ended_at IS NULL")]
