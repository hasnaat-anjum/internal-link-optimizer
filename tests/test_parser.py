"""Tests for HTML parsing: titles, links, content vs boilerplate."""

import unittest

from linkoptimizer.parser import (is_same_site, normalise_url, parse_html,
                                  split_sentences)

SAMPLE = """<!DOCTYPE html><html><head><title>  Pour Over Guide </title>
<meta name="description" content="Brew better coffee."></head><body>
<header><nav><a href="/beans.html">Beans</a></nav></header>
<main>
<h1>Pour Over Guide</h1>
<p>Good coffee starts with fresh beans. Use a medium grind for pour over.</p>
<p><a href="/beans.html" rel="nofollow">Browse our beans</a> and start brewing.</p>
<p><a href="https://other-site.com/page">External link</a></p>
<p><a href="#top">Jump link</a></p>
</main>
<footer><a href="/privacy.html">Privacy</a></footer>
</body></html>"""


class TestParseHtml(unittest.TestCase):
    def setUp(self):
        self.page = parse_html(SAMPLE, "https://example.com/guide.html")

    def test_title_and_h1_and_description(self):
        self.assertEqual(self.page.title, "Pour Over Guide")
        self.assertEqual(self.page.h1, "Pour Over Guide")
        self.assertEqual(self.page.description, "Brew better coffee.")

    def test_nav_link_is_boilerplate_not_content(self):
        nav_links = [link for link in self.page.links
                     if link.url == "https://example.com/beans.html"]
        self.assertEqual(len(nav_links), 2)  # nav + content copies
        self.assertFalse(nav_links[0].in_content)   # nav copy
        self.assertTrue(nav_links[1].in_content)    # content copy
        self.assertTrue(nav_links[1].nofollow)
        self.assertEqual(nav_links[1].anchor, "Browse our beans")

    def test_content_links_exclude_nav_footer_and_fragments(self):
        urls = {link.url for link in self.page.content_links}
        self.assertIn("https://example.com/beans.html", urls)
        self.assertIn("https://other-site.com/page", urls)
        self.assertNotIn("https://example.com/privacy.html", urls)
        self.assertNotIn("https://example.com/guide.html#top", urls)

    def test_word_count_and_sentences(self):
        self.assertGreater(self.page.word_count, 15)
        self.assertTrue(any("fresh beans" in s for s in self.page.sentences))

    def test_relative_url_resolution(self):
        page = parse_html('<a href="sub/page.html">x</a>',
                          "https://example.com/dir/index.html")
        self.assertEqual(page.links[0].url,
                         "https://example.com/dir/sub/page.html")


class TestNormaliseUrl(unittest.TestCase):
    def test_drops_fragment(self):
        self.assertEqual(normalise_url("https://Example.com/Page#section"),
                         "https://example.com/Page")

    def test_same_site(self):
        self.assertTrue(is_same_site("https://example.com/a",
                                     "https://example.com/b"))
        self.assertFalse(is_same_site("https://other.com/a",
                                      "https://example.com/b"))


class TestSplitSentences(unittest.TestCase):
    def test_basic_split(self):
        result = split_sentences("First sentence here. Second one follows! Short.")
        self.assertEqual(len(result), 2)  # "Short." is too short to keep
        self.assertTrue(result[0].startswith("First sentence"))

    def test_empty(self):
        self.assertEqual(split_sentences("   "), [])


if __name__ == "__main__":
    unittest.main()
