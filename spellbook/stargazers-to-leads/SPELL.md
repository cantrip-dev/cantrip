# Spell: stargazers to leads

**Signal in:** people who starred a GitHub repo, or a guest list from an event (a Luma CSV export works as-is).
**Out:** one row per person, with a fit score, the reasons for it, and a drafted first note. Nothing is sent.

## Run it

```bash
cantrip cast stargazers-to-leads --repo your-org/your-repo --limit 200 --out leads.csv
cantrip cast stargazers-to-leads --csv luma-guests.csv --event "Open Source AI Day" --out leads.csv
```

GitHub only lists stargazers to signed-in requests, so set `GITHUB_TOKEN` for `--repo`: a classic token with no scopes reads any public repo, a fine-grained token only the repos it covers. Edit `spell.toml` (or a copy of it) to describe who you sell to.

## For agents

Follow these steps when a person asks you to cast this spell. The CLI covers steps 1-3; steps 4-6 are where you add judgement.

1. **Gather.** Run the command above for the source the person names.
2. **Score.** The CLI scores each lead against `[icp]` and writes the reasons. Don't change scores silently: if a rule looks wrong, say which one and suggest the edit to `spell.toml`.
3. **Shortlist.** Take the `hot` leads, then `warm`, up to the number the person asked for (default 20).
4. **Research.** For each shortlisted lead, read what they've made public: their GitHub profile and pinned repos, their company's site, a recent post or talk. Use public pages only. No LinkedIn scraping, no guessing private emails.
5. **Rewrite the draft.** Keep it under 90 words. Mention one specific, true thing you found, say why you're writing, and ask one question. Never invent a shared history, a result or a number.
6. **Hand it back for approval.** Show the person each draft with the lead's name, score and reasons. Send nothing. The person approves and sends each message themselves, or through a tool they have chosen.

## Rules every run keeps

- Drafts only. A human approves every message.
- Public data only, and only what a person chose to make public.
- Respect opt-outs: anyone in `exclude` or who has asked not to be contacted is skipped.
- Email at a human pace from a properly set-up domain (SPF, DKIM, an unsubscribe line). That's the sender's job, and the spell reminds them.
