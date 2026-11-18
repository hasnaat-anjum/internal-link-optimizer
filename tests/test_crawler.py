"""Tests for the crawler (local folder + live HTTP server) and sitemaps."""

import os
import threading
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from linkoptimizer.crawler import (crawl_local_folder, crawl_site,
                                   parse_sitemap)

DEMO_SITE = os.path.join(os.path.dirname(__file__), "..", "examples", "demo-site")


class TestLocalFolderCrawl(unittest.TestCase):
    def setUp(self):
        self.result = crawl_local_folder(DEMO_SITE)

    def test_all_demo_pages_found(self):
        self.assertEqual(len(self.result.pages), 6)

    def test_orphan_wholesale_page_detected(self):
        # Wholesale is in the folder but no page links to it at all
        # (it is not even in the navigation): it must appear as an
        # orphan in the analysis, not vanish.
        from linkoptimizer.graph import analyse
        stats = analyse(self.result.pages, self.result.broken)
        self.assertEqual(stats.orphan_pages, ["http://local/wholesale.html"])

    def test_weakly_linked_about_page(self):
        # About is in the navigation but no article ever links to it.
        from linkoptimizer.graph import analyse
        stats = analyse(self.result.pages, self.result.broken)
        self.assertIn("http://local/about.html", stats.weakly_linked_pages)
        self.assertNotIn("http://local/about.html", stats.orphan_pages)

    def test_dead_end_about_page(self):
        from linkoptimizer.graph import analyse
        stats = analyse(self.result.pages, self.result.broken)
        self.assertIn("http://local/about.html", stats.dead_end_pages)

    def test_broken_link_to_missing_page(self):
        self.assertIn("http://local/missing-page.html", self.result.broken)
        from linkoptimizer.graph import analyse
        stats = analyse(self.result.pages, self.result.broken)
        self.assertIn("http://local/subscriptions.html", stats.broken_links)

    def test_suggestions_link_related_demo_pages(self):
        from linkoptimizer.graph import analyse
        from linkoptimizer.suggest import suggest_links
        stats = analyse(self.result.pages, self.result.broken)
        suggestions = suggest_links(self.result.pages, stats.authority,
                                    set(stats.orphan_pages))
        self.assertTrue(suggestions)
        pairs = {(s.source_url, s.target_url) for s in suggestions}
        # Home mentions brewing + subscriptions in text but never links them.
        self.assertTrue(("http://local/", "http://local/brewing-guide.html") in pairs
                        or ("http://local/", "http://local/subscriptions.html") in pairs)
        # The orphan wholesale page should be suggested as a target.
        self.assertTrue(any(s.target_url == "http://local/wholesale.html"
                            for s in suggestions))


class TestSitemapParsing(unittest.TestCase):
    def test_sitemap_and_index(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://example.com/a</loc></url>
          <url><loc>https://example.com/b</loc></url>
        </urlset>"""
        self.assertEqual(parse_sitemap(xml),
                         ["https://example.com/a", "https://example.com/b"])

    def test_bad_xml_returns_empty(self):
        self.assertEqual(parse_sitemap("not xml at all"), [])


class TestLiveCrawl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = partial(SimpleHTTPRequestHandler,
                          directory=os.path.abspath(DEMO_SITE))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_crawl_over_http(self):
        result = crawl_site(f"http://127.0.0.1:{self.port}/",
                            max_pages=10, delay=0)
        # Link-following from the home page reaches the 5 nav-linked pages;
        # the orphan wholesale page is unreachable without a sitemap, which
        # is exactly why sitemap/local modes exist.
        self.assertEqual(len(result.pages), 5)
        self.assertNotIn(f"http://127.0.0.1:{self.port}/wholesale.html",
                         result.pages)

    def test_crawl_honours_max_pages(self):
        result = crawl_site(f"http://127.0.0.1:{self.port}/",
                            max_pages=2, delay=0)
        self.assertEqual(len(result.pages), 2)


if __name__ == "__main__":
    unittest.main()
