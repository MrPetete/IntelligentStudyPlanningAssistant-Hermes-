"""
TraceLearn — the real "Hermes" transport.

"Hermes" is the project's name for the swappable tool-calling model behind
`llm_client` (see 02_AGENT_BACKEND_CONTEXT.md). This module is the ONE place
that actually talks to the network. `llm_client._real_*` call `complete()`;
nothing else imports this. Keeping the transport isolated means the model /
endpoint is pure config (config.py, from a git-ignored .env) — never code.

The team endpoint is a native Anthropic Messages API (LMU AI):  POST {base}/v1/messages
Auth header:  x-api-key: <key>   +   anthropic-version: 2023-06-01

NOTE — Anthropic has NO "JSON mode" switch (unlike OpenAI). To force JSON-only
output we PREFILL the assistant turn with "{"; the model then continues the
object, and we re-attach the "{" before returning. `llm_client._loads_json_loose`
still strips any stray markdown fences downstream.
"""
from __future__ import annotations

import httpx

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_BASE_URL,
    LLM_TIMEOUT_SECONDS,
    MODEL_NAME,
)


class HermesError(RuntimeError):
    """Transport / HTTP / empty-response failure. Member A's A3 (failure
    handling) catches this to drive bounded retries and safe fallbacks."""


def complete(
    *,
    system: str,
    user: str,
    json_mode: bool = True,
    max_tokens: int = 4096,
    model: str | None = None,
) -> str:
    """One blocking call to the LMU (Anthropic Messages) endpoint.

    Args:
        system: the system prompt (role / rules).
        user: the user prompt (the actual task + material).
        json_mode: if True, prefill "{" to force a JSON object response.
        max_tokens: response cap.
        model: optional per-call model override. Defaults to config.MODEL_NAME.
            This is the seam for future per-task routing (e.g. a cheap model
            for diagnostics, a stronger one for decide_replan) — pass a
            different claude-* id per call without touching this function.

    Returns:
        The raw assistant text (with the prefilled "{" re-attached in json_mode).

    Raises:
        HermesError on missing key, transport/HTTP error, or empty content.
    """
    if not ANTHROPIC_API_KEY:
        raise HermesError(
            "ANTHROPIC_API_KEY is empty — set it in backend/.env "
            "(see .env.example). Never commit the key."
        )

    messages: list[dict[str, str]] = [{"role": "user", "content": user}]
    if json_mode:
        # Prefill forces the model to continue a JSON object from the first "{".
        messages.append({"role": "assistant", "content": "{"})

    payload = {
        "model": model or MODEL_NAME,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    url = ANTHROPIC_BASE_URL.rstrip("/") + "/v1/messages"

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=LLM_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        # Do NOT include headers/payload in the message — avoid leaking the key.
        raise HermesError(f"LLM transport/HTTP error calling {url}: {exc}") from exc

    data = resp.json()
    blocks = data.get("content") or []
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    if not text.strip():
        raise HermesError("LLM returned empty content")

    return _coerce_json_text(text, prefilled=json_mode) if json_mode else text


def _coerce_json_text(text: str, *, prefilled: bool) -> str:
    """Normalize a model response into a parseable JSON string.

    Two endpoint behaviours must both work:
      1. The endpoint HONORS the assistant "{" prefill -> `text` is the
         continuation with no leading brace (e.g. '"ok": true}'). Re-attach "{".
      2. The endpoint IGNORES the prefill (observed on the LMU proxy) -> `text`
         is a fresh, often markdown-fenced, full object
         (e.g. '```json\\n{"ok": true}\\n```'). Strip the fence; do NOT prepend.

    Downstream `_loads_json_loose` is a second safety net, but we hand it clean
    text so a naive '{' + fenced-block corruption can never happen.
    """
    t = text.strip()
    # Strip a leading markdown code fence if the model added one.
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t[:4].lower() == "json":
            t = t[4:].strip()
    # Only re-attach the prefilled brace when the model genuinely continued
    # from it (case 1): i.e. the text isn't already a JSON object.
    if prefilled and not t.startswith("{"):
        t = "{" + t
    return t
