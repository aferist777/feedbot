"""What the bot can make out of a post.

One entry per treatment. A second kind of write-up — a breakdown, a script, a
argument-for-and-against — is a row here plus a prompt file, and the panel picks
it up without being touched.
"""
from dataclasses import dataclass, field
from pathlib import Path

PROMPTS = Path(__file__).parent / "prompts"

# The shape every treatment answers in. Kept common on purpose: a title, an
# opening line and a body cover a retelling, a breakdown and a script alike.
SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "hook": {"type": "string"},
        "text": {"type": "string"},
    },
    "required": ["title", "hook", "text"],
    "additionalProperties": False,
}


@dataclass
class Mode:
    id: str
    label: str
    about: str
    prompt: str                       # file name under prompts/
    chars: int = 1300                 # target length of `text`
    vars: dict = field(default_factory=dict)

    def system(self, niche: str) -> str:
        raw = (PROMPTS / self.prompt).read_text(encoding="utf-8")
        # Russian narration runs at roughly fifteen characters a second, which
        # is where the seconds figure in the prompt comes from.
        return raw.format(
            niche=niche or "не задана",
            chars=self.chars,
            seconds=round(self.chars / 15),
            **self.vars,
        )


MODES: list[Mode] = [
    Mode(
        id="retell",
        label="Пересказ",
        about="художественный пересказ поста живым голосом",
        prompt="retell.md",
        chars=1300,
    ),
]

BY_ID = {mode.id: mode for mode in MODES}


def payload() -> list[dict]:
    return [{"id": m.id, "label": m.label, "about": m.about, "chars": m.chars}
            for m in MODES]
