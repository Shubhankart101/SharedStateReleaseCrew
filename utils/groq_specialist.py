from __future__ import annotations

import json
import os

from utils.models import SpecialistFinding

try:
    from groq import Groq
except ImportError:
    Groq = None  # type: ignore[assignment]


class GroqSpecialist:
    """Real specialist callable, replaced by deterministic functions in pytest."""

    def __init__(self, role: str, api_key: str | None = None) -> None:
        key = api_key or os.getenv("GROQ_API_KEY")
        if not key:
            raise ValueError("GROQ_API_KEY is required to call Groq.")
        if Groq is None:
            raise ImportError("Install groq before running the application.")
        self.role = role
        self.client = Groq(api_key=key)

    def __call__(self, role_input: dict) -> SpecialistFinding:
        response = self.client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
            messages=[{"role": "user", "content": json.dumps(role_input, default=str)}],
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        return SpecialistFinding(**data)
