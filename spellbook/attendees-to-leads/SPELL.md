# Spell: attendees to leads

**Signal in:** an event guest list: a Luma export or any registration CSV with name, email, company, job title and LinkedIn.
**Out:** the same people sorted best-first, each with a fit score, the reasons for it, and a drafted follow-up note. Nothing is sent.

## Before the first run: the profile

Every run scores against the person's profile, `cantrip.toml`. If there isn't one, interview them first, in one short message:

1. What are you selling, and how would you describe it to a customer in one line?
2. Who buys it, and who uses or champions it? (job roles)
3. Any companies you most want, and anyone to skip (your own company, competitors)?
4. What should a first note ask for, and how do you sign your name?

Then save their answers with `cantrip init --name ... --pitch ... --buyer-roles ... --champion-roles ... --target-companies ... --exclude ... --ask ... --sender ...`. Fill in fit keywords (and, for GitHub, languages) from what they told you and show them the file. Never guess what they sell.

## Run it

```bash
cantrip cast attendees-to-leads --csv guests.csv --event "Open Source AI Day" --out leads.csv
```

Columns are found by their headers, so custom registration questions work too: a header with "company" in it is the company, "title", "role" or "position" is the job, "linkedin" is the LinkedIn URL. Luma's `checked_in_at` column marks who actually came. If the list has a GitHub column, add `--github` to pull in each person's GitHub profile as well.

Duplicate registrations (same email or LinkedIn URL) are merged. After the run you get the tier counts, the companies that sent several good-fit people (often your best accounts), and the top five leads.

## What it scores

Who counts as a good fit comes from your profile. The spell adds the event-specific signals:

- **Role:** the profile's buyer roles count most, then its champion roles
- **Seniority** from the job title (founder or C-level, VP/head/director, lead/manager, senior), scaled by the profile's `seniority` setting
- **Your target companies,** matched on company name and email domain, and **fit keywords** in the title or company
- **Attended** (checked in) rather than only registered
- **Work email** rather than a personal one
- **Lower priority** for the profile's `deprioritize` words; **excluded** companies drop to zero

## For agents

1. **Run it** on the list the person gives you.
2. **Check the scoring.** Read the top 20 and a few from the middle. If the order looks wrong for what they sell, suggest a change to their profile (roles, keywords, seniority) and rerun. Don't change scores by hand.
3. **Shortlist** the hot leads, then warm, up to the number the person asked for (default 20).
4. **Research each one from public pages:** the company's site, its recent news, the person's public posts or talks. Open a LinkedIn URL only to read it if the person has a logged-in browser they let you use; never scrape LinkedIn.
5. **Rewrite each draft** in under 90 words: one specific, true detail, why you're writing, one question. Never invent a conversation at the event, a result or a number.
6. **Hand the drafts back** with each lead's name, title, company, score and reasons. The person approves and sends every message.
