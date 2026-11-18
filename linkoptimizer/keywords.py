"""Keyword extraction: what is each page *about*?

A small TF-IDF implementation over the crawled pages (stdlib only). For
every page we keep its top keywords — the words that appear often on that
page but rarely elsewhere on the site. Two pages whose top keywords
overlap are topically related, which is exactly what a good internal link
needs: a reader on page A who would benefit from page B.

Cosine similarity over the TF-IDF vectors gives the relevance score used
by the suggestion engine.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from .parser import PageData

# Common words that carry no topical meaning. Kept deliberately short —
# the list covers the usual English stopwords plus web boilerplate.
STOPWORDS = frozenset("""
a an the and or but if then else for of to in on at by with from as is are was were
be been being have has had do does did will would shall should can could may might
must i you he she it we they me him her us them my your his its our their this that
these those there here what which who whom when where why how all any both each few
more most other some such no nor not only own same so than too very just also into
over under again further once about between through during before after above below
up down out off again once here there when where why how all any both each few more
most other some such no nor not only own same so than too very s t can will just don
should now home page click read more learn get use used using new best top free
""".split())

WORD_RE = re.compile(r"[a-z][a-z\-']{2,}")
# A hyphenated word counts as one term; keep the parts too ("on-page" →
# "on-page" and "page") so matching is forgiving.


def tokenise(text: str) -> list[str]:
    """Lowercase words of 3+ letters, minus stopwords."""
    tokens = []
    for match in WORD_RE.finditer(text.lower()):
        word = match.group(0)
        if word in STOPWORDS:
            continue
        tokens.append(word)
        if "-" in word:  # "on-page" also yields "page"
            for part in word.split("-"):
                if len(part) >= 3 and part not in STOPWORDS:
                    tokens.append(part)
    return tokens


def page_keywords(page: PageData, top_n: int = 12) -> list[tuple[str, float]]:
    """Top keywords of one page by raw frequency, title/H1 words boosted.
    Returns [(keyword, weight), ...] sorted by weight, highest first."""
    title_boost = Counter(tokenise(f"{page.title} {page.h1}"))
    body = Counter(tokenise(page.text))
    scores: dict[str, float] = {}
    for word, count in body.items():
        scores[word] = count
    for word, count in title_boost.items():
        scores[word] = scores.get(word, 0) + count * 3.0
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return ranked[:top_n]


def build_tfidf(pages: dict[str, PageData]) -> dict[str, dict[str, float]]:
    """TF-IDF vectors for every page: {url: {term: weight}}.

    IDF already downweights site-wide words (a term on every page gets
    the lowest weight), so no hard cut-off is applied — on a small site
    the shared vocabulary *is* the topical glue, and dropping it would
    make genuinely related pages look unrelated.
    """
    docs = {url: Counter(tokenise(page.text)) for url, page in pages.items()}
    total = len(docs)
    if total == 0:
        return {}
    doc_freq: Counter = Counter()
    for terms in docs.values():
        for term in terms:
            doc_freq[term] += 1
    vectors: dict[str, dict[str, float]] = {}
    for url, terms in docs.items():
        total_terms = sum(terms.values()) or 1
        vector: dict[str, float] = {}
        for term, count in terms.items():
            tf = count / total_terms
            idf = math.log((total + 1) / (doc_freq[term] + 1)) + 1.0
            vector[term] = tf * idf
        vectors[url] = vector
    return vectors


def cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Cosine similarity between two sparse TF-IDF vectors (0–1)."""
    if not vec_a or not vec_b:
        return 0.0
    shared = set(vec_a) & set(vec_b)
    dot = sum(vec_a[term] * vec_b[term] for term in shared)
    norm_a = math.sqrt(sum(value * value for value in vec_a.values()))
    norm_b = math.sqrt(sum(value * value for value in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
