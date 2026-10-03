"""F3 carry-over task list: auto-derived from records, one owner each, overdue alerts."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import rows, one, write, audit
from ..clock import now, hhmm, rel, MIN
from ..events import emit

router = APIRouter(prefix="/tasks", tags=["tasks"])


def derive(pid):
    """FR-3.1: pull carry-over work out of the records. Idempotent by task text."""
    have = {t["text"] for t in rows("SELECT text FROM tasks WHERE patient_id=?", (pid,))}
    made = []

    for m in rows("""SELECT * FROM meds WHERE patient_id=? AND status IN ('due','missed')
                     AND due_at < ?""", (pid, now() + 2 * 3600)):
        txt = (f"{'MISSED: ' if m['status'] == 'missed' else ''}"
               f"Give {m['name']} {m['dose']} {m['route']} (due {hhmm(m['due_at'])})")
        if txt not in have:
            made.append((txt, m["due_at"], "auto:med"))

    for l in rows("SELECT * FROM labs WHERE patient_id=? AND status='pending'", (pid,)):
        txt = f"Chase pending {l['name']} result"
        if txt not in have:
            made.append((txt, now() + 60 * MIN, "auto:lab"))

    for o in rows("SELECT * FROM orders WHERE patient_id=? AND status='open'", (pid,)):
        txt = f"Open order: {o['text']}"
        if txt not in have:
            made.append((txt, now() + 120 * MIN, "auto:order"))

    for txt, due, origin in made:
        write("""INSERT INTO tasks (patient_id,handoff_id,text,owner_id,due_at,status,origin)
                 VALUES (?,?,?,?,?,?,?)""", (pid, None, txt, None, due, "open", origin))
    if made:
        emit("task", f"{len(made)} carry-over task(s) derived for {pid}",
             patient=pid, count=len(made))
    return len(made)


def _shape(t):
    overdue = t["status"] == "open" and t["due_at"] < now()
    return {"id": t["id"], "text": t["text"], "owner": t["owner_id"],
            "due": hhmm(t["due_at"]), "due_rel": rel(t["due_at"]),
            "status": t["status"], "origin": t["origin"],
            "overdue": overdue, "unowned": not t["owner_id"]}


def for_patient(pid, raw=False):
    ts = rows("SELECT * FROM tasks WHERE patient_id=? AND status!='done' ORDER BY due_at", (pid,))
    return ts if raw else [_shape(t) for t in ts]


class NewTask(BaseModel):
    patient_id: str
    text: str
    owner_id: str | None = None
    due_in_min: int = 60
    actor: str = "N-01"


class Assign(BaseModel):
    owner_id: str
    actor: str = "N-01"


@router.get("")
def list_tasks(patient_id: str | None = None, owner: str | None = None):
    sql, args = "SELECT * FROM tasks WHERE status!='done'", []
    if patient_id:
        sql += " AND patient_id=?"; args.append(patient_id)
    if owner:
        sql += " AND owner_id=?"; args.append(owner)
    return [_shape(t) for t in rows(sql + " ORDER BY due_at", tuple(args))]


@router.post("/derive/{pid}")
def post_derive(pid: str):
    n = derive(pid)
    return {"patient": pid, "created": n, "tasks": for_patient(pid)}


@router.post("")
def add_task(body: NewTask):
    tid = write("""INSERT INTO tasks (patient_id,handoff_id,text,owner_id,due_at,status,origin)
                   VALUES (?,?,?,?,?,?,?)""",
                (body.patient_id, None, body.text, body.owner_id,
                 now() + body.due_in_min * MIN, "open", f"manual:{body.actor}"))
    emit("task", f"{body.actor} added task for {body.patient_id}: {body.text}", task=tid)
    audit(body.actor, "task.add", body.text)
    return _shape(one("SELECT * FROM tasks WHERE id=?", (tid,)))


@router.post("/{tid}/assign")
def assign(tid: int, body: Assign):
    t = one("SELECT * FROM tasks WHERE id=?", (tid,))
    if not t:
        raise HTTPException(404, "no such task")
    write("UPDATE tasks SET owner_id=? WHERE id=?", (body.owner_id, tid))
    emit("task", f"Task {tid} assigned to {body.owner_id} — {t['text'][:50]}", task=tid)
    audit(body.actor, "task.assign", f"{tid}->{body.owner_id}")
    return _shape(one("SELECT * FROM tasks WHERE id=?", (tid,)))


@router.post("/{tid}/done")
def complete(tid: int, actor: str = "N-02"):
    t = one("SELECT * FROM tasks WHERE id=?", (tid,))
    if not t:
        raise HTTPException(404, "no such task")
    write("UPDATE tasks SET status='done' WHERE id=?", (tid,))
    emit("task", f"{actor} completed task {tid} — {t['text'][:50]}", task=tid)
    audit(actor, "task.done", str(tid))
    return {"id": tid, "status": "done"}


def check_overdue():
    """FR-3.4: 30 min past due → notify owner and charge nurse, once."""
    late = rows("""SELECT * FROM tasks WHERE status='open' AND escalated=0
                   AND due_at < ?""", (now() - 30 * MIN,))
    for t in late:
        write("UPDATE tasks SET escalated=1 WHERE id=?", (t["id"],))
        who = t["owner_id"] or "unassigned"
        emit("task", f"OVERDUE 30m — task {t['id']} ({t['text'][:46]}) → {who} + charge nurse",
             task=t["id"], owner=who)
    return len(late)
