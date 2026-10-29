"""Thin client for Nebius Token Factory (OpenAI-compatible) running NVIDIA Nemotron.

If NEBIUS_API_KEY is not set (or DAWA_OFFLINE=1) the app runs in *offline mode*:
deterministic rule-based fallbacks are used instead of the model. Offline mode
is also the baseline the evals compare the model against.
"""
from __future__ import annotations
import json, os, re, threading
from typing import Any, Optional

BASE_URL = os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
# Model IDs are configurable; verify exact IDs in the Token Factory playground.
# IDs as listed on Nebius Token Factory (checked 27 Oct 2026). Lightning = cheap and fast; Super VL = reads images.
TEXT_MODEL = os.environ.get("DAWA_TEXT_MODEL", "nvidia/Nemotron-3_5-Lightning")
FAST_MODEL = os.environ.get("DAWA_FAST_MODEL", TEXT_MODEL)
NEBIUS_VISION_DEFAULT = "nvidia/Nemotron-3.5-Super-VL"
VISION_MODEL = os.environ.get("DAWA_VISION_MODEL", "")   # Ollama needs this set; Nebius falls back to Super VL


OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "nemotron-3-nano:4b")


_session = threading.local()      # Streamlit runs each visitor's script in its own thread, so this is per visitor


def restrict(on: bool) -> None:
    """Switch every model and web call off for the current visitor (the app does this until the access code is entered), so a leaked link cannot spend credits."""
    _session.on = bool(on)


def restricted() -> bool:
    return bool(getattr(_session, "on", False))


def provider() -> str:
    """'ollama' (local), 'nebius' (Token Factory) or 'offline' (rules only).
    DAWA_PROVIDER wins; otherwise Nebius if a key is set; otherwise offline. A restricted visitor is always offline."""
    if restricted() or os.environ.get("DAWA_OFFLINE") == "1":
        return "offline"
    p = os.environ.get("DAWA_PROVIDER", "").lower()
    if p in ("ollama", "nebius", "offline"):
        return p
    return "nebius" if os.environ.get("NEBIUS_API_KEY") else "offline"


def is_offline() -> bool:
    return provider() == "offline"


def model_name() -> str:
    return OLLAMA_MODEL if provider() == "ollama" else TEXT_MODEL


def _ollama_chat(messages: list, model: str) -> str:
    """Native Ollama API: JSON-constrained output, reasoning switched off so tokens are not spent thinking."""
    import httpx
    body = {"model": model, "messages": messages, "stream": False, "format": "json", "think": False,
            "options": {"temperature": 0.1, "num_ctx": 8192}}
    url = OLLAMA_HOST.rstrip("/") + "/api/chat"
    r = httpx.post(url, json=body, timeout=300)
    if r.status_code == 400 and "think" in r.text.lower():   # model without a thinking mode
        body.pop("think"); r = httpx.post(url, json=body, timeout=300)
    r.raise_for_status()
    return r.json()["message"]["content"]


def _client():
    from openai import OpenAI
    return OpenAI(base_url=BASE_URL, api_key=os.environ["NEBIUS_API_KEY"], timeout=60)


def _extract_json(text: str) -> Any:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fence:
        text = fence.group(1).strip()
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start > 0:
        text = text[start:]
    try:
        return json.loads(text)
    except ValueError:
        # a "cells" list may hold a batch code or a date unquoted (K2100680, MAR-23): quote what is not a number, then try again
        def quote(m):
            items = [t.strip() for t in m.group(1).split(",") if t.strip()]
            return '"cells":[' + ",".join(t if re.fullmatch(r"-?\d+(?:\.\d+)?", t) or t.startswith('"') else json.dumps(t) for t in items) + "]"
        return json.loads(re.sub(r'"cells"\s*:\s*\[([^\]]*)\]', quote, text))


def chat_json(system: str, user: str, model: Optional[str] = None, retries: int = 2) -> Any:
    """Call the model and parse a JSON answer, retrying with a repair hint."""
    local = provider() == "ollama"
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last_err: Exception | None = None
    for _ in range(retries + 1):
        if local:
            content = _ollama_chat(messages, OLLAMA_MODEL)
        else:
            resp = _nebius_create(
                model=model or TEXT_MODEL, messages=messages, temperature=0.1, max_tokens=2500)
            content = resp.choices[0].message.content or ""
        try:
            return _extract_json(content)
        except Exception as e:  # malformed JSON -> ask the model to repair
            last_err = e
            messages += [{"role": "assistant", "content": content},
                         {"role": "user", "content": "That was not valid JSON. Reply with ONLY the JSON."}]
    raise ValueError(f"Model did not return valid JSON: {last_err}")


def vision_model() -> str:
    return VISION_MODEL or (NEBIUS_VISION_DEFAULT if provider() == "nebius" else "")


def vision_available() -> bool:
    return bool(vision_model()) and not is_offline()


def _nebius_create(**kw):
    """JSON tasks do not need reasoning tokens. Ask for none; if the model rejects the field, retry without it."""
    c = _client()
    try:
        return c.chat.completions.create(extra_body={"reasoning_effort": "none"}, **kw)
    except Exception as e:
        if "reasoning" not in str(e).lower():
            raise
        return c.chat.completions.create(**kw)


def chat_vision_json(image_b64: str, mime: str, instruction: str) -> Any:
    """Send one image plus an instruction; parse a JSON answer. Works with Ollama vision models and Nebius."""
    vm = vision_model()
    if not vm:
        raise RuntimeError("Set DAWA_VISION_MODEL to a vision-capable model id to read photos.")
    if provider() == "ollama":
        content = _ollama_chat([{"role": "user", "content": instruction, "images": [image_b64]}], vm)
    else:
        resp = _nebius_create(
            model=vm, temperature=0, max_tokens=3000,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": instruction},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}}]}])
        content = resp.choices[0].message.content or ""
    try:
        return _extract_json(content)
    except ValueError:                       # json.JSONDecodeError: one automatic retry with the problem named, before the user ever sees an error
        if provider() == "ollama":
            raise
        resp = _nebius_create(
            model=vm, temperature=0, max_tokens=3000,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": instruction + "\nYour last answer was not valid JSON. Reply with ONLY valid JSON: every number a plain number (write 12 for 'GST 12 %'), every text in quotes."},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}}]}])
        return _extract_json(resp.choices[0].message.content or "")


def chat_vision_text(image_b64: str, mime: str, instruction: str) -> str:
    """Kept for the prescription screen: returns the raw text answer."""
    if not VISION_MODEL:
        raise RuntimeError("Set DAWA_VISION_MODEL to a multimodal model id to read images.")
    resp = _client().chat.completions.create(
        model=VISION_MODEL, temperature=0,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": instruction},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}}]}])
    return resp.choices[0].message.content or ""
