"""A spell is a folder in spellbook/ with a spell.toml (rules) and a SPELL.md
(instructions an agent can follow). This module loads the TOML half."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

SPELLBOOK = Path(__file__).resolve().parent.parent / "spellbook"


def load(name_or_path: str) -> dict[str, Any]:
    path = Path(name_or_path)
    if path.is_dir():
        path = path / "spell.toml"
    elif not path.exists():
        path = SPELLBOOK / name_or_path / "spell.toml"
    with path.open("rb") as fh:
        return tomllib.load(fh)
