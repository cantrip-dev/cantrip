"""A tiny client for chat AI models: any OpenAI-compatible API (OpenAI, OpenRouter,
Groq, Together, a local Ollama or LM Studio, and others) or Anthropic's API.

Set it up with environment variables (or the fields in `cantrip ui`):

    CANTRIP_AI_PROVIDER   openai (default: any OpenAI-compatible API) or anthropic
    CANTRIP_AI_KEY        your API key (not needed for a local Ollama)
    CANTRIP_AI_BASE_URL   default https://api.openai.com/v1 (anthropic: https://api.anthropic.com)
                          Ollama: http://localhost:11434/v1   OpenRouter: https://openrouter.ai/api/v1
    CANTRIP_AI_MODEL      default gpt-4o-mini (anthropic: claude-haiku-4-5)

Keys are read from the environment only; Cantrip never writes them to disk.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

PROVIDERS = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "anthropic": ("https://api.anthropic.com", "claude-haiku-4-5"),
}
DEFAULT_BASE_URL, DEFAULT_MODEL = PROVIDERS["openai"]


class AIError(Exception):
    pass


@dataclass
class AI:
    key: str = ""
    provider: str = "openai"
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    calls: int = 0
    tokens: int = 0
    log: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "AI":
        return cls.make(os.environ.get("CANTRIP_AI_PROVIDER", ""), os.environ.get("CANTRIP_AI_KEY", ""),
                        os.environ.get("CANTRIP_AI_BASE_URL", ""), os.environ.get("CANTRIP_AI_MODEL", ""))

    @classmethod
    def make(cls, provider: str = "", key: str = "", base_url: str = "", model: str = "") -> "AI":
        provider = (provider or ("anthropic" if "anthropic" in base_url else "openai")).lower()
        if provider not in PROVIDERS:
            raise AIError(f"Unknown AI provider '{provider}': use openai (any OpenAI-compatible API) or anthropic.")
        default_url, default_model = PROVIDERS[provider]
        return cls(key=key, provider=provider, base_url=base_url or default_url, model=model or default_model)

    @property
    def ready(self) -> bool:
        local = re.match(r"https?://(localhost|127\.0\.0\.1)", self.base_url)
        return bool(self.key or local)

    def chat(self, system: str, user: str, max_tokens: int = 1500) -> str:
        headers = {"Content-Type": "application/json", "User-Agent": "cantrip"}
        if self.provider == "anthropic":
            url = self.base_url.rstrip("/") + "/v1/messages"
            body = {"model": self.model, "max_tokens": max_tokens, "temperature": 0.2, "system": system,
                    "messages": [{"role": "user", "content": user}]}
            headers.update({"x-api-key": self.key, "anthropic-version": "2023-06-01"})
        else:
            url = self.base_url.rstrip("/") + "/chat/completions"
            body = {"model": self.model, "max_tokens": max_tokens, "temperature": 0.2,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            if self.key:
                headers["Authorization"] = f"Bearer {self.key}"
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as err:
            detail = err.read().decode(errors="replace")[:300]
            raise AIError(f"The AI service answered {err.code}: {detail}") from err
        except urllib.error.URLError as err:
            raise AIError(f"Couldn't reach the AI service at {self.base_url}: {err.reason}") from err
        self.calls += 1
        usage = data.get("usage") or {}
        self.tokens += usage.get("total_tokens") or usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        try:
            if self.provider == "anthropic":
                return "".join(part.get("text", "") for part in data["content"] if part.get("type") == "text")
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as err:
            raise AIError(f"Unexpected answer from the AI service: {str(data)[:300]}") from err

    def json(self, system: str, user: str, max_tokens: int = 1500) -> Any:
        """Ask for JSON and parse it, tolerating code fences and stray text around it."""
        text = self.chat(system + "\nAnswer with JSON only, no other text.", user, max_tokens)
        match = re.search(r"(\{.*\}|\[.*\])", text, re.S)
        if not match:
            raise AIError(f"The AI didn't return JSON: {text[:200]}")
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as err:
            raise AIError(f"The AI returned broken JSON: {text[:200]}") from err
