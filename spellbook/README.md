# The spellbook

Each spell is one go-to-market workflow, small enough to read in a minute.
A spell is a folder with two files:

- `spell.toml`: the rules. Who counts as a good fit, how to score them, what the first note says.
- `SPELL.md`: the same workflow written as steps an AI agent (or a person) can follow, including the parts code can't do well yet, like reading someone's recent work before writing to them.

Copy a spell, change the TOML, and you have your own. Spells never send anything: they draft, a human approves.

| Spell | Signal in | Out |
| --- | --- | --- |
| [attendees-to-leads](attendees-to-leads/) | an event guest list (CSV) | attendees sorted by fit, with follow-up drafts |
| [github-to-leads](github-to-leads/) | GitHub search, logins, contributors or stargazers | developers scored on their profile, with first-note drafts |

Ideas for the next spells live in the issues. Pick one up, or propose your own.
