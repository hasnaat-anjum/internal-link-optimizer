"""Tests for keyword extraction and TF-IDF similarity."""

import unittest

from linkoptimizer.keywords import (build_tfidf, cosine_similarity,
                                    page_keywords, tokenise)
from linkoptimizer.parser import PageData


def make_page(url, title, text):
    return PageData(url=url, title=title, text=text,
                    word_count=len(text.split()))


class TestTokenise(unittest.TestCase):
    def test_stopwords_removed_and_lowercased(self):
        tokens = tokenise("The Quick Brown Fox jumps over the lazy dog")
        self.assertIn("quick", tokens)
        self.assertIn("brown", tokens)
        self.assertNotIn("the", tokens)
        self.assertNotIn("over", tokens)

    def test_hyphenated_words_split_too(self):
        tokens = tokenise("single-origin coffee for cold-brew fans")
        self.assertIn("single-origin", tokens)
        self.assertIn("single", tokens)
        self.assertIn("origin", tokens)
        self.assertIn("cold-brew", tokens)
        self.assertIn("brew", tokens)


class TestPageKeywords(unittest.TestCase):
    def test_title_words_boosted(self):
        page = make_page("https://x/a", "Cold Brew Coffee",
                         "cold brew coffee is smooth. cold brew takes time.")
        top = [word for word, _ in page_keywords(page, top_n=3)]
        self.assertIn("cold", top)
        self.assertIn("brew", top)


class TestTfidf(unittest.TestCase):
    def setUp(self):
        self.pages = {
            "https://x/coffee": make_page(
                "https://x/coffee", "Coffee Beans",
                "coffee beans roasted fresh every week coffee beans arabica"),
            "https://x/brewing": make_page(
                "https://x/brewing", "Brewing Coffee",
                "brewing coffee at home with fresh coffee beans and hot water"),
            "https://x/shoes": make_page(
                "https://x/shoes", "Running Shoes",
                "running shoes for marathon training lightweight running shoes"),
        }
        self.vectors = build_tfidf(self.pages)

    def test_related_pages_more_similar_than_unrelated(self):
        sim_related = cosine_similarity(self.vectors["https://x/coffee"],
                                        self.vectors["https://x/brewing"])
        sim_unrelated = cosine_similarity(self.vectors["https://x/coffee"],
                                          self.vectors["https://x/shoes"])
        self.assertGreater(sim_related, sim_unrelated)
        self.assertGreater(sim_related, 0.1)

    def test_self_similarity_is_one(self):
        self.assertAlmostEqual(
            cosine_similarity(self.vectors["https://x/coffee"],
                              self.vectors["https://x/coffee"]), 1.0, places=5)

    def test_empty_vector_similarity_is_zero(self):
        self.assertEqual(cosine_similarity({}, {"a": 1.0}), 0.0)


if __name__ == "__main__":
    unittest.main()
