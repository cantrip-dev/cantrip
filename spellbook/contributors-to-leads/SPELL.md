# Spell: contributors to leads

**Signal in:** a GitHub repo, as `owner/name`. Cantrip reads the people who committed to it, most commits first, with
each person's commit count. It leaves out bots, AI coding agents that GitHub lists as users (Cursor Agent,
Claude, Codex...), and, when an organization owns the repo, people whose profile names that company: they're
its team, not leads. People who leave their company blank can't be told apart, so check the shortlist.

Good repos to read:
- **Yours:** the people who already improved your project are your likeliest champions.
- **A project your buyers build on:** its contributors know the problem you solve.
- **A competitor's:** people who build the alternative know exactly what's missing.

**Out:** one row per person, filled in from their public profile (name, company, bio, location, website, followers,
most-used languages) and their commit count, with a fit score, the reasons, and a drafted first note about their
commits. Nothing is sent.

## Before the first run: the profile

Every run scores against the person's profile, `cantrip.toml`. If there isn't one, interview them first, in one short message:

1. What are you selling, and how would you describe it to a customer in one line?
2. Who buys it, and who uses or champions it? (job roles)
3. Any companies you most want, and anyone to skip (your own company, competitors)?
4. What should a first note ask for, and how do you sign your name?

Then save their answers with `cantrip init --name ... --pitch ... --buyer-roles ... --champion-roles ... --target-companies ... --exclude ... --ask ... --sender ...`. Fill in fit keywords and languages from what they told you and show them the file. Never guess what they sell.

When the repo is their own, add their company to `exclude` too, so their team doesn't show up from other repos.

## Run it

```bash
export GITHUB_TOKEN=...   # 5,000 requests an hour instead of 60; a read-only token is enough
cantrip cast contributors-to-leads --contributors langchain-ai/langgraph --limit 100 --out leads.csv
```

Each person costs two requests (profile and repos), so without a token keep `--limit` under 30. GitHub lists
contributors with the most commits first, so a low limit keeps the people who did the most.

## What it scores

Your profile's buyer and champion roles, seniority, target companies and keywords, read from the GitHub profile's company and bio, plus:
- **Contributed:** every contributor gets points for committing to the repo
- **Core contributor:** extra points at `core_contributions` commits or more (10 by default)
- **Languages** they use most, against your profile's `languages`
- **Influence:** followers above `influencer_followers`
- **Reachable:** a public email, website or blog

## For agents

1. **Run it, then check the scoring** on the top 20. Suggest edits to the person's profile rather than changing scores by hand.
2. **Read what each person on the shortlist actually did** in that repo, on public pages only: their merged pull requests
   (`https://github.com/OWNER/REPO/pulls?q=author:LOGIN+is:merged`) and the parts of the code they touched.
   No LinkedIn scraping, no guessed private emails.
3. **Rewrite each draft** in under 90 words around one real change they made, named plainly ("your fix to the retry
   logic"). Don't flatter or inflate it, and keep the person's pitch and ask word for word.
4. **Hand the drafts back** for the person to approve and send.
