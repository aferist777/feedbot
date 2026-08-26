"""Which model does what, and how hard it tries.

Read fresh from the settings table on every call rather than at import: picking
a better model is the main lever on quality, and it should not need a restart
to try one.
"""
import logging
from typing import Optional

from app import config
from app.db.repo import sget

log = logging.getLogger("feedbot.llm.models")

# What each knob is for, and what it costs to get wrong — the panel shows these.
FIELDS = [
    {
        "key": "model.write",
        "label": "Модель для текста",
        "kind": "line",
        "default": config.MODEL_WRITE,
        "hint": "пересказ и сценарий. Бесплатные модели изредка выдумывают слова",
    },
    {
        "key": "model.write_fallback",
        "label": "Запасная модель для текста",
        "kind": "line",
        "default": "nvidia/nemotron-3-super-120b-a12b:free",
        "hint": "берётся, если основная не ответила — бесплатные провайдеры "
                "периодически отдают пустоту на несколько минут",
    },
    {
        "key": "model.rate",
        "label": "Модель для оценки постов",
        "kind": "line",
        "default": config.MODEL_RATE,
        "hint": "нужна поддержка строгого JSON — не у всех бесплатных она есть",
    },
    {
        "key": "model.temperature",
        "label": "Температура текста",
        "kind": "float",
        "default": 0.7,
        "hint": "ниже — суше и предсказуемее, выше — живее и рискованнее",
    },
    {
        "key": "model.max_tokens",
        "label": "Потолок токенов на ответ",
        "kind": "int",
        "default": 16000,
        "hint": "модели с рассуждениями тратят 1200-2000 ещё до первого слова",
    },
    {
        "key": "rate.top",
        "label": "Сколько постов отдавать на оценку",
        "kind": "int",
        "default": config.RATE_TOP,
        "hint": "остальные останутся с местом по счётчикам",
    },
    {
        "key": "rate.batch",
        "label": "Постов в одном запросе",
        "kind": "int",
        "default": config.RATE_BATCH,
        "hint": "больше — дешевле, но выше шанс, что ответ не влезет",
    },
]

BY_KEY = {field["key"]: field for field in FIELDS}


def _get(key: str):
    field = BY_KEY[key]
    raw = sget(key)
    if raw is None or raw == "":
        return field["default"]
    try:
        if field["kind"] == "int":
            return int(raw)
        if field["kind"] == "float":
            return float(raw)
    except ValueError:
        return field["default"]
    return raw


def write_model() -> str:
    return str(_get("model.write"))


def write_chain() -> list[str]:
    """The write model, then whatever should be tried when it is silent."""
    chain = [write_model()]
    spare = str(_get("model.write_fallback")).strip()
    if spare and spare != chain[0]:
        chain.append(spare)
    return chain


def rate_model() -> str:
    return str(_get("model.rate"))


def temperature() -> float:
    return float(_get("model.temperature"))


def max_tokens() -> int:
    return int(_get("model.max_tokens"))


def rate_top() -> int:
    return int(_get("rate.top"))


def rate_batch() -> int:
    return int(_get("rate.batch"))


def payload() -> list[dict]:
    return [{**field, "value": _get(field["key"])} for field in FIELDS]


def cast(key: str, raw) -> Optional[object]:
    field = BY_KEY.get(key)
    if field is None:
        return None
    if field["kind"] == "int":
        return int(raw)
    if field["kind"] == "float":
        return float(raw)
    return str(raw).strip()


def try_models(chain: list, call) -> tuple:
    """Walk the chain until one model answers. Returns (answer, model used).

    A free provider that goes quiet takes minutes to come back, and a run
    should not die waiting for it — but a model that answered badly is not
    retried elsewhere, only silence is.
    """
    from app.llm.client import LLMError

    last: Exception = LLMError("нет ни одной модели")
    for name in chain:
        try:
            return call(name), name
        except LLMError as exc:
            last = exc
            log.warning("модель %s не ответила: %s", name, exc)
    raise last
