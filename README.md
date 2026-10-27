<p align="center">
  <img src="assets/logo-small.png" alt="Cantrip" width="140">
</p>

<h1 align="center">Cantrip</h1>

<p align="center"><b>Go-to-market, cast at will.</b><br>
Open-source spells that turn developer signals into scored leads and drafted outreach.</p>

---

Devtool and AI teams sell to developers, but their best signals are scattered: GitHub stars, event guest lists, Discord, Reddit, talks. Cantrip reads those signals, scores each person against who you actually sell to, and drafts a first note you can review. It works with the tools you already have, and it never sends anything on its own.

Each workflow is a **spell**: a small folder with the rules in TOML and the steps written out so an AI agent can run them too.

## Quick start

```bash
pip install git+https://github.com/cantrip-dev/cantrip
export GITHUB_TOKEN=...   # needed for --repo: GitHub only lists stargazers to signed-in requests

# People who starred a repo
cantrip cast stargazers-to-leads --repo your-org/your-repo --limit 200 --out leads.csv

# People from an event guest list (a Luma CSV export works as-is)
cantrip cast stargazers-to-leads --csv examples/luma-guests.csv --event "Open Source AI Day" --out leads.csv
```

```
3 leads -> leads.csv  (hot 0, warm 2, cold 1)
Nothing was sent. Review the drafts, then send the ones you like yourself.
```

Each row of `leads.csv` has the person, a score from 0 to 100, a tier (hot, warm or cold), **the reasons for the score**, and a drafted note.

## Make it yours

Copy [`spellbook/stargazers-to-leads/spell.toml`](spellbook/stargazers-to-leads/spell.toml) and edit:

- `[icp]`: the companies, roles, topics and languages you sell to, and who to skip
- `[icp.weights]`: how much each signal counts
- `[templates]`: the first note for each tier

Then run `cantrip cast path/to/your-spell --repo ...`.

## The spellbook

| Spell | Signal in | Out |
| --- | --- | --- |
| [stargazers-to-leads](spellbook/stargazers-to-leads/) | GitHub stars, or an event guest list | scored leads with a drafted first note (CSV) |

Coming next: Discord and Reddit sources, and Twenty and HubSpot outputs. Ideas and pull requests are welcome.

## Built for agents

Every spell has a `SPELL.md`, the same workflow written as steps an agent can follow: run the CLI, shortlist the best leads, read their public work, rewrite each note around one true, specific detail, and hand the drafts back to a human. Point your agent at the file and say "cast this spell".

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
