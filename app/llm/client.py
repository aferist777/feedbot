"""One provider: OpenRouter. No abstraction over three backends, because there
is only ever one.

Synchronous, and called from worker threads — the event loop must stay free.
"""
import json
import logging
import time
from typing import Any, Optional

import httpx

from app.panel import keys

log = logging.getLogger("feedbot.llm")

URL = "https://openrouter.ai/api/v1/chat/completions"
RETRY_ON = (429, 500, 502, 503, 504)
BACKOFF = [5, 20, 60]


class LLMError(RuntimeError):
    pass


def _inline_refs(schema: Any, defs: Optional[dict] = None) -> Any:
    """Flatten $defs/$ref out of a JSON schema.

    Gemini-family models answer 500 when a schema contains references, and the
    free tier is full of them. Cheaper to expand than to find out at runtime.
    """
    if isinstance(schema, dict):
        defs = defs or schema.get("$defs") or {}
        if "$ref" in schema:
            name = str(schema["$ref"]).rsplit("/", 1)[-1]
            return _inline_refs(defs.get(name, {}), defs)
        return {
            key: _inline_refs(value, defs)
            for key, value in schema.items()
            if key != "$defs"
        }
    if isinstance(schema, list):
        return [_inline_refs(item, defs) for item in schema]
    return schema


def ask(
    model: str,
    messages: list[dict],
    schema: Optional[dict] = None,
    max_tokens: int = 4000,
    temperature: float = 0.3,
) -> Any:
    """Returns parsed JSON when a schema is given, otherwise the raw text."""
    key = keys.value("openrouter")
    if not key:
        raise LLMError("нет ключа OpenRouter — введи его в админке")

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "answer", "strict": True,
                            "schema": _inline_refs(schema)},
        }

    last = ""
    for attempt, pause in enumerate([0, *BACKOFF]):
        if pause:
            time.sleep(pause)
        try:
            response = httpx.post(
                URL,
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                json=body,
                timeout=180,
            )
        except httpx.HTTPError as exc:
            last = f"сеть: {exc}"
            continue
        if response.status_code in RETRY_ON:
            # The free tier throttles by the minute and by the day; the first
            # is worth waiting out, the last attempt tells the difference.
            last = f"HTTP {response.status_code}"
            log.warning("openrouter %s, попытка %s", response.status_code, attempt + 1)
            continue
        if response.status_code != 200:
            # OpenRouter wraps the real reason in {"error": {"message": ...}}
            # and pads it with account ids nobody needs to read.
            try:
                said = ((response.json() or {}).get("error") or {}).get("message")
            except ValueError:
                said = None
            raise LLMError(f"HTTP {response.status_code}: {said or response.text[:200]}")

        data = response.json()
        usage = data.get("usage") or {}
        choice = (data.get("choices") or [{}])[0]
        thought = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
        log.info("%s: %s -> %s токенов (из них %s на рассуждения)", model,
                 usage.get("prompt_tokens"), usage.get("completion_tokens"), thought)
        text = (choice.get("message") or {}).get("content") or ""
        if not text:
            # Two different empties. A free provider sometimes answers 200 with
            # no choices at all — that is worth another try. A reasoning model
            # that spent its whole budget thinking is not: the next attempt
            # would burn it the same way.
            spent_thinking = thought and thought >= max_tokens * 0.9
            last = (
                f"пустой ответ (finish={choice.get('finish_reason')}, "
                f"на рассуждения {thought} из {max_tokens})"
            )
            if spent_thinking:
                raise LLMError(
                    last + " — подними потолок токенов или возьми модель "
                    "без рассуждений"
                )
            log.warning("openrouter вернул пусто, попытка %s", attempt + 1)
            continue
        if schema is None:
            return text
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"ответ не разобрался как JSON: {exc}") from exc

    raise LLMError(f"не достучался до OpenRouter: {last}")
