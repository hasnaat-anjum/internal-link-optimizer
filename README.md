# Internal Link Optimizer

**Find the internal links your site is missing — free, open source, no API key, no account.**

Internal links are one of the highest-leverage, most-neglected parts of on-page SEO: they spread link equity, rescue orphan pages, and help readers (and Google) discover related content. The tools that do this well — Ahrefs' Link Opportunities, Link Whisper, Screaming Frog — are paid, desktop-only, or locked to WordPress. This tool does the same job for **any website**, from your own machine, with zero dependencies beyond Python itself.

## The gap it fills

- **SEOs and bloggers** search constantly for a free internal-link audit that works on any site — most free options only check one page, only work inside WordPress, or hide the suggestions behind a paywall.
- **Small business owners** have sites with dozens of pages and no idea which ones are orphans (live pages nothing links to) or which related pages never link to each other.
- Existing open-source crawlers find broken links but don't *suggest* new ones with anchor text. This one does both.

## What it does

- **Crawls your site** from a start URL (same-domain, polite: honours `robots.txt`, configurable delay and page cap), **or seeds from a `sitemap.xml`**, **or analyses a local folder of HTML files** (a static-site build — works fully offline).
- **Builds your internal link graph** — content links only (menu/footer links don't count: a link in your navigation tells Google nothing about topical relevance).
- **Finds orphan pages** (no page links to them at all), **weakly linked pages** (reachable only from navigation or footer — no article ever vouches for them), **dead-end pages** (no outgoing content links) and **broken internal links**.
- **Scores your site's internal-link health 0–100** (grade A–F) and computes **internal PageRank** so you can see where link equity actually flows.
- **Suggests the links to add**, ranked by topical similarity (TF-IDF): each suggestion names the page to edit, the page to link to, a **real anchor phrase taken from a sentence on the source page** (never invented text), the sentence it fits in, and a plain-English reason. Orphan pages are boosted to the top of the list.
- **Reports** in the terminal, **JSON**, **CSV** (one row per suggestion — paste it straight into a task list) and a **self-contained HTML report** you can share with a client.
- **Tracks progress**: save a snapshot per run and `compare` two runs to see orphans fixed, broken links resolved and health-score movement.

## Who it helps

Freelancers and SEO consultants auditing client sites, bloggers and content teams with large archives, small business owners who want their service pages to actually get found, and anyone who has ever wondered "which of my pages is nobody linking to?"

## Quick start

Requires Python 3.9+ — no third-party packages.

```bash
# Audit a live site (200 pages max by default)
python -m linkoptimizer audit https://example.com

# Audit from a sitemap — the best way to catch orphans, which a
# link-following crawl can never discover on its own
python -m linkoptimizer audit --sitemap https://example.com/sitemap.xml https://example.com

# Audit a local folder of HTML files (offline, e.g. a Hugo/Jekyll build)
python -m linkoptimizer audit --local ./my-site

# Save reports + a dated snapshot you can compare against later
python -m linkoptimizer audit https://example.com --out audit --save-snapshot

# Compare two runs and see what improved
python -m linkoptimizer compare runs/example-com-2026-11-18.json runs/example-com-2026-11-25.json

# List saved snapshots
python -m linkoptimizer history
```

Options: `--max-pages N` (default 200), `--delay SECONDS` (default 0.2), `--no-robots`, `--out PREFIX` (default `link-report`), `--quiet`.

## Example output

```
Internal Link Optimizer — https://example.com
Health score: 62/100 (grade C)
Pages crawled: 48  •  Content links: 61  •  Avg inbound links per page: 1.3
Orphan pages: 6  •  Weakly linked: 4  •  Dead-end pages: 9  •  Pages with broken links: 2
Link suggestions: 74
Orphans (fix these first):
  - https://example.com/wholesale-coffee
Top suggestions:
  - https://example.com/  →  https://example.com/brewing-guide (score 0.91, anchor: "brewing guide")
```

## Try it on the demo site

The `examples/demo-site/` folder is a tiny six-page coffee-roaster site with deliberate problems: an orphan page, a dead-end page, a broken link, and related pages that never link to each other. Run it offline:

```bash
python -m linkoptimizer audit --local examples/demo-site --out examples/demo-report
```

Expected result: 6 pages, health score 29/100 (grade F — the demo site is deliberately broken), 1 orphan (`wholesale.html`), 1 weakly linked page (`about.html`, reachable only from the menu), 2 dead-end pages, 1 broken link (`missing-page.html`), and 15 ranked suggestions — including links from the home page to the brewing guide it mentions but never links to. The generated `examples/demo-report.html` shows the full report.

## How suggestions are ranked

1. Every page is turned into a TF-IDF vector from its own text (title and H1 words count triple).
2. Page pairs are scored by cosine similarity — pages about the same things score high.
3. Pairs already linked are skipped, thin pages (< 40 words) are never suggested as targets, and at most 3 suggestions are kept per source page.
4. Orphan targets get a 50% boost, because they need links most.
5. Anchor text comes from a real sentence on the source page that mentions the target's keywords — if no sentence matches, the target's own title is used instead.

## Project structure

```
internal-link-optimizer/
├── linkoptimizer/
│   ├── __init__.py      # package info
│   ├── __main__.py      # python -m linkoptimizer entry point
│   ├── cli.py           # audit / compare / history commands
│   ├── crawler.py       # polite site crawler, sitemap reader, local-folder mode
│   ├── parser.py        # HTML → title, text, links (content vs boilerplate)
│   ├── keywords.py      # tokenising + TF-IDF similarity
│   ├── graph.py         # link graph, PageRank, orphans, health score
│   ├── suggest.py       # ranked suggestions with real anchor text
│   ├── report.py        # terminal / JSON / CSV / HTML reports
│   └── history.py       # snapshots + run comparison
├── tests/               # 48 unit + integration tests (unittest)
└── examples/
    ├── demo-site/       # six-page demo site with deliberate SEO issues
    ├── demo-report.html # generated report for the demo site
    └── demo-report-suggestions.csv
```

## Tests

```bash
python -m unittest discover -s tests -v
```

## Notes & limits

- A pure link-following crawl can only find pages that are already reachable. True orphans are only found via `--sitemap` or `--local` — use one of those for a complete audit.
- Pages rendered by JavaScript are not executed (the crawler reads the HTML the server sends). For JS-heavy sites, audit a static export with `--local`.
- Be polite: the default 0.2 s delay and 200-page cap keep small sites happy; raise the delay for shared hosting.
- Scores are local heuristics, not Google scores.

## License

MIT — see [LICENSE](LICENSE).
