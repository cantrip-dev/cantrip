"""cantrip: turn developer signals into scored leads with drafted notes.

    cantrip cast stargazers-to-leads --repo owner/name --out leads.csv
    cantrip cast stargazers-to-leads --csv luma-guests.csv --out leads.csv
"""

from __future__ import annotations

import argparse
import sys
import urllib.error

from cantrip import __version__, spell
from cantrip.draft import draft
from cantrip.score import score
from cantrip.sinks import csv_file as csv_sink
from cantrip.sources import csv_file, github_stars


def cast(args: argparse.Namespace) -> int:
    config = spell.load(args.spell)
    if args.event:
        config["event_name"] = args.event
    if args.repo:
        leads = github_stars.stargazers(args.repo, limit=args.limit, enrich=not args.no_enrich)
    elif args.csv:
        leads = csv_file.people(args.csv, signal=args.signal)
    else:
        print("Give a source: --repo owner/name or --csv file.csv", file=sys.stderr)
        return 2

    try:
        results = [draft(score(lead, config.get("icp", {})), config) for lead in leads]
    except urllib.error.HTTPError as err:
        if err.code in (401, 403):
            print("GitHub refused the request. Listing stargazers needs GITHUB_TOKEN set: a classic token\n"
                  "with no scopes reads any public repo; a fine-grained token reads only repos it covers.",
                  file=sys.stderr)
            return 1
        raise
    results.sort(key=lambda lead: lead.score, reverse=True)
    if args.min_tier != "cold":
        keep = {"hot"} if args.min_tier == "hot" else {"hot", "warm"}
        results = [lead for lead in results if lead.tier in keep]
    count = csv_sink.write(results, args.out)

    tiers = {t: sum(1 for lead in results if lead.tier == t) for t in ("hot", "warm", "cold")}
    print(f"{count} leads -> {args.out}  (hot {tiers['hot']}, warm {tiers['warm']}, cold {tiers['cold']})")
    print("Nothing was sent. Review the drafts, then send the ones you like yourself.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cantrip", description="Go-to-market, cast at will.")
    parser.add_argument("--version", action="version", version=f"cantrip {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("cast", help="run a spell from the spellbook")
    p.add_argument("spell", help="spell name (e.g. stargazers-to-leads) or path to its folder")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--repo", help="GitHub repo whose stargazers to read, as owner/name")
    src.add_argument("--csv", help="CSV of people, e.g. a Luma guest export")
    p.add_argument("--signal", default="registered", choices=["registered", "attended", "starred"],
                   help="what the people in the CSV did (default: registered)")
    p.add_argument("--event", help="event name to use in drafts for CSV sources")
    p.add_argument("--limit", type=int, default=100, help="max stargazers to read (default 100)")
    p.add_argument("--no-enrich", action="store_true", help="skip GitHub profile lookups")
    p.add_argument("--min-tier", default="cold", choices=["hot", "warm", "cold"], help="drop leads below this tier")
    p.add_argument("--out", default="leads.csv", help="where to write the results (default leads.csv)")
    p.set_defaults(func=cast)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
