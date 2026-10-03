"""AI-2 — semantic read-back / narrative coverage, backed by Nemotron on the GB10.

The deterministic keyword match in modules/handoff.py returns instantly but scores real
omissions as covered (it matched "allergy history" on the word "been"). Nemotron does the
real comparison, but the brief measures ~55k reasoning chars / ~258s for the tool-driven
version, so the model never blocks the request:

  POST /handoffs/{hid}/coverage  → deterministic result NOW, model run started in background
  GET  /handoffs/{hid}/coverage  → latest state; engine flips to "nemotron" when it lands

Single-turn and tool-free on purpose: the expected items are passed inline, so the model
never needs get_handoff_draft and the run costs ~15-30s instead of ~4 minutes.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .clock import now, hhmm
from .db import one
from .events import emit
from .modules.handoff import _covered, _expected

router = APIRouter(prefix="/handoffs", tags=["handoff"])

MODEL_URL = os.environ.get("SG_MODEL_URL", "http://127.0.0.1:8001/v1")
MODEL_NAME = os.environ.get("SG_MODEL", "nemotron")
MAX_TOKENS = int(os.environ.get("SG_MAX_TOKENS", "9000"))
TIMEOUT = int(os.environ.get("SG_MODEL_TIMEOUT", "300"))

# The prompt the eval suite scored 48/50 against. Read from the file so it stays the
# single source of truth; tools/smoke.sh asserts that file matches evals/scenarios.json.
_CFG = Path(__file__).resolve().parent.parent / "integration" / "agent_config.json"
FALLBACK_PROMPT = (
    "You are a clinical handoff assistant on a hospital ward. You support nurses; you never "
    "make clinical decisions and you never act on a patient's behalf."
)


def system_prompt() -> str:
    try:
        return json.loads(_CFG.read_text())["system_prompt"]
    except Exception:
        return FALLBACK_PROMPT


_STATE: dict[str, dict] = {}
_LOCK = threading.Lock()


class Narrative(BaseModel):
    text: str
    actor: str = "N-02"


def _deterministic(hid: str, text: str) -> dict:
    exp = _expected(hid)
    gaps = [i for i in exp if not _covered(i["text"], text)]
    return {
        "covered": [i for i in exp if i not in gaps],
        "gaps": gaps,
        "engine": "deterministic",
        "status": "done",
        "note": "keyword match — not semantic",
    }


def _ask_model(items: list[dict], text: str) -> tuple[list[str], str]:
    """Returns (gap_refs, raw_content). Raises on transport or truncation."""
    listing = "\n".join(f'{i["ref"]}: {i["text"]}' for i in items)
    user = (
        "An outgoing nurse gave this spoken handoff:\n"
        f'"""\n{text}\n"""\n\n'
        "These items are on record for this patient and must be carried over:\n"
        f"{listing}\n\n"
        "For each item decide whether the handoff actually communicated it. A paraphrase "
        "counts (\"water pill\" covers furosemide). Mentioning a topic without the clinically "
        "important part does NOT count. An absent record is not a negative finding.\n"
        'Respond with ONLY JSON: {"gaps": ["<ref>", ...]} listing the refs NOT communicated. '
        "Use only refs from the list above. Never invent a ref."
    )
    body = json.dumps({
        "model": MODEL_NAME,
        "messages": [{"role": "system", "content": system_prompt()},
                     {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": MAX_TOKENS,
    }).encode()
    req = urllib.request.Request(
        f"{MODEL_URL}/chat/completions", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = json.load(r)

    choice = data["choices"][0]
    msg = choice.get("message") or {}
    content = (msg.get("content") or "").strip()
    reasoning = msg.get("reasoning") or msg.get("reasoning_content") or ""
    if choice.get("finish_reason") == "length" and not content:
        raise RuntimeError(
            f"all {MAX_TOKENS} tokens went to reasoning ({len(reasoning)} chars) — raise SG_MAX_TOKENS")

    valid = {i["ref"] for i in items}
    for m in re.finditer(r"\{.*?\}", content, re.S):
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "gaps" in obj:
            return [str(g) for g in (obj["gaps"] or []) if str(g) in valid], content
    raise RuntimeError(f"no parseable JSON in model reply: {content[:200]!r}")


def _run(hid: str, text: str) -> None:
    started = time.time()
    items = _expected(hid)
    try:
        gap_refs, _raw = _ask_model(items, text)
    except Exception as exc:                      # model down, timeout, truncation, bad JSON
        with _LOCK:
            cur = _STATE.get(hid, {})
            cur.update(status="done", model_error=str(exc)[:200])
            _STATE[hid] = cur
        emit("safety", f"{hid}: Nemotron coverage unavailable ({type(exc).__name__}) — "
                       f"deterministic result stands", handoff=hid)
        return

    gaps = [i for i in items if i["ref"] in gap_refs]
    elapsed = round(time.time() - started, 1)
    with _LOCK:
        _STATE[hid] = {
            "covered": [i for i in items if i["ref"] not in gap_refs],
            "gaps": gaps,
            "engine": "nemotron",
            "status": "done",
            "elapsed_s": elapsed,
            "note": f"semantic comparison by {MODEL_NAME} in {elapsed}s",
        }
    emit("handoff", f"{hid}: Nemotron coverage — {len(items) - len(gaps)}/{len(items)} "
                    f"communicated, {len(gaps)} gap(s) in {elapsed}s", handoff=hid)
    for g in gaps:
        emit("safety", f'GAP in {hid} (nemotron): "{g["text"]}" was not communicated',
             handoff=hid, ref=g["ref"])


@router.post("/{hid}/coverage")
def post_coverage(hid: str, body: Narrative):
    """Deterministic answer immediately; Nemotron run started in the background.

    Unlike /readback this does not mutate the handoff: the outgoing nurse re-runs it as she
    edits, and none of those runs are the receiver's formal read-back.
    """
    if not one("SELECT id FROM handoffs WHERE id=?", (hid,)):
        raise HTTPException(404, f"no handoff {hid}")
    det = _deterministic(hid, body.text)
    with _LOCK:
        _STATE[hid] = {**det, "status": "running", "ward_time": hhmm(now())}
    threading.Thread(target=_run, args=(hid, body.text), daemon=True).start()
    emit("handoff", f"{hid}: coverage check started — {len(det['gaps'])} gap(s) by keyword, "
                    f"asking {MODEL_NAME}", handoff=hid)
    return {"handoff": hid, **det, "status": "running", "model": MODEL_NAME}


@router.get("/{hid}/coverage")
def get_coverage(hid: str):
    with _LOCK:
        st = _STATE.get(hid)
    if not st:
        raise HTTPException(404, f"no coverage run for {hid} — POST it first")
    return {"handoff": hid, **st}
