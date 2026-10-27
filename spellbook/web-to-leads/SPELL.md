# Spell: web to leads

**Signal in:** the open web. An AI model reads your profile (and an optional brief), plans searches, reads the pages they return, and lists the people and companies those pages actually name.
**Out:** one row per lead with a fit score, the reasons, **the page it was found on and a quote from it**, and a draft written around that quote. Nothing is sent.

## What it needs

An AI model and a search service. Each user brings their own; keys are read from environment variables (or typed into `cantrip ui` for one run) and never written to disk.

| Setting | What to put |
| --- | --- |
| `CANTRIP_AI_PROVIDER` | `openai` (default: OpenAI or any OpenAI-compatible API) or `anthropic` |
| `CANTRIP_AI_KEY` | your key. Not needed for a local Ollama |
| `CANTRIP_AI_BASE_URL` | optional: `https://openrouter.ai/api/v1`, `http://localhost:11434/v1` (Ollama)… |
| `CANTRIP_AI_MODEL` | optional: defaults to `gpt-4o-mini` or `claude-haiku-4-5` |
| `CANTRIP_SEARCH` | `tavily` (default), `brave`, `serpapi` or `searxng` |
| `CANTRIP_SEARCH_KEY` | the search service's key |
| `CANTRIP_SEARCH_URL` | your SearXNG address (free and self-hosted, no key) |

A run of 8 searches reads about 24 pages and makes about 40 AI calls with drafts (roughly 80-100k tokens): from a few cents to around ten cents with a small model. `--dry-run` shows the planned searches and the estimate without running them.

## Before the first run: the profile

Every run scores against the person's profile, `cantrip.toml`. If there isn't one, interview them first, in one short message:

1. What are you selling, and how would you describe it to a customer in one line?
2. Who buys it, and who uses or champions it? (job roles)
3. Any companies you most want, and anyone to skip (your own company, competitors)?
4. What should a first note ask for, and how do you sign your name?

Then save their answers with `cantrip init --name ... --pitch ... --buyer-roles ... --champion-roles ... --target-companies ... --exclude ... --ask ... --sender ...`. Never guess what they sell.

## Run it

```bash
cantrip cast web-to-leads --web --out leads.csv                                   # searches planned from the profile alone
cantrip cast web-to-leads --web "DevRel leads at AI infrastructure startups" --queries 10 --out leads.csv
cantrip cast web-to-leads --web "..." --dry-run                                   # see the searches and the cost first
cantrip cast web-to-leads --web "..." --research --top 10                         # also research the 10 best before drafting
```

Research mode works on any spell: `cantrip cast attendees-to-leads --csv guests.csv --research --ai-drafts` looks up the best attendees on the web and writes their drafts around what it found.

## How it keeps leads real

- The model may only list people and companies **named on the page**. Cantrip checks: a person whose name isn't on the page is dropped, as is a title, company or LinkedIn link the page doesn't contain.
- The quote shown as evidence must really be on the page, or it's removed so no draft is built on it.
- A company with nobody named gets no draft: there's no one to write to yet.
- LinkedIn, YouTube, social networks and job boards are never read (add more under `skip_domains`).
- Drafts may only use facts from the page, the research notes and your profile: no invented dates, numbers or meetings.

Search results vary and pages can be old, so check each lead before writing. Someone may have changed jobs since the page was published.

## For agents

1. Make sure a profile exists (above) and that the keys are set.
2. Run with `--dry-run` first and show the person the planned searches. Adjust the brief if they look off.
3. Run it, then read the top 20: open each lead's source page and confirm they still hold that role. Drop anyone who doesn't fit.
4. Improve the drafts that need it, keeping to facts from the source page.
5. Hand the drafts back with each lead's name, title, company, score, reasons and source link. The person approves and sends every message.
