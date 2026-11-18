"""Link-graph analysis: who links to whom, and who is left out.

Builds the site's internal link graph from the crawled pages and answers
the questions that matter for SEO:

* **Orphan pages** — live pages no other page links to at all, not
  even from the navigation. Google (and readers) can barely find them;
  they collect almost no link equity.
* **Weakly linked pages** — reachable only from navigation or footer.
  Findable, but no article ever vouches for them topically; they are the
  next-best candidates for a content link.
* **Dead-end pages** — pages with no outgoing content links; they trap
  readers and pass no equity onwards.
* **Broken internal links** — links pointing at pages that returned an
  error or do not exist.
* **Internal PageRank** — a simple iterative authority score (damping
  0.85) showing how link equity actually flows. Pages with high value
  but low authority are the ones to link *to* first.
* **Health score (0–100)** — one number summarising the whole site.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from .parser import PageData


@dataclass
class GraphStats:
    """Summary numbers for one crawl."""

    total_pages: int = 0
    total_content_links: int = 0
    orphan_pages: list[str] = field(default_factory=list)
    weakly_linked_pages: list[str] = field(default_factory=list)
    dead_end_pages: list[str] = field(default_factory=list)
    broken_links: dict[str, list[str]] = field(default_factory=dict)
    avg_inbound: float = 0.0
    health_score: int = 0
    authority: dict[str, float] = field(default_factory=dict)  # url -> PageRank


def build_graph(pages: dict[str, PageData]) -> dict[str, set[str]]:
    """Adjacency map {source_url: {target_url}} using content links only,
    restricted to pages that were actually crawled."""
    graph: dict[str, set[str]] = {}
    for url, page in pages.items():
        targets = {target for target in page.internal_link_targets if target in pages}
        graph[url] = targets
    return graph


def build_full_graph(pages: dict[str, PageData]) -> dict[str, set[str]]:
    """Adjacency map using *all* internal links, including navigation
    and footer links. Used for orphan detection: a page linked only from
    the menu is not an orphan — it is just weakly linked."""
    graph: dict[str, set[str]] = {}
    for url, page in pages.items():
        targets = {link.url for link in page.links
                   if link.url in pages}
        graph[url] = targets
    return graph


def inbound_counts(graph: dict[str, set[str]]) -> dict[str, int]:
    """How many crawled pages link to each page (content links only)."""
    counts = {url: 0 for url in graph}
    for targets in graph.values():
        for target in targets:
            counts[target] = counts.get(target, 0) + 1
    return counts


def compute_pagerank(graph: dict[str, set[str]], damping: float = 0.85,
                     iterations: int = 30) -> dict[str, float]:
    """Classic PageRank over the internal link graph. Dangling pages
    (no outbound links) distribute their rank evenly, as in the original
    algorithm. Scores sum to 1.0."""
    nodes = list(graph)
    total = len(nodes)
    if total == 0:
        return {}
    rank = {node: 1.0 / total for node in nodes}
    for _ in range(iterations):
        new_rank = {node: (1.0 - damping) / total for node in nodes}
        dangling_sum = sum(rank[node] for node in nodes if not graph[node])
        for node in nodes:
            new_rank[node] += damping * dangling_sum / total
            for target in graph[node]:
                new_rank[target] += damping * rank[node] / len(graph[node])
        rank = new_rank
    return rank


def find_broken_links(pages: dict[str, PageData],
                      broken_status: dict[str, int]) -> dict[str, list[str]]:
    """Map each source page to the internal links on it that are broken
    (target was fetched and returned an error, or — in local-folder mode —
    the target file does not exist). A link to a page the crawler simply
    never reached (page cap) is *not* called broken: it was never checked.
    """
    broken: dict[str, list[str]] = {}
    for url, page in pages.items():
        bad = sorted({link.url for link in page.content_links
                      if link.url in broken_status})
        if bad:
            broken[url] = bad
    return broken


def analyse(pages: dict[str, PageData],
            broken_status: dict[str, int]) -> GraphStats:
    """Full graph analysis for one crawl."""
    stats = GraphStats(total_pages=len(pages))
    if not pages:
        return stats
    graph = build_graph(pages)
    inbound = inbound_counts(graph)
    stats.total_content_links = sum(len(targets) for targets in graph.values())
    stats.avg_inbound = stats.total_content_links / len(pages)
    stats.authority = compute_pagerank(graph)

    # The home page is the crawl root: it is linked from everywhere by
    # definition, so it can never be an orphan or weakly linked. Skip it.
    home = min(pages, key=lambda url: (len(urlparse(url).path), url))
    inbound_any = inbound_counts(build_full_graph(pages))
    stats.orphan_pages = sorted(
        url for url, count in inbound_any.items()
        if count == 0 and url != home
    )
    # Reachable only from navigation / footer: Google and readers can
    # find the page, but no article ever vouches for it topically.
    stats.weakly_linked_pages = sorted(
        url for url in pages
        if url != home and inbound.get(url, 0) == 0
        and inbound_any.get(url, 0) > 0
    )
    stats.dead_end_pages = sorted(
        url for url, targets in graph.items() if not targets and url != home
    )
    stats.broken_links = find_broken_links(pages, broken_status)
    stats.health_score = health_score(stats)
    return stats


def health_score(stats: GraphStats) -> int:
    """0–100 health score. Orphans and broken links cost the most,
    because they are the issues that actually lose traffic."""
    if stats.total_pages == 0:
        return 0
    score = 100.0
    orphan_rate = len(stats.orphan_pages) / stats.total_pages
    score -= min(40.0, orphan_rate * 200)          # up to -40
    weak_rate = len(stats.weakly_linked_pages) / stats.total_pages
    score -= min(10.0, weak_rate * 40)             # up to -10
    broken_pages = len(stats.broken_links)
    score -= min(30.0, broken_pages * 6)           # up to -30
    dead_rate = len(stats.dead_end_pages) / stats.total_pages
    score -= min(15.0, dead_rate * 60)             # up to -15
    if stats.avg_inbound < 1.0:                    # thinly linked site
        score -= 10.0
    elif stats.avg_inbound < 2.0:
        score -= 5.0
    return max(0, min(100, round(score)))


def health_grade(score: int) -> str:
    """Letter grade for a health score."""
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"
