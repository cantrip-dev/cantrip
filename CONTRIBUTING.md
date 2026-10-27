# Contributing to Cantrip

Thanks for helping! The fastest ways in:

- **Write a spell.** Copy `spellbook/attendees-to-leads/`, change it for a new signal (Discord joins, Reddit threads, docs visits...) and open a pull request.
- **Add a source or a sink.** Sources live in `cantrip/sources/`, outputs in `cantrip/sinks/`. Twenty and HubSpot outputs are wanted.
- **Report what didn't work** in an issue, with the command you ran.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Cantrip has no runtime dependencies on purpose. Please keep it that way unless there's a strong reason.

## Sign off your commits (DCO)

We use the [Developer Certificate of Origin](https://developercertificate.org/). It says you wrote the change (or have the right to submit it) and agree to license it under Apache 2.0. Add a sign-off line to every commit with `-s`:

```bash
git commit -s -m "Add a Discord source"
```

This adds `Signed-off-by: Your Name <you@example.com>` to the commit message.

## Ground rules for spells

Spells draft, humans send. A spell must not send messages on its own, scrape sites that forbid it (LinkedIn included), or guess private email addresses.
