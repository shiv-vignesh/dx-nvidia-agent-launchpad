"""NemoClaw / OpenClaw-facing tool surface.

The agent layer is NOT built here. This is the seam it plugs into:

  GET  /agent/tools        → OpenAI-style `tools[]` (JSON Schema), paste straight into
                             a /v1/chat/completions request
  POST /agent/call         → run one tool, get back a compact string ready to drop into
                             a {"role":"tool", tool_call_id, content} message
  GET  /agent/inference-points → the six places a model is actually needed, with the
                             sample response each one would return

Two rules from the repo's own onboarding are honoured here (docs/onboarding/00-agents-101.md):
  * **Few tools, tight descriptions** — five, not fifteen. Fewer tools select better.
  * **Summarize, never dump** — every result is capped and counted. A 4,000-row tool
    result is re-prefilled on every subsequent turn of the loop.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .db import rows, one, write, audit
from .clock import now, hhmm, rel

router = APIRouter(prefix="/agent", tags=["agent"])

CAP = 1200          # characters per tool result — the prefill discipline, enforced


def _cap(text: str) -> dict:
    """Cap a tool result and report its cost. Agent loops re-prefill this every turn."""
    truncated = len(text) > CAP
    body = text[:CAP] + ("\n…[truncated]" if truncated else "")
    return {"content": body, "approx_tokens": len(body) // 4, "truncated": truncated}


# --------------------------------------------------------------------- tools

TOOLS = [
    {"type": "function", "function": {
        "name": "get_patient_snapshot",
        "description": "Compact clinical snapshot for one patient: demographics, code status, "
                       "allergies, latest vitals with trend direction, flagged and pending labs, "
                       "meds due or missed, and safety status. Summarized, not raw rows.",
        "parameters": {"type": "object", "required": ["patient_id"], "properties": {
            "patient_id": {"type": "string", "description": "e.g. P-101"}}}}},
    {"type": "function", "function": {
        "name": "get_handoff_draft",
        "description": "The current I-PASS handoff draft: every field with the record it came "
                       "from, which required fields are still empty, and the read-back if given.",
        "parameters": {"type": "object", "required": ["handoff_id"], "properties": {
            "handoff_id": {"type": "string", "description": "e.g. HO-101-a1b2"}}}}},
    {"type": "function", "function": {
        "name": "list_open_items",
        "description": "Everything outstanding for a patient: open tasks with owner and due "
                       "time, pending lab results, and meds due or missed. Use before judging "
                       "whether a handoff omitted something.",
        "parameters": {"type": "object", "required": ["patient_id"], "properties": {
            "patient_id": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "search_notes",
        "description": "Search free-text nursing notes, aide observations and family concerns "
                       "for a patient. Returns matching notes only, newest first.",
        "parameters": {"type": "object", "required": ["patient_id"], "properties": {
            "patient_id": {"type": "string"},
            "query": {"type": "string", "description": "keyword, e.g. 'confusion'. Omit for all."}}}}},
    {"type": "function", "function": {
        "name": "get_care_team",
        "description": "Who is looking after a patient right now, and who to page: the RN on "
                       "shift, the aide, the charge nurse, the on-call provider and their "
                       "backup. Use before composing an escalation.",
        "parameters": {"type": "object", "required": ["patient_id"], "properties": {
            "patient_id": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "submit_analysis",
        "description": "Return the model's finding to the system: a gap list, an urgency "
                       "ranking, or a drafted summary. Recorded as a PROPOSAL for a caregiver "
                       "to confirm — this never changes care or sends anything.",
        "parameters": {"type": "object", "required": ["handoff_id", "kind", "finding"],
                       "properties": {
                           "handoff_id": {"type": "string"},
                           "kind": {"type": "string",
                                    "enum": ["readback_gaps", "urgency_ranking",
                                             "inconsistency", "summary"]},
                           "finding": {"type": "string",
                                       "description": "The finding. Cite the record behind it — "
                                                      "a finding with no evidence is rejected."}}}}},
]


@router.get("/tools")
def get_tools():
    """Paste this array straight into the `tools` field of a chat-completions request."""
    return {"tools": TOOLS, "tool_choice": "auto",
            "note": "OpenAI function-calling shape. Results are capped at "
                    f"{CAP} chars — tool output is re-prefilled every loop turn."}


# --------------------------------------------------------------------- dispatch

def _snapshot(pid):
    p = one("SELECT * FROM patients WHERE id=?", (pid,))
    if not p:
        return f"No patient {pid}."
    v = rows("SELECT * FROM vitals WHERE patient_id=? ORDER BY t DESC LIMIT 3", (pid,))
    if not v:
        return f"{p['name']}, {p['age']}y, room {p['room']}. {p['dx']}. No vitals recorded yet."
    trend = "no prior reading"
    if len(v) >= 2:
        d = v[0]["spo2"] - v[1]["spo2"]
        trend = f"SpO2 {'falling' if d < 0 else 'rising' if d > 0 else 'flat'} ({d:+d}%)"
    labs = rows("""SELECT * FROM labs WHERE patient_id=? AND (flag IS NOT NULL OR status='pending')
                   ORDER BY resulted_at DESC LIMIT 5""", (pid,))
    meds = rows("SELECT * FROM meds WHERE patient_id=? AND status IN ('due','missed')", (pid,))
    al = rows("SELECT * FROM alarm_events WHERE patient_id=? ORDER BY t DESC LIMIT 3", (pid,))
    return "\n".join([
        f"{p['name']}, {p['age']}y, room {p['room']}. {p['dx']}.",
        f"Code status {p['code_status']}. Allergies: {p['allergies']}. Isolation: {p['isolation']}.",
        f"Latest vitals {hhmm(v[0]['t'])}: HR {v[0]['hr']}, BP {v[0]['bp']}, RR {v[0]['rr']}, "
        f"T {v[0]['temp']}, SpO2 {v[0]['spo2']}% — {trend}.",
        "Labs: " + ("; ".join(
            f"{l['name']} {l['value'] or 'PENDING'}{' ' + l['flag'] if l['flag'] else ''}"
            for l in labs) or "none flagged"),
        "Meds outstanding: " + ("; ".join(
            f"{m['name']} {m['dose']} {m['status']} ({hhmm(m['due_at'])})" for m in meds) or "none"),
        f"Fall risk Morse {p['fall_score']}; {p['fall_interventions']}.",
        "Alarm changes: " + ("; ".join(f"{hhmm(a['t'])} {a['detail']}" for a in al) or "none"),
    ] + _icu_lines(pid, p))


def _icu_lines(pid, p):
    """Only emitted when present, so a med-surg snapshot stays short."""
    out = []
    pod = None
    if p["surgery_on"]:
        from .modules.directory import post_op_day
        pod = post_op_day(p["surgery_on"])
    if pod is not None:
        out.append(f"Post-op day {pod} (surgery {p['surgery_on']}).")
    if p["weight_kg"]:
        stale = " STALE, not weighed today" if not p["weight_at"] else ""
        out.append(f"Weight {p['weight_kg']} kg ({p['weight_source']}).{stale}")
    if (p["allergies_status"] or "documented") != "documented":
        out.append("ALLERGY HISTORY NOT DOCUMENTED — 'none recorded' is not 'none known'.")
    sed = rows("SELECT * FROM sedation WHERE patient_id=? ORDER BY t DESC LIMIT 1", (pid,))
    if sed:
        out.append(f"Sedation: {sed[0]['drug']} {sed[0]['dose']}, RASS {sed[0]['rass']}.")
    vt = rows("SELECT * FROM vent_settings WHERE patient_id=? ORDER BY t", (pid,))
    if vt:
        ch = [f"{hhmm(x['t'])} PEEP {w['peep']}→{x['peep']}"
              for w, x in zip(vt, vt[1:]) if w["peep"] != x["peep"]]
        out.append(f"Vent: {vt[-1]['mode']}, PEEP {vt[-1]['peep']}, FiO2 {vt[-1]['fio2']}%."
                   + (f" Changed: {'; '.join(ch)}." if ch else ""))
    rst = rows("SELECT * FROM restraint_events WHERE patient_id=? ORDER BY t DESC LIMIT 1", (pid,))
    if rst:
        out.append(f"Restraints {rst[0]['action']} at {hhmm(rst[0]['t'])} "
                   f"({rst[0]['reason']}).")
    dev = rows("SELECT * FROM devices WHERE patient_id=? AND status='in situ'", (pid,))
    if dev:
        out.append("Devices: " + "; ".join(f"{d['kind']} {d['site']}" for d in dev) + ".")
    wd = rows("SELECT * FROM wounds WHERE patient_id=?", (pid,))
    if wd:
        out.append("Wounds: " + "; ".join(f"{w['site']} {w['description']}" for w in wd) + ".")
    return out


def _draft(hid):
    h = one("SELECT * FROM handoffs WHERE id=?", (hid,))
    if not h:
        return f"No handoff {hid}."
    fs = rows("SELECT * FROM handoff_fields WHERE handoff_id=?", (hid,))
    lines = [f"Handoff {hid} — status {h['status']}, {h['giver_id']} → {h['receiver_id']}."]
    for f in fs:
        val = f["value"] or "** EMPTY **"
        lines.append(f"[{f['section']}] {f['label']}: {val}  (source: {f['source']})")
    miss = [f["label"] for f in fs if f["required"] and not f["value"]]
    lines.append("Missing required: " + ("; ".join(miss) if miss else "none"))
    if h["readback"]:
        lines.append(f"Receiver said: \"{h['readback']}\"")
    return "\n".join(lines)


def _open_items(pid):
    ts = rows("SELECT * FROM tasks WHERE patient_id=? AND status!='done' ORDER BY due_at", (pid,))
    pend = rows("SELECT * FROM labs WHERE patient_id=? AND status='pending'", (pid,))
    meds = rows("SELECT * FROM meds WHERE patient_id=? AND status IN ('due','missed')", (pid,))
    lines = [f"Open items for {pid}:"]
    for t in ts:
        lines.append(f"- TASK {t['id']}: {t['text']} | owner {t['owner_id'] or 'UNASSIGNED'} "
                     f"| due {hhmm(t['due_at'])} ({rel(t['due_at'])})")
    for l in pend:
        lines.append(f"- PENDING LAB: {l['name']} — no result yet")
    for m in meds:
        lines.append(f"- MED {m['status'].upper()}: {m['name']} {m['dose']} due {hhmm(m['due_at'])}")
    return "\n".join(lines) if len(lines) > 1 else f"Nothing outstanding for {pid}."


def _notes(pid, query=None):
    ns = rows("SELECT * FROM notes WHERE patient_id=? ORDER BY t DESC", (pid,))
    if query:
        ns = [n for n in ns if query.lower() in n["text"].lower()]
    if not ns:
        return f"No notes for {pid}" + (f" matching '{query}'." if query else ".")
    return "\n".join(f"{hhmm(n['t'])} [{n['kind']}] {n['author']}: {n['text']}"
                     f"{'  <ABNORMAL>' if n['abnormal'] else ''}" for n in ns)


def _submit(hid, kind, finding):
    if not one("SELECT * FROM handoffs WHERE id=?", (hid,)):
        return f"No handoff {hid} — nothing recorded."
    write("INSERT INTO acks (handoff_id,kind,ref,actor,t) VALUES (?,?,?,?,?)",
          (hid, f"proposal:{kind}", finding[:400], "agent", now()))
    audit("agent", f"proposal.{kind}", f"{hid}: {finding[:120]}")
    from .events import emit
    emit("safety", f"AGENT PROPOSAL ({kind}) on {hid}: {finding[:80]} — awaiting caregiver confirmation",
         handoff=hid, kind=kind)
    return (f"Recorded as a PROPOSAL on {hid}. It changes nothing until a caregiver confirms it. "
            f"Do not tell the user the action is done.")


def _care_team(pid):
    from .modules.directory import current_rn, on_shift
    p = one("SELECT * FROM patients WHERE id=?", (pid,))
    if not p:
        return f"No patient {pid}."
    rn = current_rn(pid)
    lines = [f"Care team for {p['name']} ({pid}), room {p['room']}:"]
    lines.append(f"- RN on shift: {rn['name']} ({rn['id']}), "
                 f"{hhmm(rn['shift_start'])}-{hhmm(rn['shift_end'])}" if rn
                 else "- RN on shift: NONE ASSIGNED")
    for role, label in (("aide", "Aide"), ("charge", "Charge nurse"),
                        ("provider", "Provider")):
        for s_ in rows("SELECT * FROM staff WHERE role=?", (role,)):
            if on_shift(s_):
                bk = one("SELECT * FROM staff WHERE backup_for=?", (s_["id"],))
                lines.append(f"- {label}: {s_['name']} ({s_['id']})" +
                             (f", backup {bk['name']} ({bk['id']})" if bk else ""))
    return "\n".join(lines)


DISPATCH = {
    "get_patient_snapshot": lambda a: _snapshot(a["patient_id"]),
    "get_care_team": lambda a: _care_team(a["patient_id"]),
    "get_handoff_draft": lambda a: _draft(a["handoff_id"]),
    "list_open_items": lambda a: _open_items(a["patient_id"]),
    "search_notes": lambda a: _notes(a["patient_id"], a.get("query")),
    "submit_analysis": lambda a: _submit(a["handoff_id"], a["kind"], a["finding"]),
}


class Call(BaseModel):
    name: str
    arguments: dict = {}
    tool_call_id: str | None = None


@router.post("/call")
def call_tool(body: Call):
    """Execute one tool call. The response is shaped to drop straight into the history."""
    fn = DISPATCH.get(body.name)
    if not fn:
        raise HTTPException(404, f"no tool '{body.name}'. Available: {list(DISPATCH)}")
    try:
        result = fn(body.arguments)
    except KeyError as e:
        raise HTTPException(422, f"missing required argument {e}")
    capped = _cap(result)
    return {"role": "tool", "tool_call_id": body.tool_call_id or f"call_{body.name}",
            "name": body.name, **capped}


# ------------------------------------------------------- where inference is needed

INFERENCE_POINTS = [
    {"id": "AI-1", "step": 2, "where": "Handoff draft — free-text notes",
     "today": "Nursing notes are copied into the draft verbatim; only structured records are parsed.",
     "needs_model": "Read the shift's free-text notes and turn them into I-PASS claims, "
                    "keeping a pointer to the sentence each claim came from.",
     "tools": ["get_patient_snapshot", "search_notes"],
     "sample": "Patient summary: 78y with CHF exacerbation, day 3. Increasing exertional dyspnoea "
               "documented this afternoon (note 18:10). Family at bedside asking about discharge "
               "planning — not yet addressed by the team.\n"
               "Source: nursing note 18:10, aide observation 18:25."},
    {"id": "AI-2", "step": 6, "where": "Read-back comparison",
     "today": "STUB — keyword match in modules/handoff.py. 'K+' never matches 'potassium'.",
     "needs_model": "Compare what the receiver said against the required items semantically, "
                    "so a paraphrase counts as covered and a true omission is caught.",
     "tools": ["get_handoff_draft", "submit_analysis"],
     "sample": "Covered: severity, code status, allergies, the furosemide dose.\n"
               "NOT said back (3):\n"
               "  1. Pending troponin — no result yet, needs chasing.\n"
               "  2. Potassium 3.1 (LOW) with furosemide due at 20:00 — replacement ordered.\n"
               "  3. SpO2 low limit was changed 92% → 88% at 17:50.\n"
               "Item 2 is the one I would not let pass: a low potassium plus a loop diuretic is "
               "the combination that causes the arrhythmia."},
    {"id": "AI-3", "step": 7, "where": "Urgency ranking",
     "today": "Tasks are sorted by due time only. A chart review is ranked beside a missed dose.",
     "needs_model": "Rank the outstanding items by clinical consequence, not by clock order.",
     "tools": ["list_open_items", "get_patient_snapshot", "submit_analysis"],
     "sample": "1. Potassium 3.1 before the 20:00 furosemide — arrhythmia risk. Do first.\n"
               "2. Pending troponin — chest pain was the admission complaint.\n"
               "3. Furosemide 20:00 — on time, no issue.\n"
               "4. Cardiology consult — important, but not this shift.\n"
               "Re-ordered 1 and 3: the clock says furosemide first, the physiology says potassium first."},
    {"id": "AI-4", "step": 10, "where": "SBAR composition",
     "today": "Template string assembly. Background is a data dump of rows.",
     "needs_model": "Write a Situation and Assessment a tired provider reads in ten seconds, "
                    "and propose the Recommendation the nurse can accept or change.",
     "tools": ["get_patient_snapshot", "search_notes"],
     "sample": "S: Alma Whitfield, 78, room 412-A, day 3 CHF. SpO2 has fallen 95% → 89% over four "
               "hours and she is working harder to breathe.\n"
               "B: Furosemide 40mg IV at 16:05. BNP 1840. Potassium 3.1. Troponin pending. "
               "RR up 18 → 26. DNR, no intubation.\n"
               "A: This looks like ongoing fluid overload, not responding to the morning dose.\n"
               "R (proposed): Please review within 30 minutes. I would like a chest film and a "
               "further IV furosemide order.\n"
               "— the nurse edits R and presses send; I never send."},
    {"id": "AI-5", "step": 12, "where": "Cross-source inconsistency",
     "today": "Not implemented at all. Nothing compares what was said against what is recorded.",
     "needs_model": "Catch the handoff that says 'stable, no issues' while the records disagree. "
                    "This is the check that has no deterministic version.",
     "tools": ["get_handoff_draft", "get_patient_snapshot", "submit_analysis"],
     "sample": "CONTRADICTION. The handoff says \"settled overnight, no concerns\".\n"
               "The records say: lactate 2.8 (HIGH) at 18:05, temperature 38.9, HR 102 → 110, "
               "blood culture pending.\n"
               "Three of the four sepsis screen criteria are met and the trend is upward. "
               "I would not record this patient as stable.\n"
               "Evidence: labs/lactate 18:05, vitals 18:00, notes 18:15 ('rigors')."},
    {"id": "AI-6", "step": 13, "where": "Family summary and translation",
     "today": "Template with a 3-word medical glossary. Patient language is stored but unused.",
     "needs_model": "Write the plan at a 6th-grade reading level in the patient's own language, "
                    "without dropping anything clinically material.",
     "tools": ["get_patient_snapshot"],
     "sample": "Дмитрий находится в палате 412-B. Вчера ему сделали операцию на бедре.\n"
               "Сегодня вечером: антибиотик в 20:30, обезболивающее по необходимости.\n"
               "Мы следим за тем, чтобы он безопасно вставал — используем пояс для ходьбы.\n"
               "(Russian — his recorded preferred language. English version also generated.)"},
]


@router.get("/inference-points")
def inference_points():
    return {"count": len(INFERENCE_POINTS), "points": INFERENCE_POINTS,
            "note": "Everything else in this backend is deterministic and runs without a model."}
