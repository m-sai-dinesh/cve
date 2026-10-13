"""Gemini client with Annex-22 provenance (PRD §15).

Every call records: model id, prompt template version, SHA-256 of the rendered
prompt, SHA-256 of the input payload, and the temperature. Structured calls use
Gemini's ``response_schema`` so the API returns conforming JSON (PRD §12.3).

If no API key is configured the client reports ``available == False`` and callers
fall back to their deterministic reasoner. That is a documented operating mode,
not a silent degradation: the generator is recorded on every stored decision.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..config import settings
from .logging import get_logger

log = get_logger("llm")

PROMPT_VERSION = "1.0.0"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_payload(payload: Any) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))


@dataclass
class LLMResult:
    text: str
    data: Any | None = None
    model_id: str = ""
    prompt_hash: str = ""
    input_hash: str = ""
    temperature: float = 0.0
    prompt_version: str = PROMPT_VERSION
    generator: str = "gemini"          # "gemini" | "deterministic"
    usage: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def provenance(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id, "prompt_hash": self.prompt_hash,
            "input_hash": self.input_hash, "temperature": self.temperature,
            "prompt_version": self.prompt_version, "generator": self.generator,
        }


class LLMClient:
    """Thin wrapper over google-genai; safe to construct even with no key."""

    def __init__(self) -> None:
        self._client = None
        self._init_error = ""
        if settings.llm_enabled:
            try:
                from google import genai  # lazy: keeps import cost off the hot path

                self._client = genai.Client(api_key=settings.gemini_api_key)
            except Exception as exc:
                self._init_error = f"{type(exc).__name__}: {exc}"
                log.warning("gemini_init_failed", error=self._init_error)

    @property
    def available(self) -> bool:
        return self._client is not None

    @property
    def model_id(self) -> str:
        return settings.llm_model

    def status(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "model_id": self.model_id,
            "temperature": settings.llm_temperature,
            "prompt_version": PROMPT_VERSION,
            "send_raw_code": settings.llm_send_raw_code,
            "mode": "gemini" if self.available else "deterministic-fallback",
            "error": self._init_error,
        }

    # ---------------------------------------------------------------- calling
    def generate(
        self,
        prompt: str,
        *,
        input_payload: Any = None,
        system: str = "",
        schema: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> LLMResult:
        temp = settings.llm_temperature if temperature is None else temperature
        res = LLMResult(
            text="",
            model_id=self.model_id,
            prompt_hash=sha256((system or "") + "\n" + prompt),
            input_hash=hash_payload(input_payload if input_payload is not None else prompt),
            temperature=temp,
        )
        if not self.available:
            res.generator = "deterministic"
            res.error = self._init_error or "no GEMINI_API_KEY configured"
            return res

        from google.genai import types as gt

        cfg: dict[str, Any] = {
            "temperature": temp,
            "max_output_tokens": max_output_tokens or settings.llm_max_output_tokens,
        }
        if system:
            cfg["system_instruction"] = system
        if schema is not None:
            cfg["response_mime_type"] = "application/json"
            cfg["response_schema"] = schema
        models_to_try = [self.model_id]
        for fm in ("gemini-3.1-flash-lite", "gemini-3.5-flash-lite"):
            if fm not in models_to_try:
                models_to_try.append(fm)

        last_error = ""
        for mid in models_to_try:
            try:
                resp = self._client.models.generate_content(
                    model=mid, contents=prompt, config=gt.GenerateContentConfig(**cfg)
                )
                res.model_id = mid
                res.text = (resp.text or "").strip()
                meta = getattr(resp, "usage_metadata", None)
                if meta is not None:
                    res.usage = {
                        "prompt_tokens": getattr(meta, "prompt_token_count", None),
                        "output_tokens": getattr(meta, "candidates_token_count", None),
                        "total_tokens": getattr(meta, "total_token_count", None),
                    }
                if schema is not None:
                    res.data = _loose_json(res.text)
                    if res.data is None:
                        res.error = "model returned text that is not valid JSON"
                res.error = ""
                break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                log.warning("gemini_call_failed", model=mid, error=last_error)
                continue
        else:
            res.error = last_error
            res.generator = "deterministic"
        return res

    def count_tokens(self, text: str) -> int | None:
        """Token budgeting via the SDK (PRD §6.2) with a ~4-chars/token fallback."""
        if not self.available:
            return max(1, len(text) // 4)
        for mid in [self.model_id, "gemini-3.1-flash-lite"]:
            try:
                r = self._client.models.count_tokens(model=mid, contents=text)
                return getattr(r, "total_tokens", None)
            except Exception:
                continue
        return max(1, len(text) // 4)


def _loose_json(text: str) -> Any | None:
    """Parse JSON, tolerating ```json fences or surrounding prose."""
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except Exception:
            pass
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = text.find(opener), text.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(text[i : j + 1])
            except Exception:
                continue
    return None


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


# --------------------------------------------------------------------- safety
SECRET_PATTERNS = [
    re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[-_]?key|private[-_]?key|credential)\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{12,}"),
    re.compile(r"(?i)\b(aws_)?(secret_)?access_key(_id)?\b"),
]


def mask_secret(value: str) -> str:
    """Mask a secret before it is stored or sent anywhere (PRD §15 data minimisation)."""
    if value is None:
        return ""
    v = str(value)
    if len(v) <= 4:
        return "****"
    return v[:2] + "*" * min(10, max(4, len(v) - 4)) + v[-2:]


def looks_secret(key: str, value: str = "") -> bool:
    blob = f"{key} {value}"
    return any(p.search(blob) for p in SECRET_PATTERNS)
