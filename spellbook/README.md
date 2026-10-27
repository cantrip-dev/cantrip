# The spellbook

Each spell is one go-to-market workflow, small enough to read in a minute.
A spell is a folder with two files:

- `spell.toml`: the rules. Who counts as a good fit, how to score them, what the first note says.
- `SPELL.md`: the same workflow written as steps an AI agent (or a person) can follow, including the parts code can't do well yet, like reading someone's recent work before writing to them.

Copy a spell, change the TOML, and you have your own. Spells never send anything: they draft, a human approves.

| Spell | Signal in | Out |
| --- | --- | --- |
| [stargazers-to-leads](stargazers-to-leads/) | GitHub stars, or an event guest list (CSV) | scored leads with a drafted first note, as CSV |

Ideas for the next spells live in the issues. Pick one up, or propose your own.
