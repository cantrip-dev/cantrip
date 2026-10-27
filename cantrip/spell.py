"""A spell is a folder in spellbook/ with a spell.toml (rules) and a SPELL.md
(instructions an agent can follow). This module loads the TOML half."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

# In a clone of the repo the spellbook sits next to the package; in an installed
# copy it ships inside it.
_HERE = Path(__file__).resolve().parent
SPELLBOOK = next((p for p in (_HERE.parent / "spellbook", _HERE / "spellbook") if p.is_dir()), _HERE / "spellbook")


def load(name_or_path: str) -> dict[str, Any]:
    path = Path(name_or_path)
    if path.is_dir():
        path = path / "spell.toml"
    elif not path.exists():
        path = SPELLBOOK / name_or_path / "spell.toml"
    with path.open("rb") as fh:
        return tomllib.load(fh)
