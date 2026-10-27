"""cantrip: turn people who showed interest into a sorted list of leads with drafted notes.

    cantrip ui                        # the same, in your browser
    cantrip init                      # describe what you sell and who you sell to
    cantrip cast attendees-to-leads --csv guests.csv --event "Open Source AI Day"
    cantrip cast github-to-leads --search "agents language:python location:seattle"
    cantrip cast github-to-leads --users handles.txt
    cantrip cast github-to-leads --contributors owner/repo
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
from collections.abc import Iterable
from pathlib import Path

from cantrip import __version__, engine, profile, spell
from cantrip.lead import Lead
from cantrip.report import summary
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


def cast(args: argparse.Namespace) -> int:
    try:
        mine = profile.load(args.profile)
    except profile.ProfileMissing as err:
        print(err, file=sys.stderr)
        return 2
    config = profile.apply(spell.load(args.spell), mine)
    if args.event:
        config["event_name"] = args.event
    leads = _source(args)
    if leads is None:
        print("Give a source: --csv, --search, --users, --contributors or --stars", file=sys.stderr)
        return 2

    try:
        results = engine.run(config, leads, add_github=args.github, min_tier=args.min_tier)
    except urllib.error.HTTPError as err:
        if err.code in (401, 403):
            print(f"GitHub refused the request ({err.code}). Set GITHUB_TOKEN; for --stars GitHub always "
                  "requires one,\nand a fine-grained token only reads the repos it covers.", file=sys.stderr)
            return 1
        raise

    count = csv_sink.write(results, args.out)
    print(f"{count} leads -> {args.out}, best first")
    print(summary(results))
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
    p.add_argument("--profile", help="your profile (default ./cantrip.toml, made by `cantrip init`)")
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
