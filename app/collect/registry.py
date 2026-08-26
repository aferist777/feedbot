"""Which kinds of source exist, and what each one calls a name.

One entry per adapter, so the panel can draw the "add a source" form without
knowing anything about Reddit in particular — and so adding a second adapter
later is a row here plus a module, not a rewrite of the panel.
"""
from dataclasses import dataclass
from typing import Callable, Optional

from app.collect import reddit


@dataclass
class Adapter:
    id: str
    label: str
    name_label: str      # what the "name" field means for this adapter
    name_hint: str
    look_up: Optional[Callable[[str], Optional[dict]]]


ADAPTERS: list[Adapter] = [
    Adapter(
        id="reddit",
        label="Reddit",
        name_label="сабреддит",
        name_hint="без r/ — например SaaS",
        look_up=reddit.look_up,
    ),
]

BY_ID = {adapter.id: adapter for adapter in ADAPTERS}


def payload() -> list[dict]:
    return [
        {
            "id": a.id,
            "label": a.label,
            "name_label": a.name_label,
            "name_hint": a.name_hint,
        }
        for a in ADAPTERS
    ]
