"""ShiftGuard CLI — run the handoff check on a seed case against local inference.

    python -m app [data/seed/bed4.json]

Inference target via env (defaults to Ollama):
    INFERENCE_BASE_URL (default http://127.0.0.1:11434/v1)   # or the registry router :9000/v1
    INFERENCE_MODEL    (default qwen2.5:7b)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from app.adapters.agent_heuristic import HeuristicAgent
from app.adapters.agent_openai import OpenAIAgent
from app.application.handoff_service import HandoffService
from app.domain.models import ShiftRecord


def main() -> int:
    case_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/seed/bed4.json")
    case = json.loads(case_path.read_text(encoding="utf-8"))
    records = ShiftRecord(**case["records"])
    handoff = case["handoff"]

    mode = os.environ.get("INFERENCE_MODE", "model")
    if mode == "heuristic":
        agent = HeuristicAgent()
        where = "heuristic (no model)"
    else:
        base_url = os.environ.get("INFERENCE_BASE_URL", "http://127.0.0.1:11434/v1")
        model = os.environ.get("INFERENCE_MODEL", "qwen2.5:7b")
        agent = OpenAIAgent(base_url=base_url, model=model)
        where = f"{model} @ {base_url}"

    print(f"=== Handoff for patient {records.patient_id} (extractor: {where}) ===")
    print(handoff, "\n")

    flags = HandoffService(agent=agent).analyze(handoff, records)

    print(f"=== {len(flags)} flag(s) for the incoming nurse to confirm ===")
    for f in flags:
        print(f"  [{f.severity.upper()}] {f.kind}")
        print(f"      {f.message}")
        print(f"      evidence: {f.evidence.ref}  ({f.evidence.detail})")
    if not flags:
        print("  (no omissions detected)")

    # for the demo answer key: did we catch what we expected?
    expected = set(case.get("expected_flags", []))
    got = {f.kind for f in flags}
    if expected:
        print(f"\nanswer key: expected {sorted(expected)} · got {sorted(got)} · "
              f"{'PASS' if expected <= got else 'MISS'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
