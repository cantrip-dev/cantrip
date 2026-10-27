"""cantrip: turn people who showed interest into a sorted list of leads with drafted notes.

    cantrip ui                        # the same, in your browser
    cantrip init                      # describe what you sell and who you sell to
    cantrip cast attendees-to-leads --csv guests.csv --event "Open Source AI Day"
    cantrip cast github-to-leads --search "agents language:python location:seattle"
    cantrip cast github-to-leads --users handles.txt
    cantrip cast github-to-leads --contributors owner/repo
    cantrip cast web-to-leads --web "AI startups hiring their first DevRel"   # needs an AI model and a search key
    cantrip cast attendees-to-leads --csv guests.csv --research               # research the best leads on the web
    cantrip why-now --save                    # suggest why-now signals for your profile, checked on the web
    cantrip search "devrel leads at AI startups"                             # check your search service works
    cantrip cast attendees-to-leads --csv guests.csv --to notion              # also add them to Notion (or hubspot, twenty, espocrm)
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
from collections.abc import Iterable
from pathlib import Path

from cantrip import __version__, engine, profile, spell
from cantrip.ai import AI, AIError
from cantrip.web import Search, SearchError
from cantrip.lead import Lead
from cantrip.report import summary
from cantrip import sinks
from cantrip.sinks import csv_file as csv_sink
from cantrip.sources import csv_file, github
from cantrip.sources import web as web_source


def _source(args: argparse.Namespace) -> Iterable[Lead] | None:
    enrich = not args.no_enrich
    if args.csv:
        return csv_file.people(args.csv, signal=args.signal)
    if args.search:
        return github.search(args.search, limit=args.limit, do_enrich=enrich)
    if args.users:
        return github.users(Path(args.users).read_text().splitlines(), do_enrich=enrich)
    if args.contributors:
        return github.contributors(args.contributors, limit=args.limit, do_enrich=enrich)
    if args.stars:
        return github.stargazers(args.stars, limit=args.limit, do_enrich=enrich)
    return None


def _progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _check_ai(ai: AI, search: Search | None) -> str:
    if not ai.ready:
        return ("This needs an AI model. Set CANTRIP_AI_KEY (and CANTRIP_AI_BASE_URL / CANTRIP_AI_MODEL for a\n"
                "provider other than OpenAI, or point CANTRIP_AI_BASE_URL at a local Ollama).")
    if search is not None and not search.ready:
        return ("This needs a search service. Set CANTRIP_SEARCH (tinyfish, exa, tavily, brave, serper, serpapi or\n"
                "searxng) and CANTRIP_SEARCH_KEY, or CANTRIP_SEARCH_URL for your own SearXNG.")
    return ""


def cast(args: argparse.Namespace) -> int:
    try:
        mine = profile.load(args.profile)
    except profile.ProfileMissing as err:
        print(err, file=sys.stderr)
        return 2
    if args.web is not None and args.spell == "attendees-to-leads":
        args.spell = "web-to-leads"  # a common slip; the web source needs the web spell's scoring
    config = profile.apply(spell.load(args.spell), mine)
    if args.event:
        config["event_name"] = args.event
    ai_drafts = (config.get("ai_drafts", False) or args.ai_drafts) and not args.no_ai_drafts
    uses_web = args.web is not None or args.research
    crm = None
    if args.to:
        try:
            crm = sinks.connect(args.to)
        except sinks.CRMError as err:
            print(err, file=sys.stderr)
            return 2
    ai = AI.from_env() if (uses_web or ai_drafts) else None
    search = Search.from_env() if uses_web else None
    if ai is not None:
        problem = _check_ai(ai, search)
        if problem:
            print(problem, file=sys.stderr)
            return 2

    if args.web is not None:
        queries = web_source.plan(ai, config, args.web, args.queries)
        _progress("Planned searches:\n" + "\n".join(f"  - {q}" for q in queries))
        _progress(f"Estimated cost: {len(queries)} searches, up to {len(queries) * args.pages} pages read and "
                  f"AI calls to read them, plus up to {args.top} AI drafts"
                  + (f" and {args.top} research lookups." if args.research else "."))
        if args.dry_run:
            return 0
        leads = web_source.find(ai, search, config, queries=queries, pages_per_query=args.pages, progress=_progress)
    else:
        leads = _source(args)
    if leads is None:
        print("Give a source: --csv, --search, --users, --contributors, --stars or --web", file=sys.stderr)
        return 2

    try:
        results = engine.run(config, leads, add_github=args.github, min_tier=args.min_tier)
        if ai is not None and (args.research or ai_drafts):
            engine.enhance(results, config, ai, search, research=args.research, ai_drafts=ai_drafts,
                           top=args.top, progress=_progress)
    except urllib.error.HTTPError as err:
        if err.code in (401, 403):
            print(f"GitHub refused the request ({err.code}). Set GITHUB_TOKEN; for --stars GitHub always "
                  "requires one,\nand a fine-grained token only reads the repos it covers.", file=sys.stderr)
            return 1
        raise
    except (AIError, SearchError) as err:
        print(err, file=sys.stderr)
        return 1

    crm_line = ""
    if crm is not None:
        try:
            counts = sinks.push(crm, results, min_tier=args.crm_tier, progress=_progress)
            crm_line = (f"{crm.label}: {counts['added']} added, {counts['already there']} already there"
                        + (f", {counts['failed']} failed (see the crm column)" if counts["failed"] else "")
                        + (f", {counts['skipped']} skipped (no person named)" if counts["skipped"] else "") + ".")
        except sinks.CRMError as err:
            crm_line = f"Couldn't add leads to {crm.label}: {err}"
    count = csv_sink.write(results, args.out)
    print(f"{count} leads -> {args.out}, best first")
    print(summary(results))
    if crm_line:
        print(crm_line)
    if ai is not None:
        print(f"Used {ai.calls} AI calls" + (f" ({ai.tokens:,} tokens)" if ai.tokens else "")
              + (f" and {search.searches} searches" if search else "")
              + (f"; {search.skipped} pages couldn't be read" if search and search.skipped else "") + ".")
    print("Nothing was sent. Review the drafts, then send the ones you like yourself.")
    return 0


def init(args: argparse.Namespace) -> int:
    answers = {key: getattr(args, key) for key, _, _ in profile.QUESTIONS if getattr(args, key, None)}
    if args.event:
        answers["event"] = args.event
    path = Path(args.out)
    if path.exists() and not args.force:
        print(f"{path} already exists. Edit it, or pass --force to start over.", file=sys.stderr)
        return 1
    try:
        written = profile.init(answers, path)
    except ValueError as err:
        print(err, file=sys.stderr)
        return 2
    print(f"Saved your profile to {written}. Every spell will now score leads against it.")
    print("Next: cantrip cast attendees-to-leads --csv guests.csv   or   cantrip cast github-to-leads --search \"...\"")
    return 0


def why_now(args: argparse.Namespace) -> int:
    try:
        mine = profile.load(args.profile)
    except profile.ProfileMissing as err:
        print(err, file=sys.stderr)
        return 2
    config = profile.apply(spell.load("web-to-leads"), mine)
    ai, search = AI.from_env(), Search.from_env()
    problem = _check_ai(ai, None)
    if problem:
        print(problem, file=sys.stderr)
        return 2
    try:
        found = web_source.suggest_why_now(ai, config, search if search.ready else None, progress=_progress)
    except (AIError, SearchError) as err:
        print(err, file=sys.stderr)
        return 1
    for i, s in enumerate(found, 1):
        print(f"{i}. {s['signal']}\n   why: {s['why']}\n   search: {s['search']}")
        for ex in s["examples"]:
            print(f"   seen on the web: {ex['title'][:70]}  {ex['url']}")
    if not search.ready:
        print("(Set a search service to check each signal on the web.)")
    if args.save and found:
        path = Path(args.profile) if args.profile else profile.DEFAULT_PATH
        answers = _answers(mine)
        answers["why_now"] = list(dict.fromkeys(answers.get("why_now", []) + [s["signal"] for s in found]))
        profile.update(answers, path)
        print(f"Added them to {path} under why_now. Edit or delete any that don't fit.")
    elif found:
        print("Run again with --save to add them to your profile, or copy the ones you like into why_now.")
    return 0


def _answers(mine: dict) -> dict:
    """A loaded profile flattened back into init's answers."""
    return {**mine.get("product", {}), **mine.get("icp", {})}


def search_check(args: argparse.Namespace) -> int:
    search = Search.from_env()
    if not search.ready:
        print(_check_ai(AI(key="x"), search) or "Set CANTRIP_SEARCH first.", file=sys.stderr)
        return 2
    try:
        results = search.search(args.query, args.count)
    except SearchError as err:
        print(err, file=sys.stderr)
        return 1
    print(f"{search.provider} works: {len(results)} results for '{args.query}'")
    for r in results:
        print(f"  {r.title[:70] or '(no title)'}\n    {r.url}" + ("  [page text included]" if len(r.content) > 500 else ""))
    return 0


def ui(args: argparse.Namespace) -> int:
    from cantrip.ui.server import serve

    serve(port=args.port, profile_path=args.profile, open_browser=not args.no_browser)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cantrip", description="Go-to-market, cast at will.")
    parser.add_argument("--version", action="version", version=f"cantrip {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    i = sub.add_parser("init", help="describe what you sell and who you sell to (writes cantrip.toml)",
                       description="Asks a few questions, or takes them as flags (lists are comma-separated).")
    i.add_argument("--name", help="what you sell: a product, service or offer")
    i.add_argument("--pitch", help="one line describing it, as you'd say it to a customer")
    i.add_argument("--buyer-roles", dest="buyer_roles", help="job roles that buy it")
    i.add_argument("--champion-roles", dest="champion_roles", help="job roles that use or champion it")
    i.add_argument("--why-now", dest="why_now", help="signals that make now a good time to reach out, e.g. "
                   "'just raised a seed round' (or let `cantrip why-now` suggest them)")
    i.add_argument("--stages", help="company stages you sell to, e.g. 'seed, series a'")
    i.add_argument("--seniority", choices=list(profile.SENIORITY_SCALE), help="how much seniority matters")
    i.add_argument("--target-companies", dest="target_companies", help="companies you most want")
    i.add_argument("--keywords", help="words in a title, bio or company that signal a good fit")
    i.add_argument("--languages", help="programming languages your users write")
    i.add_argument("--deprioritize", help="words that mark a weaker lead, e.g. student")
    i.add_argument("--exclude", help="companies or email domains to skip")
    i.add_argument("--ask", help="what your first note asks for, e.g. 'a 15-minute call'")
    i.add_argument("--sender", help="your first name, to sign drafts")
    i.add_argument("--event", help="default event name for attendee drafts")
    i.add_argument("--out", default=str(profile.DEFAULT_PATH), help="where to save it (default cantrip.toml)")
    i.add_argument("--force", action="store_true", help="overwrite an existing profile")
    i.set_defaults(func=init)

    u = sub.add_parser("ui", help="open Cantrip in your browser (runs on this computer only)")
    u.add_argument("--port", type=int, default=8765, help="port to use (default 8765)")
    u.add_argument("--profile", help="profile to use and save (default ./cantrip.toml)")
    u.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    u.set_defaults(func=ui)

    w = sub.add_parser("why-now", help="suggest why-now signals for your profile (needs an AI model; a search "
                       "service checks each on the web)")
    w.add_argument("--profile", help="your profile (default ./cantrip.toml)")
    w.add_argument("--save", action="store_true", help="add the suggestions to your profile")
    w.set_defaults(func=why_now)

    q = sub.add_parser("search", help="check your search service: run one search and show the results")
    q.add_argument("query", nargs="?", default="developer relations lead at an AI startup")
    q.add_argument("--count", type=int, default=5)
    q.set_defaults(func=search_check)

    p = sub.add_parser("cast", help="run a spell from the spellbook")
    p.add_argument("spell", help="spell name (e.g. attendees-to-leads) or path to its folder")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--csv", help="CSV of people, e.g. a Luma guest export")
    src.add_argument("--search", help='GitHub user search, e.g. "agents language:python location:seattle"')
    src.add_argument("--users", help="text file of GitHub logins or profile URLs, one per line")
    src.add_argument("--contributors", help="GitHub repo whose contributors to read, as owner/name")
    src.add_argument("--stars", help="GitHub repo whose stargazers to read, as owner/name (needs GITHUB_TOKEN)")
    src.add_argument("--web", nargs="?", const="", metavar="BRIEF",
                     help="search the web for leads that fit your profile; add a brief to steer it (web-to-leads)")
    p.add_argument("--queries", type=int, default=8, help="web searches to run (default 8)")
    p.add_argument("--pages", type=int, default=3, help="pages to read per search (default 3)")
    p.add_argument("--dry-run", action="store_true", help="with --web: show the planned searches and stop")
    p.add_argument("--research", action="store_true", help="research the best leads on the web before drafting")
    p.add_argument("--ai-drafts", action="store_true", help="write the best leads' drafts with AI")
    p.add_argument("--no-ai-drafts", action="store_true", help="use the spell's templates, not AI, for drafts")
    p.add_argument("--top", type=int, default=15, help="how many of the best leads get research or AI drafts (default 15)")
    p.add_argument("--signal", default="registered", choices=["registered", "attended"],
                   help="what the people in the CSV did, when it has no check-in column (default: registered)")
    p.add_argument("--profile", help="your profile (default ./cantrip.toml, made by `cantrip init`)")
    p.add_argument("--event", help="event name to use in the drafts")
    p.add_argument("--github", action="store_true", help="for CSV rows with a GitHub column, add their GitHub profile")
    p.add_argument("--limit", type=int, default=50, help="max people to read from GitHub (default 50)")
    p.add_argument("--no-enrich", action="store_true", help="skip GitHub profile lookups")
    p.add_argument("--min-tier", default="cold", choices=["hot", "warm", "cold"], help="drop leads below this tier")
    p.add_argument("--to", choices=list(sinks.CRMS), help="also add the leads to a CRM: notion, hubspot, twenty or "
                   "espocrm (settings in the README); people already there are left alone")
    p.add_argument("--crm-tier", default="warm", choices=["hot", "warm", "cold"],
                   help="with --to: add leads at this tier or better (default warm)")
    p.add_argument("--out", default="leads.csv", help="where to write the results (default leads.csv)")
    p.set_defaults(func=cast)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
