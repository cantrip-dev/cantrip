# Spell: GitHub to leads

**Signal in:** developers found by their GitHub profile, in one of four ways:

| Flag | Who you get |
| --- | --- |
| `--search "agents language:python location:seattle"` | anyone matching a [GitHub user search](https://docs.github.com/en/search-github/searching-on-github/searching-users) |
| `--users handles.txt` | a list of logins or profile URLs you already have |
| `--contributors owner/repo` | people who committed to a repo: yours, a competitor's, or a project your buyers use |
| `--stars owner/repo` | people who starred a repo (GitHub requires a token for this) |

**Out:** one row per person, filled in from their public profile (name, company, bio, location, website, followers, most-used languages), with a fit score, the reasons, and a drafted first note. Nothing is sent.

## Run it

```bash
export GITHUB_TOKEN=...   # 5,000 requests an hour instead of 60
cantrip cast github-to-leads --search "devrel in:bio followers:>200" --limit 100 --out leads.csv
cantrip cast github-to-leads --contributors langchain-ai/langgraph --limit 100 --out leads.csv
```

Each person costs two requests (profile and repos), so without a token keep `--limit` under 30.

## What it scores

The same seniority and function rules as attendees-to-leads, read from the profile's company and bio, plus:
- **Languages** they use most, against your list
- **Influence:** followers above `influencer_followers`
- **Contributed** code, when the source is a repo's contributors
- **Reachable:** a public email, website or blog

## For agents

1. **Pick the source** that matches the ask: a search for "find developers who...", contributors for "people who build on X", a list when the person already has handles.
2. **Run it, then check the scoring** on the top 20. Suggest edits to `spell.toml` rather than changing scores by hand.
3. **Research the shortlist** on public pages only: pinned repos, recent commits, their site or blog. No LinkedIn scraping, no guessed private emails.
4. **Rewrite each draft** in under 90 words around one real thing they built, then **hand the drafts back** for the person to approve and send.
