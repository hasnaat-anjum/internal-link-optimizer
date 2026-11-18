"""Command-line interface.

Commands::

    audit      crawl a site (or a local folder) and report on its links
    compare    diff two saved audit snapshots
    history    list saved snapshots for a site

Examples::

    python -m linkoptimizer audit https://example.com
    python -m linkoptimizer audit https://example.com --max-pages 500 --out audit
    python -m linkoptimizer audit --sitemap https://example.com/sitemap.xml https://example.com
    python -m linkoptimizer audit --local ./my-site --out report
    python -m linkoptimizer compare runs/a.json runs/b.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .crawler import crawl_local_folder, crawl_site
from .graph import analyse, inbound_counts, build_graph
from .history import (compare_snapshots, compare_text, load_snapshot,
                      save_snapshot, snapshot_path)
from .report import result_dict, terminal_summary, write_outputs
from .suggest import suggest_links


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="linkoptimizer",
        description="Find the internal links your site is missing — "
                    "orphan pages, broken links and ranked suggestions "
                    "with real anchor text. No API key needed.")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="crawl a site and report on its internal links")
    audit.add_argument("url", nargs="?", default="",
                       help="site to crawl, e.g. https://example.com")
    audit.add_argument("--local", metavar="DIR",
                       help="analyse a local folder of HTML files instead of crawling")
    audit.add_argument("--sitemap", metavar="URL",
                       help="seed the crawl from a sitemap.xml URL")
    audit.add_argument("--max-pages", type=int, default=200,
                       help="maximum pages to crawl (default: 200)")
    audit.add_argument("--delay", type=float, default=0.2,
                       help="seconds between requests (default: 0.2)")
    audit.add_argument("--no-robots", action="store_true",
                       help="ignore robots.txt (not recommended)")
    audit.add_argument("--out", metavar="PREFIX", default="link-report",
                       help="output file prefix for .json/.csv/.html (default: link-report)")
    audit.add_argument("--save-snapshot", action="store_true",
                       help="also save a dated snapshot under runs/ for later comparison")
    audit.add_argument("--quiet", action="store_true",
                       help="print only the summary, no progress lines")

    compare = sub.add_parser("compare", help="compare two saved audit snapshots")
    compare.add_argument("old", help="older snapshot JSON file")
    compare.add_argument("new", help="newer snapshot JSON file")

    history = sub.add_parser("history", help="list saved snapshots")
    history.add_argument("--dir", default="runs", help="snapshot directory (default: runs)")
    return parser


def _run_audit(args) -> int:
    if args.local:
        if not os.path.isdir(args.local):
            print(f"error: folder not found: {args.local}", file=sys.stderr)
            return 2
        site = args.local  # shown as given, so reports stay portable
        result = crawl_local_folder(args.local)
        source = "local-folder"
    else:
        if not args.url:
            print("error: give a site URL, or use --local DIR", file=sys.stderr)
            return 2
        site = args.url if args.url.startswith(("http://", "https://")) else "https://" + args.url
        progress = None if args.quiet else (
            lambda count, url: print(f"[{count}] {url}"))
        try:
            result = crawl_site(site, max_pages=args.max_pages,
                                delay=args.delay,
                                respect_robots=not args.no_robots,
                                sitemap_url=args.sitemap, progress=progress)
        except Exception as exc:  # network failure before any page
            print(f"error: crawl failed: {exc}", file=sys.stderr)
            return 1
        source = "sitemap" if args.sitemap else "crawl"

    if not result.pages and not result.broken:
        print("error: no pages could be fetched — check the URL and your connection.",
              file=sys.stderr)
        return 1

    stats = analyse(result.pages, result.broken)
    suggestions = suggest_links(result.pages, stats.authority,
                                set(stats.orphan_pages))
    data = result_dict(site, result.pages, stats, suggestions, source=source,
                       errors=result.errors,
                       skipped_robots=result.skipped_robots)

    # Fill in real inbound counts for the JSON report.
    graph = build_graph(result.pages)
    inbound = inbound_counts(graph)
    for url, info in data["pages"].items():
        info["inbound_links"] = inbound.get(url, 0)

    paths = write_outputs(data, args.out)
    if args.save_snapshot:
        snap = save_snapshot(data, snapshot_path("runs", site))
        paths["snapshot"] = snap
    print(terminal_summary(data))
    print("Reports written:")
    for kind, path in paths.items():
        print(f"  {kind}: {path}")
    if result.errors:
        print(f"Note: {len(result.errors)} page(s) could not be fetched "
              f"(details in the JSON report under 'fetch_errors').")
    if result.skipped_robots:
        print(f"Note: {len(result.skipped_robots)} URL(s) skipped per robots.txt.")
    return 0


def _run_compare(args) -> int:
    try:
        old = load_snapshot(args.old)
        new = load_snapshot(args.new)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read snapshot: {exc}", file=sys.stderr)
        return 2
    print(compare_text(compare_snapshots(old, new)))
    return 0


def _run_history(args) -> int:
    if not os.path.isdir(args.dir):
        print(f"No snapshots yet (folder {args.dir} does not exist).")
        return 0
    files = sorted(f for f in os.listdir(args.dir) if f.endswith(".json"))
    if not files:
        print(f"No snapshots in {args.dir} yet.")
        return 0
    print(f"Snapshots in {args.dir}:")
    for name in files:
        try:
            data = load_snapshot(os.path.join(args.dir, name))
            summary = data["summary"]
            print(f"  {name} — {data['site']} — "
                  f"health {summary['health_score']} "
                  f"({summary['pages_crawled']} pages, "
                  f"{summary['orphan_pages']} orphans)")
        except Exception:
            print(f"  {name} — unreadable")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point: parse arguments and dispatch to the subcommand."""
    args = _build_parser().parse_args(argv)
    if args.command == "audit":
        return _run_audit(args)
    if args.command == "compare":
        return _run_compare(args)
    if args.command == "history":
        return _run_history(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
