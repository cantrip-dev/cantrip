# Spell: forks to leads

**Signal in:** a GitHub repo, as `owner/name`. Cantrip reads the people who forked it, newest forks first, and
notes the day each one last pushed to their fork, if they did since forking: those people are building on the
code, not just saving a copy. Like the contributors and stargazers sources, it leaves out bots, organizations,
AI coding agents that GitHub lists as users, and, when an organization owns the repo, its staff (by company,
email or website domain, bio @mention or login). Anyone else you don't want, mark **No** in the app (they go
under `[skip]` in the profile and never come back).

Good repos to read:
- **Yours:** people who forked it and changed it want something it doesn't do yet.
- **A project your buyers build on:** a fork with new pushes is someone shipping on that stack.
- **A competitor's:** people adapting the alternative to their needs know where it falls short.

**Out:** one row per person, filled in from their public profile (name, company, bio, location, website, followers,
most-used languages), with a fit score, the reasons, and a drafted first note about their fork. Nothing is sent.

## Before the first run: the profile

Every run scores against the person's profile, `cantrip.toml`. If there isn't one, interview them first, in one short message:

1. What are you selling, and how would you describe it to a customer in one line?
2. Who buys it, and who uses or champions it? (job roles)
3. Any companies you most want, and anyone to skip (your own company, competitors)?
4. What should a first note ask for, and how do you sign your name?

Then save their answers with `cantrip init --name ... --pitch ... --buyer-roles ... --champion-roles ... --target-companies ... --exclude ... --ask ... --sender ...`. Fill in fit keywords and languages from what they told you and show them the file. Never guess what they sell.

## Run it

```bash
export GITHUB_TOKEN=...   # 5,000 requests an hour instead of 60; a read-only token is enough
cantrip cast forks-to-leads --forks langchain-ai/langgraph --limit 100 --out leads.csv
```

Each person costs two requests (profile and repos), so without a token keep `--limit` under 30. GitHub lists
forks newest first, so a low limit keeps the most recent.

## What it scores

Your profile's buyer and champion roles, seniority, target companies and keywords, read from the GitHub profile's company and bio, plus:
- **Forked:** every person gets points for forking the repo
- **Pushed to their fork:** extra points when they pushed to it after forking (a push in the first 10 minutes doesn't count; GitHub can touch a new fork itself). Syncing a fork with the original counts as a push too, so read the fork before writing.
- **Languages** they use most, against your profile's `languages`
- **Influence:** followers above `influencer_followers`
- **Reachable:** a public email, website or blog

## For agents

1. **Run it, then check the scoring** on the top 20. Suggest edits to the person's profile rather than changing scores by hand.
2. **Look at what each person on the shortlist changed** in their fork, on public pages only: compare it with the
   original (`https://github.com/OWNER/REPO/compare/main...LOGIN:REPO:main`) and read their commit messages.
   No LinkedIn scraping, no guessed private emails.
3. **Rewrite each draft** in under 90 words around one real change they made, named plainly ("your fork adds a
   Postgres backend"). If the fork has no changes of its own, don't pretend it does. Keep the person's pitch and ask word for word.
4. **Hand the drafts back** for the person to approve and send.
