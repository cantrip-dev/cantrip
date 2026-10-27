# Spell: attendees to leads

**Signal in:** an event guest list: a Luma export or any registration CSV with name, email, company, job title and LinkedIn.
**Out:** the same people sorted best-first, each with a fit score, the reasons for it, and a drafted follow-up note. Nothing is sent.

## Run it

```bash
cantrip cast attendees-to-leads --csv guests.csv --event "Open Source AI Day" --out leads.csv
```

Columns are found by their headers, so custom registration questions work too: a header with "company" in it is the company, "title", "role" or "position" is the job, "linkedin" is the LinkedIn URL. Luma's `checked_in_at` column marks who actually came. If the list has a GitHub column, add `--github` to pull in each person's GitHub profile as well.

Duplicate registrations (same email or LinkedIn URL) are merged. After the run you get the tier counts, the companies that sent several good-fit people (often your best accounts), and the top five leads.

## What it scores

Set in `spell.toml`, every rule with its points:

- **Seniority** from the job title: founder or C-level, VP/head/director, lead/manager, senior
- **Function:** DevRel and community first, then marketing, growth, partnerships and sales, then engineering and product. Change the order to match who buys from you.
- **Your target companies,** matched on company name and email domain
- **Attended** (checked in) rather than only registered
- **Work email** rather than a personal one
- **Lower priority** for students, interns and job seekers; **excluded** companies drop to zero

## For agents

1. **Run it** on the list the person gives you.
2. **Check the scoring.** Read the top 20 and a few from the middle. If a rule is clearly wrong for this person (they sell to engineers, not marketers), suggest the change to `spell.toml` and rerun. Don't change scores by hand.
3. **Shortlist** the hot leads, then warm, up to the number the person asked for (default 20).
4. **Research each one from public pages:** the company's site, its recent news, the person's public posts or talks. Open a LinkedIn URL only to read it if the person has a logged-in browser they let you use; never scrape LinkedIn.
5. **Rewrite each draft** in under 90 words: one specific, true detail, why you're writing, one question. Never invent a conversation at the event, a result or a number.
6. **Hand the drafts back** with each lead's name, title, company, score and reasons. The person approves and sends every message.
