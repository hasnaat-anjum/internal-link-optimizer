"""Reports: turn an analysis into something a human can act on.

Four outputs, all generated from the same data:

* **terminal** — a short summary printed after every run,
* **JSON** — the full machine-readable result (also the snapshot format),
* **CSV** — one row per suggestion, ready for a spreadsheet or a task list,
* **HTML** — a self-contained, styled report you can open in a browser
  and share with a client or a team.
"""

from __future__ import annotations

import csv
import html
import io
import json
from datetime import datetime, timezone

from .graph import GraphStats, health_grade
from .parser import PageData
from .suggest import Suggestion

PAGE_SIZE = 50  # rows per HTML table page (keeps big reports readable)


def result_dict(site: str, pages: dict[str, PageData], stats: GraphStats,
                suggestions: list[Suggestion], source: str = "crawl",
                errors: dict | None = None,
                skipped_robots: list | None = None) -> dict:
    """The complete analysis as plain data (JSON-serialisable)."""
    return {
        "tool": "internal-link-optimizer",
        "version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "site": site,
        "source": source,
        "summary": {
            "pages_crawled": stats.total_pages,
            "content_links": stats.total_content_links,
            "avg_inbound_links": round(stats.avg_inbound, 2),
            "orphan_pages": len(stats.orphan_pages),
            "weakly_linked_pages": len(stats.weakly_linked_pages),
            "dead_end_pages": len(stats.dead_end_pages),
            "pages_with_broken_links": len(stats.broken_links),
            "suggestions": len(suggestions),
            "health_score": stats.health_score,
            "health_grade": health_grade(stats.health_score),
        },
        "orphan_pages": stats.orphan_pages,
        "weakly_linked_pages": stats.weakly_linked_pages,
        "dead_end_pages": stats.dead_end_pages,
        "broken_links": stats.broken_links,
        "fetch_errors": errors or {},
        "skipped_robots": skipped_robots or {},
        "authority": {url: round(score, 5)
                      for url, score in sorted(stats.authority.items(),
                                               key=lambda item: -item[1])},
        "pages": {
            url: {
                "title": page.title,
                "h1": page.h1,
                "word_count": page.word_count,
                "inbound_links": 0,  # filled by caller when needed
                "outbound_content_links": len(page.content_links),
                "status": page.status,
            }
            for url, page in pages.items()
        },
        "suggestions": [item.to_dict() for item in suggestions],
    }


def terminal_summary(data: dict) -> str:
    """Short human-readable summary for the terminal."""
    summary = data["summary"]
    lines = [
        "",
        f"Internal Link Optimizer — {data['site']}",
        f"Health score: {summary['health_score']}/100 "
        f"(grade {summary['health_grade']})",
        f"Pages crawled: {summary['pages_crawled']}  •  "
        f"Content links: {summary['content_links']}  •  "
        f"Avg inbound links per page: {summary['avg_inbound_links']}",
        f"Orphan pages: {summary['orphan_pages']}  •  "
        f"Weakly linked: {summary['weakly_linked_pages']}  •  "
        f"Dead-end pages: {summary['dead_end_pages']}  •  "
        f"Pages with broken links: {summary['pages_with_broken_links']}",
        f"Link suggestions: {summary['suggestions']}",
    ]
    if data["orphan_pages"]:
        lines.append("Orphans (fix these first):")
        for url in data["orphan_pages"][:10]:
            lines.append(f"  - {url}")
    top = data["suggestions"][:5]
    if top:
        lines.append("Top suggestions:")
        for item in top:
            lines.append(f"  - {item['source_url']}  →  {item['target_url']} "
                         f"(score {item['score']}, anchor: “{item['anchor']}”)")
    lines.append("")
    return "\n".join(lines)


def suggestions_csv(suggestions: list[Suggestion]) -> str:
    """Suggestions as CSV text (source, target, score, anchor, reason)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["source_url", "target_url", "score", "anchor_text",
                     "sentence", "reason"])
    for item in suggestions:
        writer.writerow([item.source_url, item.target_url, item.score,
                         item.anchor, item.sentence, item.reason])
    return buffer.getvalue()


def _esc(text: str) -> str:
    return html.escape(text or "")


def html_report(data: dict) -> str:
    """Self-contained HTML report (inline CSS, no external assets)."""
    summary = data["summary"]
    grade = summary["health_grade"]
    grade_class = {"A": "good", "B": "good", "C": "warn",
                   "D": "bad", "F": "bad"}[grade]

    def table_rows(rows, columns):
        out = []
        for row in rows:
            cells = "".join(f"<td>{_esc(str(cell))}</td>" for cell in row)
            out.append(f"<tr>{cells}</tr>")
        return "\n".join(out)

    orphan_rows = table_rows(
        [(url, data["pages"].get(url, {}).get("title", "")) for url in data["orphan_pages"]],
        2)
    weak_rows = table_rows(
        [(url, data["pages"].get(url, {}).get("title", "")) for url in data.get("weakly_linked_pages", [])],
        2)
    broken_rows = table_rows(
        [(src, ", ".join(targets)) for src, targets in data["broken_links"].items()],
        2)
    suggestion_rows = table_rows(
        [(item["source_url"], item["target_url"], item["score"],
          item["anchor"], item["reason"]) for item in data["suggestions"]],
        5)
    authority_rows = table_rows(
        [(url, score) for url, score in
         sorted(data["authority"].items(), key=lambda item: -item[1])[:15]],
        2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Internal Link Report — {_esc(data['site'])}</title>
<style>
  body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #1f2937; }}
  h1 {{ font-size: 1.6rem; }} h2 {{ margin-top: 2rem; border-bottom: 2px solid #e5e7eb;
         padding-bottom: .3rem; }}
  .cards {{ display: flex; flex-wrap: wrap; gap: .75rem; margin: 1rem 0; }}
  .card {{ border: 1px solid #e5e7eb; border-radius: .5rem; padding: .75rem 1rem;
          min-width: 120px; background: #f9fafb; }}
  .card b {{ font-size: 1.5rem; display: block; }}
  .grade {{ font-size: 2.2rem; font-weight: 800; }}
  .good {{ color: #047857; }} .warn {{ color: #b45309; }} .bad {{ color: #b91c1c; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .9rem; }}
  th, td {{ border: 1px solid #e5e7eb; padding: .45rem .6rem; text-align: left;
            vertical-align: top; word-break: break-word; }}
  th {{ background: #f3f4f6; }}
  .muted {{ color: #6b7280; font-size: .85rem; }}
  code {{ background: #f3f4f6; padding: 0 .25rem; border-radius: .25rem; }}
</style>
</head>
<body>
<h1>Internal Link Report</h1>
<p class="muted">Site: <code>{_esc(data['site'])}</code> &nbsp;•&nbsp;
Generated: {_esc(data['generated_at'])} &nbsp;•&nbsp;
Source: {_esc(data['source'])}</p>
<p>Health score: <span class="grade {grade_class}">{summary['health_score']}/100
(grade {grade})</span></p>
<div class="cards">
  <div class="card"><b>{summary['pages_crawled']}</b>pages crawled</div>
  <div class="card"><b>{summary['content_links']}</b>content links</div>
  <div class="card"><b>{summary['avg_inbound_links']}</b>avg inbound / page</div>
  <div class="card"><b>{summary['orphan_pages']}</b>orphan pages</div>
  <div class="card"><b>{summary['weakly_linked_pages']}</b>weakly linked</div>
  <div class="card"><b>{summary['dead_end_pages']}</b>dead-end pages</div>
  <div class="card"><b>{summary['pages_with_broken_links']}</b>pages w/ broken links</div>
  <div class="card"><b>{summary['suggestions']}</b>suggestions</div>
</div>

<h2>Orphan pages ({summary['orphan_pages']})</h2>
<p class="muted">Live pages no other page links to — link to these first.</p>
{"<table><tr><th>URL</th><th>Title</th></tr>" + orphan_rows + "</table>" if orphan_rows else "<p>No orphan pages. 🎉</p>"}

<h2>Weakly linked pages ({summary['weakly_linked_pages']})</h2>
<p class="muted">Reachable only from the navigation or footer — no article links to them. Add a content link from a related page.</p>
{"<table><tr><th>URL</th><th>Title</th></tr>" + weak_rows + "</table>" if weak_rows else "<p>No weakly linked pages. 🎉</p>"}

<h2>Broken internal links ({summary['pages_with_broken_links']} pages)</h2>
{"<table><tr><th>Source page</th><th>Broken target(s)</th></tr>" + broken_rows + "</table>" if broken_rows else "<p>No broken internal links. 🎉</p>"}

<h2>Link suggestions ({summary['suggestions']})</h2>
<p class="muted">Add these links — anchor text is taken from real sentences on the source page.</p>
{"<table><tr><th>Source page</th><th>Link to</th><th>Score</th><th>Anchor text</th><th>Why</th></tr>" + suggestion_rows + "</table>" if suggestion_rows else "<p>No suggestions — the site is already well linked.</p>"}

<h2>Top pages by internal authority</h2>
<p class="muted">Where your link equity actually flows (internal PageRank).</p>
{"<table><tr><th>URL</th><th>Authority</th></tr>" + authority_rows + "</table>" if authority_rows else "<p>No pages.</p>"}

<p class="muted">Generated by <a href="https://github.com/hasnaat-anjum/internal-link-optimizer">Internal Link Optimizer</a> — free, open source, no API key needed.</p>
</body>
</html>
"""


def write_outputs(data: dict, out_prefix: str) -> dict[str, str]:
    """Write JSON, CSV and HTML reports next to *out_prefix*.
    Returns {format: path} for the files written."""
    paths: dict[str, str] = {}
    json_path = f"{out_prefix}.json"
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    paths["json"] = json_path
    suggestions = [
        Suggestion(item["source_url"], item["target_url"], item["score"],
                   item["anchor"], item["sentence"], item["reason"])
        for item in data["suggestions"]
    ]
    csv_path = f"{out_prefix}-suggestions.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(suggestions_csv(suggestions))
    paths["csv"] = csv_path
    html_path = f"{out_prefix}.html"
    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write(html_report(data))
    paths["html"] = html_path
    return paths
