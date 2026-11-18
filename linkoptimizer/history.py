"""Run history: save each audit and compare runs over time.

Every ``audit`` run can save its JSON result as a snapshot. ``compare``
then diffs two snapshots and reports what changed: orphans fixed, new
orphans, broken links fixed or introduced, health-score movement and
suggestion count. That turns a one-off audit into a repeatable check you
can run weekly and watch improve.
"""

from __future__ import annotations

import json
import os
from datetime import datetime


def snapshot_path(out_dir: str, site: str) -> str:
    """Default snapshot filename for a site, e.g. ``runs/example-com-2026-11-18.json``."""
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in site)
    stamp = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"{safe}-{stamp}.json")


def save_snapshot(data: dict, path: str) -> str:
    """Write a snapshot file; returns the path written."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    return path


def load_snapshot(path: str) -> dict:
    """Read a snapshot file back."""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def compare_snapshots(old: dict, new: dict) -> dict:
    """Diff two snapshots. Returns a plain dict of changes."""
    old_summary, new_summary = old["summary"], new["summary"]
    old_orphans = set(old.get("orphan_pages", []))
    new_orphans = set(new.get("orphan_pages", []))
    old_broken = set(old.get("broken_links", {}))
    new_broken = set(new.get("broken_links", {}))
    old_sugg = {(item["source_url"], item["target_url"]) for item in old["suggestions"]}
    new_sugg = {(item["source_url"], item["target_url"]) for item in new["suggestions"]}
    return {
        "old_date": old.get("generated_at", "?"),
        "new_date": new.get("generated_at", "?"),
        "site": new.get("site", old.get("site", "")),
        "health_score": {"before": old_summary["health_score"],
                         "after": new_summary["health_score"],
                         "change": new_summary["health_score"] - old_summary["health_score"]},
        "pages": {"before": old_summary["pages_crawled"],
                  "after": new_summary["pages_crawled"]},
        "orphans_fixed": sorted(old_orphans - new_orphans),
        "orphans_new": sorted(new_orphans - old_orphans),
        "broken_fixed": sorted(old_broken - new_broken),
        "broken_new": sorted(new_broken - old_broken),
        "suggestions_resolved": len(old_sugg - new_sugg),
        "suggestions_new": len(new_sugg - old_sugg),
        "suggestions_now": new_summary["suggestions"],
    }


def compare_text(diff: dict) -> str:
    """Human-readable comparison report."""
    health = diff["health_score"]
    arrow = "▲" if health["change"] > 0 else ("▼" if health["change"] < 0 else "–")
    lines = [
        "",
        f"Internal-link progress — {diff['site']}",
        f"Health score: {health['before']} → {health['after']} "
        f"({arrow} {health['change']:+d})",
        f"Pages: {diff['pages']['before']} → {diff['pages']['after']}  •  "
        f"Open suggestions now: {diff['suggestions_now']}",
        f"Orphans fixed: {len(diff['orphans_fixed'])}  •  "
        f"New orphans: {len(diff['orphans_new'])}",
        f"Broken links fixed: {len(diff['broken_fixed'])}  •  "
        f"New broken links: {len(diff['broken_new'])}",
        f"Suggestions resolved: {diff['suggestions_resolved']}  •  "
        f"New suggestions: {diff['suggestions_new']}",
    ]
    for label, items in (("Orphans fixed", diff["orphans_fixed"]),
                         ("New orphans", diff["orphans_new"]),
                         ("Broken links fixed", diff["broken_fixed"]),
                         ("New broken links", diff["broken_new"])):
        if items:
            lines.append(f"{label}:")
            for item in items[:10]:
                lines.append(f"  - {item}")
    lines.append("")
    return "\n".join(lines)
