"""cantrip: turn people who showed interest into a sorted list of leads with drafted notes.

    cantrip cast attendees-to-leads --csv guests.csv --event "Open Source AI Day"
    cantrip cast github-to-leads --search "agents language:python location:seattle"
    cantrip cast github-to-leads --users handles.txt
    cantrip cast github-to-leads --contributors owner/repo
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
from collections.abc import Iterable, Iterator
from pathlib import Path

from cantrip import __version__, spell
from cantrip.draft import draft
from cantrip.lead import Lead
from cantrip.report import summary
from cantrip.score import score
from cantrip.sinks import csv_file as csv_sink
from cantrip.sources import csv_file, github


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


def _unique(leads: Iterable[Lead]) -> Iterator[Lead]:
    seen = set()
    for lead in leads:
        if lead.key and lead.key in seen:
            continue
        seen.add(lead.key)
        yield lead


def cast(args: argparse.Namespace) -> int:
    config = spell.load(args.spell)
    if args.event:
        config["event_name"] = args.event
    leads = _source(args)
    if leads is None:
        print("Give a source: --csv, --search, --users, --contributors or --stars", file=sys.stderr)
        return 2

    results = []
    try:
        for lead in _unique(leads):
            if args.github and lead.github and not lead.followers:
                github.enrich(lead)
            results.append(draft(score(lead, config.get("icp", {})), config))
    except urllib.error.HTTPError as err:
        if err.code in (401, 403):
            print(f"GitHub refused the request ({err.code}). Set GITHUB_TOKEN; for --stars GitHub always "
                  "requires one,\nand a fine-grained token only reads the repos it covers.", file=sys.stderr)
            return 1
        raise

    results.sort(key=lambda lead: lead.score, reverse=True)
    if args.min_tier != "cold":
        keep = {"hot"} if args.min_tier == "hot" else {"hot", "warm"}
        results = [lead for lead in results if lead.tier in keep]
    count = csv_sink.write(results, args.out)
    print(f"{count} leads -> {args.out}, best first")
    print(summary(results))
    print("Nothing was sent. Review the drafts, then send the ones you like yourself.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cantrip", description="Go-to-market, cast at will.")
    parser.add_argument("--version", action="version", version=f"cantrip {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("cast", help="run a spell from the spellbook")
    p.add_argument("spell", help="spell name (e.g. attendees-to-leads) or path to its folder")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--csv", help="CSV of people, e.g. a Luma guest export")
    src.add_argument("--search", help='GitHub user search, e.g. "agents language:python location:seattle"')
    src.add_argument("--users", help="text file of GitHub logins or profile URLs, one per line")
    src.add_argument("--contributors", help="GitHub repo whose contributors to read, as owner/name")
    src.add_argument("--stars", help="GitHub repo whose stargazers to read, as owner/name (needs GITHUB_TOKEN)")
    p.add_argument("--signal", default="registered", choices=["registered", "attended"],
                   help="what the people in the CSV did, when it has no check-in column (default: registered)")
    p.add_argument("--event", help="event name to use in the drafts")
    p.add_argument("--github", action="store_true", help="for CSV rows with a GitHub column, add their GitHub profile")
    p.add_argument("--limit", type=int, default=50, help="max people to read from GitHub (default 50)")
    p.add_argument("--no-enrich", action="store_true", help="skip GitHub profile lookups")
    p.add_argument("--min-tier", default="cold", choices=["hot", "warm", "cold"], help="drop leads below this tier")
    p.add_argument("--out", default="leads.csv", help="where to write the results (default leads.csv)")
    p.set_defaults(func=cast)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
