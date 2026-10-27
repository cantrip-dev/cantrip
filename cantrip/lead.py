"""The one record every cantrip passes along: a person who sent a signal."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Lead:
    # Who they are
    name: str = ""
    handle: str = ""  # GitHub login, Luma handle, Discord name...
    email: str = ""
    company: str = ""
    title: str = ""
    location: str = ""
    bio: str = ""
    website: str = ""
    # Where they came from
    source: str = ""  # e.g. "github-stars:cantrip-dev/cantrip", "luma:open-source-ai-day"
    signal: str = ""  # the action itself: "starred", "registered", "attended"
    # What GitHub says about them, when we know their login
    followers: int = 0
    public_repos: int = 0
    top_languages: list[str] = field(default_factory=list)
    # Filled in by the cantrip
    score: int = 0
    tier: str = ""
    reasons: list[str] = field(default_factory=list)
    draft: str = ""

    def to_row(self) -> dict[str, str]:
        row = asdict(self)
        for key in ("top_languages", "reasons"):
            row[key] = "; ".join(row[key])
        return {k: str(v) for k, v in row.items()}

    @property
    def first_name(self) -> str:
        return (self.name or self.handle).split()[0] if (self.name or self.handle) else "there"
