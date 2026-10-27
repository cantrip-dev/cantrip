<p align="center">
  <img src="assets/logo-small.png" alt="Cantrip" width="140">
</p>

<h1 align="center">Cantrip</h1>

<p align="center"><b>Go-to-market, cast at will.</b><br>
Open-source spells that turn event attendees and GitHub profiles into sorted leads and drafted outreach.</p>

---

Devtool and AI teams sell to developers, and their best leads are people who already showed up: at an event, in a repo, on GitHub. Cantrip takes those people, scores each one against who you actually sell to, sorts them best-first, and drafts a first note you can review. It works with the tools you already have, and it never sends anything on its own.

Each workflow is a **spell**: a small folder with the rules in TOML and the steps written out so an AI agent can run them too.

## Quick start

```bash
pip install git+https://github.com/cantrip-dev/cantrip

# An event guest list (a Luma export or any CSV with name, email, company, title, LinkedIn)
cantrip cast attendees-to-leads --csv examples/luma-guests.csv --event "Open Source AI Day" --out leads.csv

# Developers found by their GitHub profile
export GITHUB_TOKEN=...   # optional: 5,000 requests an hour instead of 60
cantrip cast github-to-leads --search '"developer advocate" in:bio followers:>100' --limit 50 --out leads.csv
```

```
4 leads -> leads.csv, best first
hot 1, warm 2, cold 1
Companies with several good-fit people: Example Labs (2)
Top leads:
   80  Ada Example, Head of Developer Relations at Example Labs
Nothing was sent. Review the drafts, then send the ones you like yourself.
```

Each row of `leads.csv` has the person, a score from 0 to 100, a tier (hot, warm or cold), **the reasons for the score**, and a drafted note.

## The spellbook

| Spell | Signal in | Out |
| --- | --- | --- |
| [attendees-to-leads](spellbook/attendees-to-leads/) | an event guest list: name, email, company, job title, LinkedIn | attendees sorted by seniority, role and fit, with follow-up drafts |
| [github-to-leads](spellbook/github-to-leads/) | a GitHub user search, a list of logins, a repo's contributors or stargazers | developers scored on their public profile, with first-note drafts |

Coming next: Discord and Reddit sources, and Twenty and HubSpot outputs. Ideas and pull requests are welcome.

## Make it yours

Copy a spell's `spell.toml` and edit:

- `[icp]`: your target companies, topics and languages, who to deprioritize and who to skip
- `[[icp.seniority]]` and `[[icp.functions]]`: which titles and roles count, and how much
- `[icp.weights]`: how much each other signal counts
- `[templates]`: the first note for each tier

Then run `cantrip cast path/to/your-spell --csv ...`.

## Built for agents

Every spell has a `SPELL.md`, the same workflow written as steps an agent can follow: run the CLI, check the scoring, shortlist the best leads, read their public work, rewrite each note around one true, specific detail, and hand the drafts back to a human. Point your agent at the file and say "cast this spell".

## Principles

- **Drafts, not sends.** A human approves every message.
- **Public data only.** No LinkedIn scraping and no guessed private emails.
- **Explainable.** Every score comes with its reasons.
- **Connects, doesn't rebuild.** Your CRM, email and analytics stay where they are.
- **No dependencies.** Plain Python 3.11+, so it's easy to read, audit and fork.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). We use DCO sign-off (`git commit -s`).

## License

[Apache 2.0](LICENSE)
