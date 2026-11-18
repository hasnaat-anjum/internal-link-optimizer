"""Tests for link suggestions: ranking, anchors, and the honesty rules."""

import unittest

from linkoptimizer.parser import Link, PageData
from linkoptimizer.suggest import _find_anchor, suggest_links


def rich_page(url, title, text, targets=()):
    links = [Link(href=t, url=t, anchor="link", in_content=True)
             for t in targets]
    words = text.split()
    return PageData(url=url, title=title, text=text,
                    sentences=[text], word_count=len(words) * 8, links=links)


class TestSuggestions(unittest.TestCase):
    def setUp(self):
        self.pages = {
            "https://x/coffee": rich_page(
                "https://x/coffee", "Coffee Beans Guide",
                "Fresh coffee beans make the best coffee. Our guide covers "
                "roast levels, origins and storage for coffee beans."),
            "https://x/brewing": rich_page(
                "https://x/brewing", "Brewing Coffee at Home",
                "Brewing coffee at home starts with fresh coffee beans. "
                "Grind your coffee beans just before brewing for best flavour."),
            "https://x/shoes": rich_page(
                "https://x/shoes", "Running Shoes",
                "Running shoes for marathon training with lightweight "
                "cushioning and durable soles for long distance runners."),
        }

    def test_related_pages_suggested_unrelated_not(self):
        suggestions = suggest_links(self.pages, {}, set())
        pairs = {(s.source_url, s.target_url) for s in suggestions}
        self.assertIn(("https://x/coffee", "https://x/brewing"), pairs)
        self.assertNotIn(("https://x/coffee", "https://x/shoes"), pairs)

    def test_existing_links_never_suggested(self):
        pages = dict(self.pages)
        pages["https://x/coffee"] = rich_page(
            "https://x/coffee", "Coffee Beans Guide",
            "Fresh coffee beans make the best coffee.",
            targets=("https://x/brewing",))
        suggestions = suggest_links(pages, {}, set())
        pairs = {(s.source_url, s.target_url) for s in suggestions}
        self.assertNotIn(("https://x/coffee", "https://x/brewing"), pairs)

    def test_no_self_links(self):
        suggestions = suggest_links(self.pages, {}, set())
        for item in suggestions:
            self.assertNotEqual(item.source_url, item.target_url)

    def test_orphan_boost_and_reason(self):
        suggestions = suggest_links(self.pages, {},
                                    orphan_pages={"https://x/brewing"})
        brewing = [s for s in suggestions
                   if s.target_url == "https://x/brewing"]
        self.assertTrue(brewing)
        self.assertIn("Orphan", brewing[0].reason)

    def test_anchor_comes_from_real_sentence(self):
        suggestions = suggest_links(self.pages, {}, set())
        coffee_to_brewing = [s for s in suggestions
                             if s.source_url == "https://x/coffee"
                             and s.target_url == "https://x/brewing"]
        self.assertTrue(coffee_to_brewing)
        item = coffee_to_brewing[0]
        self.assertIn(item.anchor.lower(), item.sentence.lower())
        self.assertTrue(item.sentence)  # a real sentence is attached

    def test_max_three_per_page(self):
        pages = dict(self.pages)
        for i in range(6):
            pages[f"https://x/extra{i}"] = rich_page(
                f"https://x/extra{i}", "More Coffee Beans",
                "Fresh coffee beans roasted weekly for brewing coffee at home.")
        suggestions = suggest_links(pages, {}, set())
        from collections import Counter
        per_source = Counter(s.source_url for s in suggestions)
        self.assertTrue(all(count <= 3 for count in per_source.values()))

    def test_thin_pages_never_suggested_as_targets(self):
        pages = dict(self.pages)
        pages["https://x/thin"] = PageData(
            url="https://x/thin", title="Coffee Beans Thin",
            text="coffee beans coffee", word_count=3)
        suggestions = suggest_links(pages, {}, set())
        self.assertFalse(any(s.target_url == "https://x/thin"
                             for s in suggestions))


class TestFindAnchor(unittest.TestCase):
    def test_fallback_uses_target_title(self):
        source = PageData(url="https://x/a", title="A", text="unrelated words",
                          sentences=["Something completely different here."])
        anchor, sentence = _find_anchor(source, [("coffee", 2.0)], "Coffee Beans Guide")
        self.assertEqual(anchor, "Coffee Beans Guide")
        self.assertEqual(sentence, "")


if __name__ == "__main__":
    unittest.main()
