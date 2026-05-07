"""
Lightweight LLM client for the workflow.

Supports free / low-cost options as requested:
- Ollama (local Llama): free, no API key. Run `ollama run llama3.2` (or similar) first.
- Deep Seek: set DEEPSEEK_API_KEY for api.deepseek.com (low-cost, often free-tier offers).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Literal, Optional

import httpx

# Backend selection: "ollama" (Llama via Ollama) or "deepseek"
LLM_BACKEND = os.environ.get("LLM_BACKEND", "ollama").lower()
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")


def get_llm_backend() -> Literal["ollama", "deepseek"]:
    if LLM_BACKEND in ("ollama", "deepseek"):
        return LLM_BACKEND  # type: ignore
    return "ollama"


def _messages_to_ollama_prompt(messages: List[Dict[str, str]]) -> str:
    """Convert OpenAI-style messages to a single prompt for Ollama."""
    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            parts.append(f"System: {content}")
        elif role == "user":
            parts.append(f"User: {content}")
        elif role == "assistant":
            parts.append(f"Assistant: {content}")
    if parts:
        parts.append("Assistant:")
    return "\n\n".join(parts)


async def chat_ollama(
    messages: List[Dict[str, str]],
    *,
    model: str = OLLAMA_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    timeout: float = 120.0,
) -> str:
    """Call Ollama /api/chat (Llama or other local model)."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            f"{base_url.rstrip('/')}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
        )
        r.raise_for_status()
        data = r.json()
    return (data.get("message") or {}).get("content", "").strip()


async def chat_deepseek(
    messages: List[Dict[str, str]],
    *,
    model: str = DEEPSEEK_MODEL,
    base_url: str = DEEPSEEK_BASE_URL,
    api_key: Optional[str] = None,
    timeout: float = 120.0,
) -> str:
    """Call Deep Seek API (OpenAI-compatible). Requires DEEPSEEK_API_KEY."""
    key = api_key or DEEPSEEK_API_KEY
    if not key:
        raise ValueError(
            "DEEPSEEK_API_KEY is not set. Set it in the environment or pass api_key=..."
        )
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            f"{base_url.rstrip('/')}/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "stream": False},
        )
        r.raise_for_status()
        data = r.json()
    choice = (data.get("choices") or [None])[0]
    if not choice:
        return ""
    return (choice.get("message") or {}).get("content", "").strip()


async def chat(
    messages: List[Dict[str, str]],
    *,
    backend: Optional[Literal["ollama", "deepseek"]] = None,
    **kwargs: Any,
) -> str:
    """
    Single entry point for the lightweight LLM.
    Uses LLM_BACKEND env (default ollama). Pass backend= to override.
    """
    backend = backend or get_llm_backend()
    if backend == "ollama":
        return await chat_ollama(messages, **kwargs)
    if backend == "deepseek":
        return await chat_deepseek(messages, **kwargs)
    raise ValueError(f"Unknown backend: {backend}")


async def complete(prompt: str, **kwargs: Any) -> str:
    """Convenience: single user prompt."""
    return await chat([{"role": "user", "content": prompt}], **kwargs)
