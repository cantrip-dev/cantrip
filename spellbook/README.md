# The spellbook

Each spell is one go-to-market workflow, small enough to read in a minute.
Spells are product-neutral: what you sell and who you sell to come from your profile (`cantrip.toml`, made by `cantrip init`). A spell is a folder with two files:

- `spell.toml`: how it scores (seniority ladder, weights, tiers) and what the first note says. Your profile is laid over it.
- `SPELL.md`: the same workflow written as steps an AI agent (or a person) can follow, including the parts code can't do well yet, like reading someone's recent work before writing to them.

Copy a spell, change the TOML, and you have your own. Spells never send anything: they draft, a human approves.

| Spell | Signal in | Out |
| --- | --- | --- |
| [attendees-to-leads](attendees-to-leads/) | an event guest list (CSV) | attendees sorted by fit, with follow-up drafts |
| [github-to-leads](github-to-leads/) | GitHub search, logins, contributors or stargazers | developers scored on their profile, with first-note drafts |
| [contributors-to-leads](contributors-to-leads/) | a GitHub repo | its contributors ranked by commits and fit, with drafts about their work |

Ideas for the next spells live in the issues. Pick one up, or propose your own.
