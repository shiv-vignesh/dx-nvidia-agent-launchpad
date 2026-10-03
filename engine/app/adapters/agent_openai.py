"""OpenAIAgent — AgentPort backed by any OpenAI-compatible endpoint (Ollama :11434/v1 now,
our registry router :9000/v1, or vLLM later). Asks the model which on-record meds/vitals the
handoff mentions, and returns a grounded ExtractedHandoff. Pure-stdlib HTTP (no deps)."""
from __future__ import annotations

import json
import re
import urllib.request

from app.domain.models import ExtractedHandoff, ShiftRecord


class OpenAIAgent:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434/v1",
        model: str = "qwen2.5:7b",
        api_key: str = "ollama-local",
        timeout: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def extract(self, handoff_text: str, records: ShiftRecord) -> ExtractedHandoff:
        content = self._call(self._build_prompt(handoff_text, records))
        return self._parse(content)

    # ── grounded prompt: the model may only pick from names already on record ──
    @staticmethod
    def _build_prompt(handoff_text: str, records: ShiftRecord) -> str:
        meds = [m.name for m in records.meds]
        vitals = [v.name for v in records.vitals]
        return (
            "You are a clinical shift-handoff checker. Given the outgoing nurse's handoff note "
            "and this patient's meds/vitals on record, decide which of those are explicitly "
            "mentioned or addressed in the note. Only use names from the lists; never invent.\n"
            f"Meds on record: {meds}\n"
            f"Vitals on record: {vitals}\n"
            f'Handoff note:\n"""\n{handoff_text}\n"""\n'
            'Respond with ONLY JSON: {"mentioned_meds": [...], "mentioned_vitals": [...]}'
        )

    # ── tolerant JSON extraction: grounded = unparseable means "nothing mentioned" ──
    @staticmethod
    def _parse(content: str) -> ExtractedHandoff:
        for match in re.finditer(r"\{.*?\}", content, re.S):
            try:
                obj = json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and ("mentioned_meds" in obj or "mentioned_vitals" in obj):
                return ExtractedHandoff(
                    mentioned_meds=[str(x) for x in obj.get("mentioned_meds", []) or []],
                    mentioned_vitals=[str(x) for x in obj.get("mentioned_vitals", []) or []],
                )
        return ExtractedHandoff()

    def _call(self, prompt: str) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "stream": False,
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.load(r)
        return data["choices"][0]["message"]["content"] or ""
