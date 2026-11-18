"""Tests for the link graph: PageRank, orphans, dead ends, health."""

import unittest

from linkoptimizer.graph import (analyse, build_graph, compute_pagerank,
                                 health_grade, inbound_counts)
from linkoptimizer.parser import Link, PageData


def page(url, targets):
    """A page whose content links point at *targets*."""
    links = [Link(href=t, url=t, anchor="link", in_content=True)
             for t in targets]
    return PageData(url=url, title=url, text="some words here " * 20,
                    word_count=60, links=links)


class TestGraph(unittest.TestCase):
    def setUp(self):
        # home -> a, b ; a -> b ; b -> (nothing) ; c -> a (orphan c itself)
        self.pages = {
            "https://x/": page("https://x/", ["https://x/a", "https://x/b"]),
            "https://x/a": page("https://x/a", ["https://x/b"]),
            "https://x/b": page("https://x/b", []),
            "https://x/c": page("https://x/c", ["https://x/a"]),
        }

    def test_inbound_counts(self):
        counts = inbound_counts(build_graph(self.pages))
        self.assertEqual(counts["https://x/b"], 2)
        self.assertEqual(counts["https://x/c"], 0)

    def test_orphan_detection(self):
        stats = analyse(self.pages, {})
        self.assertIn("https://x/c", stats.orphan_pages)
        self.assertNotIn("https://x/", stats.orphan_pages)  # home is exempt
        self.assertNotIn("https://x/a", stats.orphan_pages)

    def test_weakly_linked_page_is_not_an_orphan(self):
        # Page d is linked only from a navigation menu (boilerplate link):
        # findable, but with no content link vouching for it.
        pages = dict(self.pages)
        nav_link = Link(href="/d", url="https://x/d", anchor="D",
                        in_content=False)
        home = PageData(url="https://x/", title="home",
                        text="some words here " * 20, word_count=60,
                        links=[Link(href="/a", url="https://x/a", anchor="a",
                                    in_content=True),
                               Link(href="/b", url="https://x/b", anchor="b",
                                    in_content=True),
                               nav_link])
        pages["https://x/"] = home
        pages["https://x/d"] = PageData(url="https://x/d", title="d",
                                        text="some words here " * 20,
                                        word_count=60)
        stats = analyse(pages, {})
        self.assertNotIn("https://x/d", stats.orphan_pages)
        self.assertIn("https://x/d", stats.weakly_linked_pages)

    def test_dead_end_detection(self):
        stats = analyse(self.pages, {})
        self.assertIn("https://x/b", stats.dead_end_pages)

    def test_pagerank_sums_to_one(self):
        rank = compute_pagerank(build_graph(self.pages))
        self.assertAlmostEqual(sum(rank.values()), 1.0, places=5)
        # b has the most inbound links, so it should hold the most rank.
        self.assertGreater(rank["https://x/b"], rank["https://x/c"])

    def test_broken_links_found(self):
        pages = dict(self.pages)
        pages["https://x/a"] = page(
            "https://x/a", ["https://x/b", "https://x/gone"])
        stats = analyse(pages, {"https://x/gone": 404})
        self.assertIn("https://x/a", stats.broken_links)
        self.assertIn("https://x/gone", stats.broken_links["https://x/a"])

    def test_health_score_and_grade(self):
        stats = analyse(self.pages, {})
        self.assertGreaterEqual(stats.health_score, 0)
        self.assertLessEqual(stats.health_score, 100)
        self.assertEqual(health_grade(95), "A")
        self.assertEqual(health_grade(80), "B")
        self.assertEqual(health_grade(65), "C")
        self.assertEqual(health_grade(45), "D")
        self.assertEqual(health_grade(10), "F")
        # A perfect tiny site scores high.
        perfect = {"https://x/": page("https://x/", ["https://x/a"]),
                   "https://x/a": page("https://x/a", ["https://x/"])}
        self.assertGreaterEqual(analyse(perfect, {}).health_score, 90)

    def test_empty_site_scores_zero(self):
        self.assertEqual(analyse({}, {}).health_score, 0)


if __name__ == "__main__":
    unittest.main()
