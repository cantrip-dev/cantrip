"""Your profile: what you sell and who you sell it to.

Spells are generic workflows. The profile (cantrip.toml, made by `cantrip init`)
is what makes a run yours: it names your product, describes your ideal
customer (ICP), and signs your drafts. Spells read it and score every lead
against it.
"""

from __future__ import annotations

import copy
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path("cantrip.toml")
SENIORITY_SCALE = {"high": 1.5, "normal": 1.0, "low": 0.5, "ignore": 0.0}
BUYER_POINTS, CHAMPION_POINTS = 25, 15
LIST_FIELDS = ("buyer_roles", "champion_roles", "why_now", "stages", "target_companies", "keywords", "languages",
               "deprioritize", "exclude")


class ProfileMissing(Exception):
    pass


def load(path: str | Path | None = None) -> dict[str, Any]:
    path = Path(path) if path else DEFAULT_PATH
    if not path.exists():
        raise ProfileMissing(
            f"No profile at {path}. Run `cantrip init` to describe what you sell and who you sell to,\n"
            "or pass --profile examples/profiles/devtool-startup.toml to try an example.")
    with path.open("rb") as fh:
        return tomllib.load(fh)


def apply(spell: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """The spell's settings with the profile's product and ICP laid over them."""
    config = copy.deepcopy(spell)
    product = profile.get("product", {})
    for key, target in (("name", "product"), ("pitch", "pitch"), ("ask", "ask"), ("sender", "sender"),
                        ("event", "event_name")):
        if product.get(key):
            config[target] = product[key]

    icp = config.setdefault("icp", {})
    mine = profile.get("icp", {})
    for key in ("why_now", "stages", "target_companies", "keywords", "languages", "deprioritize", "exclude"):
        if key in mine:
            icp[key] = mine[key]
    functions = []
    if mine.get("buyer_roles"):
        functions.append({"points": BUYER_POINTS, "words": mine["buyer_roles"]})
    if mine.get("champion_roles"):
        functions.append({"points": CHAMPION_POINTS, "words": mine["champion_roles"]})
    if functions:
        icp["functions"] = functions
    scale = SENIORITY_SCALE.get(mine.get("seniority", "normal"), 1.0)
    icp["seniority"] = [dict(level, points=round(level["points"] * scale)) for level in icp.get("seniority", [])
                        if scale]

    config["skip_people"] = list(profile.get("skip", {}).get("people", []))
    icp.setdefault("weights", {}).update(profile.get("weights", {}))
    config.setdefault("templates", {}).update(profile.get("templates", {}))
    return config


# --- cantrip init -------------------------------------------------------------

QUESTIONS = [
    ("name", "What are you selling? (product or offer name)", "e.g. Acme Vector DB, or 'sponsorships for our AI meetup'"),
    ("pitch", "Describe it in one line, as you'd say it to a customer", "e.g. a vector database that runs inside Postgres"),
    ("buyer_roles", "Who buys it? Job roles, comma-separated", "e.g. head of engineering, platform, cto"),
    ("champion_roles", "Who uses or champions it? Comma-separated (optional)", "e.g. ml engineer, data scientist"),
    ("seniority", "How much does seniority matter? high / normal / low / ignore", "normal"),
    ("why_now", "What makes now the right time to reach someone? Signals, comma-separated (optional; "
                "`cantrip why-now` suggests some)", "e.g. just raised a seed round, hiring their first salesperson"),
    ("stages", "Company stages you sell to (optional, comma-separated)", "e.g. pre-seed, seed, series a"),
    ("target_companies", "Companies you most want (optional, comma-separated)", ""),
    ("keywords", "Words that signal a good fit in a title, bio or company (comma-separated)", "e.g. rag, llm, search"),
    ("languages", "Programming languages your users write, for GitHub spells (optional)", "e.g. Python, TypeScript"),
    ("deprioritize", "Words that mark a weaker lead (optional)", "e.g. student, intern"),
    ("exclude", "Companies or email domains to skip, like your own and competitors (optional)", ""),
    ("ask", "The one thing your first note asks for", "e.g. a 15-minute call"),
    ("sender", "Your first name, to sign the drafts", ""),
]


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _toml_value(value: Any) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def render(answers: dict[str, Any]) -> str:
    lines = ["# Your Cantrip profile: what you sell and who you sell it to.",
             "# Every spell scores leads against this file. Edit it any time.", "", "[product]"]
    for key in ("name", "pitch", "ask", "sender", "event"):
        if answers.get(key):
            lines.append(f"{key} = {_toml_value(answers[key])}")
    lines += ["", "[icp]"]
    if answers.get("seniority"):
        lines.append(f"seniority = {_toml_value(answers['seniority'])}  # high | normal | low | ignore")
    for key in LIST_FIELDS:
        lines.append(f"{key} = {_toml_value(answers.get(key, []))}")
    return "\n".join(lines) + "\n"


def _table(name: str, values: dict[str, Any]) -> str:
    lines = [f"[{name}]"]
    for key, value in values.items():
        if isinstance(value, str) and "\n" in value:
            lines.append(f'{key} = """\n{value.strip()}\n"""')
        elif isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key} = {value}")
        elif isinstance(value, (str, list)):
            lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines)


def update(answers: dict[str, Any], path: str | Path = DEFAULT_PATH, tables: dict[str, dict] | None = None) -> Path:
    """Rewrite the product and ICP, keeping any [weights], [templates] or [skip] you added by hand.
    `tables` replaces those tables by name."""
    path = Path(path)
    kept = {}
    if path.exists():
        kept = {k: v for k, v in load(path).items() if k not in ("product", "icp") and isinstance(v, dict)}
    kept.update(tables or {})
    written = init(answers, path, interactive=False)
    if kept:
        written.write_text(written.read_text() + "\n" + "\n\n".join(_table(k, v) for k, v in kept.items()) + "\n")
        load(written)
    return written


def init(answers: dict[str, Any], path: str | Path = DEFAULT_PATH, ask=input, interactive: bool | None = None) -> Path:
    """Fill gaps in `answers` by asking (when interactive), then write the profile."""
    if interactive is None:
        interactive = sys.stdin.isatty()
    for key, question, hint in QUESTIONS:
        if answers.get(key) or not interactive:
            continue
        reply = ask(f"{question}\n  ({hint}) > " if hint else f"{question} > ").strip()
        if reply:
            answers[key] = reply
    for key in LIST_FIELDS:
        if isinstance(answers.get(key), str):
            answers[key] = _split(answers[key])
    if answers.get("seniority") and answers["seniority"] not in SENIORITY_SCALE:
        answers["seniority"] = "normal"
    missing = [key for key in ("name", "pitch", "buyer_roles") if not answers.get(key)]
    if missing:
        raise ValueError(f"A profile needs at least: {', '.join(missing)}")
    path = Path(path)
    path.write_text(render(answers))
    load(path)  # make sure it reads back
    return path


def say_no(who: str, path: str | Path = DEFAULT_PATH) -> list[str]:
    """Add a person (GitHub login, email or LinkedIn link) to the profile's [skip] list, so no spell shows them
    again. Raises OSError when the profile can't be written, such as a read-only secret file."""
    mine = load(path)
    people = list(mine.get("skip", {}).get("people", []))
    if who.strip().lower() not in {p.lower() for p in people}:
        people.append(who.strip())
    answers = {**mine.get("product", {}), **mine.get("icp", {})}
    update(answers, path, tables={"skip": {**mine.get("skip", {}), "people": people}})
    return people


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
