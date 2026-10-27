"""The one record every cantrip passes along: a person who sent a signal."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

PERSONAL_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "hotmail.com", "outlook.com", "live.com",
    "icloud.com", "me.com", "aol.com", "proton.me", "protonmail.com", "qq.com", "163.com",
}


@dataclass
class Lead:
    # Who they are
    name: str = ""
    email: str = ""
    company: str = ""
    title: str = ""
    linkedin: str = ""
    github: str = ""
    location: str = ""
    bio: str = ""
    website: str = ""
    # Where they came from
    source: str = ""  # e.g. "github-search:language:python", "csv:open-source-ai-day"
    signal: str = ""  # the action itself: "registered", "attended", "contributed", "starred", "found", "mentioned"
    source_url: str = ""  # the page a web lead was found on
    evidence: str = ""  # what that page says about them, in its own words
    research: str = ""  # notes from research mode
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
        who = self.name or self.github
        return who.split()[0] if who else "there"

    @property
    def email_domain(self) -> str:
        return self.email.rsplit("@", 1)[-1].lower() if "@" in self.email else ""

    @property
    def has_work_email(self) -> bool:
        return bool(self.email_domain) and self.email_domain not in PERSONAL_EMAIL_DOMAINS

    @property
    def key(self) -> str:
        """What makes two rows the same person, for de-duplication."""
        return (self.email or self.linkedin.rstrip("/") or self.github or self.name
                or f"company:{self.company}").lower()
