"""Internal Link Optimizer — find the internal links your site is missing.

A free, offline-first SEO tool: crawl any website (or a folder of HTML
files), map its internal link graph, find orphan and broken pages, and get
ranked internal-link suggestions with real anchor text taken from your own
content. No API key, no account, no paid plan — everything runs locally.

Typical use::

    python -m linkoptimizer audit https://example.com --max-pages 200
    python -m linkoptimizer audit --local ./my-site --out report.html
    python -m linkoptimizer compare runs/2026-11-18.json runs/2026-11-25.json
"""

__version__ = "1.0.0"
__author__ = "Hasnaat Anjum"
