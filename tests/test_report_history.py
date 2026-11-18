"""Tests for reports (JSON/CSV/HTML) and snapshot history."""

import json
import os
import tempfile
import unittest

from linkoptimizer.graph import GraphStats
from linkoptimizer.history import (compare_snapshots, load_snapshot,
                                   save_snapshot)
from linkoptimizer.parser import PageData
from linkoptimizer.report import (html_report, result_dict, suggestions_csv,
                                  terminal_summary, write_outputs)
from linkoptimizer.suggest import Suggestion


def sample_data():
    pages = {
        "https://x/": PageData(url="https://x/", title="Home",
                               word_count=50, status=200),
        "https://x/a": PageData(url="https://x/a", title="Page A",
                                word_count=80, status=200),
    }
    stats = GraphStats(total_pages=2, total_content_links=1, avg_inbound=0.5,
                       orphan_pages=["https://x/a"], health_score=70,
                       authority={"https://x/": 0.6, "https://x/a": 0.4})
    suggestions = [Suggestion("https://x/", "https://x/a", 0.85,
                              "coffee beans", "Fresh coffee beans here.",
                              "Closely related.")]
    return result_dict("https://x/", pages, stats, suggestions)


class TestReports(unittest.TestCase):
    def test_result_dict_shape(self):
        data = sample_data()
        self.assertEqual(data["summary"]["health_score"], 70)
        self.assertEqual(data["summary"]["health_grade"], "C")
        self.assertEqual(len(data["suggestions"]), 1)

    def test_terminal_summary_mentions_key_facts(self):
        text = terminal_summary(sample_data())
        self.assertIn("70/100", text)
        self.assertIn("https://x/a", text)

    def test_csv_has_header_and_row(self):
        text = suggestions_csv([Suggestion("https://x/", "https://x/a", 0.85,
                                          "coffee beans", "Fresh coffee.",
                                          "Related.")])
        lines = text.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("source_url,target_url"))

    def test_html_report_escapes_and_contains_tables(self):
        text = html_report(sample_data())
        self.assertIn("Health score", text)
        self.assertIn("https://x/a", text)
        self.assertIn("coffee beans", text)

    def test_write_outputs_creates_three_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = os.path.join(tmp, "report")
            paths = write_outputs(sample_data(), prefix)
            self.assertEqual(set(paths), {"json", "csv", "html"})
            for path in paths.values():
                self.assertTrue(os.path.exists(path))
            with open(paths["json"], encoding="utf-8") as handle:
                loaded = json.load(handle)
            self.assertEqual(loaded["summary"]["health_score"], 70)


class TestHistory(unittest.TestCase):
    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "snap.json")
            save_snapshot(sample_data(), path)
            self.assertEqual(load_snapshot(path)["site"], "https://x/")

    def test_compare_detects_fixed_orphan(self):
        old = sample_data()
        new = sample_data()
        new["orphan_pages"] = []
        new["summary"] = dict(old["summary"])
        new["summary"]["orphan_pages"] = 0
        new["summary"]["health_score"] = 92
        diff = compare_snapshots(old, new)
        self.assertEqual(diff["orphans_fixed"], ["https://x/a"])
        self.assertEqual(diff["health_score"]["change"], 22)


if __name__ == "__main__":
    unittest.main()
