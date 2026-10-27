"""A small JSON-over-HTTP helper shared by the CRM connectors."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any


class CRMError(Exception):
    pass


def call(method: str, url: str, headers: dict[str, str], body: Any = None, retries: int = 3) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "cantrip", **headers})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as err:
            if err.code == 429 and attempt < retries:  # rate limited: wait and try again
                time.sleep(float(err.headers.get("Retry-After") or 2 ** attempt))
                continue
            detail = err.read().decode(errors="replace")[:400]
            raise CRMError(f"{method} {url.split('?')[0]} answered {err.code}: {detail}") from err
        except urllib.error.URLError as err:
            raise CRMError(f"Couldn't reach {url.split('/')[2]}: {err.reason}") from err
    raise CRMError("Too many retries")


def split_name(name: str) -> tuple[str, str]:
    parts = name.strip().split()
    if not parts:
        return "", ""
    return parts[0], " ".join(parts[1:])


def note_text(lead) -> str:
    """Score, reasons, source and draft, as plain text for a CRM note."""
    lines = [f"Cantrip score: {lead.score} ({lead.tier})"]
    if lead.reasons:
        lines.append("Why: " + "; ".join(lead.reasons))
    if lead.source_url or lead.source:
        lines.append(f"Found via: {lead.source_url or lead.source}")
    if lead.evidence:
        lines.append(f'Evidence: "{lead.evidence}"')
    if lead.research:
        lines.append("Research:\n" + lead.research)
    if lead.draft:
        lines.append("Draft first note (not sent):\n" + lead.draft)
    return "\n".join(lines)
