"""FastAPI adapter — HTTP + Swagger UI over the handoff check.

A stack-facing adapter in the hexagonal sense: it composes an AgentPort impl with
HandoffService and exposes it over HTTP. The domain stays untouched — this layer only
translates JSON <-> domain models, so the Swagger schema is generated straight from
ShiftRecord / Flag.

Run (binds 0.0.0.0 so teammates on the LAN can reach it; picks a free port):
    python -m app.web.server
    SHIFTGUARD_PORT=8900 python -m app.web.server     # ask for a specific port

Swagger UI:  http://<host>:<port>/docs
Extractor picked by the same env vars the CLI uses:
    INFERENCE_MODE=heuristic   -> no model, instant/offline (demo-safe default here)
    INFERENCE_BASE_URL / INFERENCE_MODEL  -> any OpenAI-compatible endpoint
"""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.adapters.agent_heuristic import HeuristicAgent
from app.adapters.agent_openai import OpenAIAgent
from app.application.handoff_service import HandoffService
from app.domain.models import Flag, ShiftRecord

# app/web/server.py -> parents[2] == backend/
SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seed"


def build_agent():
    """Same selection rule as the CLI, so HTTP and `python -m app` agree."""
    if os.environ.get("INFERENCE_MODE", "heuristic") == "heuristic":
        return HeuristicAgent(), "heuristic (no model)"
    base_url = os.environ.get("INFERENCE_BASE_URL", "http://127.0.0.1:11434/v1")
    model = os.environ.get("INFERENCE_MODEL", "qwen2.5:7b")
    return OpenAIAgent(base_url=base_url, model=model), f"{model} @ {base_url}"


class AnalyzeRequest(BaseModel):
    """An outgoing nurse's narrative plus that patient's meds/vitals on record."""

    handoff: str = Field(
        ...,
        description="Free-text handoff note from the outgoing nurse.",
        examples=["Patient in bed 4 stable overnight. Gave heparin around 2000. Vitals look fine."],
    )
    records: ShiftRecord


app = FastAPI(
    title="ShiftGuard",
    version="0.1.0",
    description=(
        "On-device shift-handoff checker. Extracts which on-record meds and vitals the "
        "outgoing nurse's narrative actually mentions, then runs deterministic rules to flag "
        "what was omitted. Every flag cites a concrete record.\n\n"
        "Start with **GET /cases**, then **POST /analyze/case/{case_id}** for a one-click demo."
    ),
)


@app.get("/health", summary="Liveness + which extractor is wired in", tags=["meta"])
def health() -> dict[str, str]:
    _, where = build_agent()
    return {"status": "ok", "extractor": where, "seed_dir": str(SEED_DIR)}


@app.get("/cases", summary="List the bundled seed cases", tags=["demo"])
def cases() -> list[str]:
    if not SEED_DIR.is_dir():
        return []
    return sorted(p.stem for p in SEED_DIR.glob("*.json"))


@app.post(
    "/analyze",
    response_model=list[Flag],
    summary="Analyze a handoff you supply",
    tags=["analyze"],
)
def analyze(req: AnalyzeRequest) -> list[Flag]:
    agent, _ = build_agent()
    return HandoffService(agent=agent).analyze(req.handoff, req.records)


@app.post(
    "/analyze/case/{case_id}",
    response_model=list[Flag],
    summary="Analyze a bundled seed case (no body to type)",
    tags=["demo"],
)
def analyze_case(case_id: str) -> list[Flag]:
    path = SEED_DIR / f"{case_id}.json"
    # keep the path inside SEED_DIR: case_id arrives from the URL
    if path.parent != SEED_DIR or not path.is_file():
        raise HTTPException(status_code=404, detail=f"no seed case {case_id!r}; see GET /cases")
    case = json.loads(path.read_text(encoding="utf-8"))
    agent, _ = build_agent()
    return HandoffService(agent=agent).analyze(case["handoff"], ShiftRecord(**case["records"]))


def pick_port(preferred: int, host: str, tries: int = 25) -> int:
    """First free port at or above `preferred` — vLLM (:8000), the registry router (:9000)
    and Ollama (:11434) may already hold theirs, and we don't want to fight them."""
    for port in range(preferred, preferred + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((host, port))
            except OSError:
                continue
            return port
    raise SystemExit(f"no free port in {preferred}..{preferred + tries - 1}")


def lan_ip() -> str:
    """Best-effort LAN address to hand to teammates (no packets actually sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def main() -> None:
    import uvicorn

    host = os.environ.get("SHIFTGUARD_HOST", "0.0.0.0")
    port = pick_port(int(os.environ.get("SHIFTGUARD_PORT", "8800")), host)
    _, where = build_agent()
    print(f"ShiftGuard API · extractor: {where}")
    print(f"  Swagger UI : http://127.0.0.1:{port}/docs")
    print(f"  On the LAN : http://{lan_ip()}:{port}/docs")
    print(f"  bound to {host}:{port}\n")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
