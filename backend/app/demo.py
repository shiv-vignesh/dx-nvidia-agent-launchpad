"""The scripted demo: one synthetic patient at a 19:00 shift change, start to finish.
POST /demo/run walks every P0 feature and returns a numbered transcript."""
import asyncio
from fastapi import APIRouter

from .db import reset_and_seed, rows, one
from .clock import hhmm, now, jump, set_speed, reset as clock_reset, status
from .events import emit, clear as clear_events
from .modules import handoff, tasks, messaging, escalation, oversight, extras

router = APIRouter(prefix="/demo", tags=["demo"])

PATIENT = "P-101"       # Alma Whitfield, CHF, the richest record
SHORT_READBACK = ("Alma in 412-A, heart failure, DNR, allergic to penicillin. "
                  "She's a watcher, got her furosemide this afternoon.")


@router.post("/reset")
def reset():
    reset_and_seed()
    clock_reset()
    clear_events()
    emit("demo", "Ward reset — 3 synthetic patients, ward clock back to 18:20")
    return {"ok": True, "clock": status()}


@router.get("/script")
def script():
    return {
        "story": "19:00 shift change on a 3-bed med-surg ward. Priya (N-01) hands "
                 "Alma Whitfield to Marcus (N-02).",
        "beats": [
            "1. Derive carry-over tasks from the MAR, labs and orders (F3)",
            "2. Build the I-PASS draft with the safety block pinned on top (F1)",
            "3. Try to start the handoff — blocked, today's weight is missing (FR-1.3)",
            "4. Priya enters the weight; the draft flips to READY",
            "5. Priya enters focus mode; a routine page is held (F6)",
            "6. Marcus reads back too little — the gaps are named (F2)",
            "7. Close is blocked: unacknowledged items and an unowned task",
            "8. Assign the task, acknowledge everything, handoff CLOSES",
            "9. Priya leaves focus mode — the held page arrives as a digest",
            "10. Marcus escalates a falling SpO2 by SBAR; send is refused with no ask (F4)",
            "11. He adds the ask and sends; the clock runs past 10 min with no reply",
            "12. The page re-routes to the backup provider (F5), who replies",
            "13. Charge board and the unit report (F8)",
        ],
        "run": "POST /demo/run",
    }


_pace = {"s": 0.8}


async def _step(log, n, title, detail=""):
    await asyncio.sleep(_pace["s"])      # beats land one at a time on the console
    emit("demo", f"STEP {n} — {title}")
    log.append({"step": n, "title": title, "detail": detail, "ward_time": hhmm(now())})


@router.post("/run")
async def run(pace: float = 0.8):
    """Play the full demo. `pace` is the real-time gap between beats, in seconds —
    set 0 for an instant run, 1.5 to narrate over the console log."""
    _pace["s"] = max(0.0, pace)
    reset_and_seed()
    clock_reset()
    clear_events()
    set_speed(60)
    log = []
    emit("demo", "=== ShiftGuard demo: 19:00 shift change, bed 412-A ===")

    await _step(log, 1, "Derive carry-over tasks")
    n = tasks.derive(PATIENT)
    log[-1]["detail"] = f"{n} tasks from MAR, pending labs and open orders"

    await _step(log, 2, "Build the I-PASS draft")
    d = handoff.build_draft(PATIENT, "N-01", "N-02")
    hid = d["id"]
    log[-1]["detail"] = (f"{hid} · severity {d['ipass']['illness'][0]['value']} · "
                         f"{len(d['safety_block'])} safety fields · "
                         f"missing {d['missing_required']}")

    await _step(log, 3, "Read-back refused while a required field is empty")
    try:
        handoff.post_readback(hid, handoff.Readback(text=SHORT_READBACK))
        log[-1]["detail"] = "unexpectedly allowed"
    except Exception as e:
        det = getattr(e, "detail", str(e))
        emit("safety", f"BLOCKED: {det}")
        log[-1]["detail"] = f"blocked — {det}"

    await _step(log, 4, "Nurse fills the missing weight")
    d = handoff.edit_field(hid, "baseline_weight",
                           handoff.FieldEdit(value="81.4 kg (bed scale)", actor="N-01"))
    log[-1]["detail"] = f"status now {d['status']}"

    await _step(log, 5, "Focus mode on; a routine page is held")
    messaging.start_focus(messaging.FocusStart(staff_id="N-01", reason="handoff"))
    m = messaging.new_message(messaging.Plain(
        sender_id="C-01", recipient_id="N-01", urgency="routine",
        body="Can you cover the 20:00 break?"))
    messaging.send(m["id"], messaging.Send(message_id=m["id"], actor="C-01"))
    held_id = m["id"]
    log[-1]["detail"] = f"message {held_id} held, not delivered"

    await _step(log, 6, "Receiver read-back — gaps named")
    rb = handoff.post_readback(hid, handoff.Readback(text=SHORT_READBACK, actor="N-02"))
    log[-1]["detail"] = (f"{len(rb['covered'])} covered, {len(rb['gaps'])} gaps: "
                         + "; ".join(g["text"][:44] for g in rb["gaps"][:3]))

    await _step(log, 7, "Close refused — nothing acknowledged, a task has no owner")
    chk = handoff.close_check(hid)
    log[-1]["detail"] = f"{len(chk['blockers'])} blockers"

    await _step(log, 8, "Assign the task, acknowledge everything, close")
    for t in tasks.list_tasks(patient_id=PATIENT):
        if t["unowned"]:
            tasks.assign(t["id"], tasks.Assign(owner_id="N-02", actor="N-02"))
    for kind in ("safety_block", "task", "contingency"):
        handoff.post_ack(hid, handoff.Ack(kind=kind, ref="all", actor="N-02"))
    chk = handoff.close_check(hid)
    log[-1]["detail"] = f"closed={chk['closed']}, blockers={chk['blockers']}"

    await _step(log, 9, "Focus mode off — held page delivered as a digest")
    dg = messaging.end_focus("N-01")
    log[-1]["detail"] = f"{len(dg['digest'])} message(s) released"

    await _step(log, 10, "SBAR drafted; send refused with no Recommendation")
    esc = escalation.draft(escalation.Draft(
        patient_id=PATIENT, sender_id="N-02", recipient_id="D-01", urgency="urgent",
        concern="SpO2 has drifted 95% → 89% over four hours and she is working harder to breathe."))
    mid = esc["id"]
    try:
        messaging.send(mid, messaging.Send(message_id=mid, actor="N-02"))
        log[-1]["detail"] = "unexpectedly sent"
    except Exception as e:
        det = getattr(e, "detail", str(e))
        emit("safety", f"BLOCKED: {det}")
        log[-1]["detail"] = f"SBAR {mid} blocked — {det}"

    await _step(log, 11, "Ask added, nurse sends")
    escalation.set_ask(mid, escalation.SetAsk(
        recommendation="Please review within 30 minutes — I want a chest film and "
                       "an order for IV furosemide."))
    sent = messaging.send(mid, messaging.Send(message_id=mid, actor="N-02"))
    log[-1]["detail"] = f"state {sent['state']}, re-route at {sent['reroute_at']}"

    await _step(log, 12, "No reply for 10 ward minutes — re-route to the backup")
    jump(11)
    await asyncio.sleep(0.2)
    messaging.check_reroute()
    tasks.check_overdue()
    after = messaging.get_message(mid)
    messaging.mark_read(mid, actor=after["to"])
    rep = messaging.reply(mid, messaging.Reply(
        body="On my way. Start 2L oxygen and get the chest film.", actor=after["to"]))
    log[-1]["detail"] = (f"re-routed to {after['rerouted_to']}, "
                         f"state now {rep['original']['state']}")

    await _step(log, 13, "Charge board and unit report")
    b = oversight.board()
    r = oversight.report()
    log[-1]["detail"] = (f"{len(b['rows'])} beds · completion {r['completion_rate']} · "
                         f"{r['audit_entries']} audit entries")

    emit("demo", "=== demo complete ===")
    return {
        "ward_time": hhmm(now()),
        "handoff": hid,
        "transcript": log,
        "board": b,
        "report": r,
        "watch": "attach to ws://<host>:8099/events for the live stream",
    }
