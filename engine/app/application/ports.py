"""Ports — the interfaces the application core depends on. Adapters (stack-facing) implement them.
Keeps domain/application free of OpenClaw/OpenShell/vLLM/Ollama specifics."""
from __future__ import annotations

from typing import Protocol

from app.domain.models import ExtractedHandoff, ShiftRecord


class AgentPort(Protocol):
    """Extracts structured claims from a free-text handoff (the model's job).
    Implemented by: a direct OpenAI-compatible client (Ollama/registry) now,
    an OpenClaw-driven adapter later — same interface either way."""

    def extract(self, handoff_text: str, records: ShiftRecord) -> ExtractedHandoff: ...
