"""The visual packs, and which posts each is meant for.

The panel draws the picker from this list, so a pack that is not written yet is
visible but cannot be chosen — the plan is part of the interface rather than a
note somewhere else.
"""
from dataclasses import dataclass


@dataclass
class Pack:
    id: str
    label: str
    about: str
    ready: bool


PACKS: list[Pack] = [
    Pack("talk", "Разговорный",
         "слова всплывают в такт речи — под истории, байки и споры", True),
    Pack("tech", "Технический",
         "мокапы интерфейсов, терминал, логи — под софт и настройку", True),
    Pack("numbers", "Цифры",
         "счётчики и графики — когда в посте рост, суммы и сравнения", True),
    Pack("toon", "Мультяшный",
         "рисованные иконки и подчёркивания — под лёгкое и бытовое", True),
    Pack("cinema", "Кинематографичный",
         "вспышки, тряска, монтажный ритм — под драму и провалы", True),
]

BY_ID = {pack.id: pack for pack in PACKS}


def payload() -> list[dict]:
    return [{"id": p.id, "label": p.label, "about": p.about, "ready": p.ready}
            for p in PACKS]
