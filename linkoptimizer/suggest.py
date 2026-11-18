"""Link suggestions: which links to add, and with what anchor text.

For every page, rank all other pages by topical similarity (TF-IDF cosine)
and propose the strongest matches that are not already linked. Each
suggestion carries:

* **source** — the page to edit,
* **target** — the page it should link to,
* **score** — similarity (0–1) boosted when the target is an orphan or a
  high-authority page that deserves more links,
* **anchor** — a real phrase taken from a sentence on the source page
  that mentions the target's keywords (never invented text),
* **sentence** — the full source sentence, so the user knows exactly
  where the link fits,
* **reason** — a plain-English explanation of why the link helps.

Rules that keep suggestions honest:

* never suggest a link that already exists (content links),
* never suggest a page linking to itself,
* never suggest thin pages (< 40 words) as targets,
* at most 3 suggestions per source page, so the list stays actionable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .keywords import (STOPWORDS, build_tfidf, cosine_similarity,
                       page_keywords, tokenise)
from .parser import PageData

MAX_SUGGESTIONS_PER_PAGE = 3
MIN_SIMILARITY = 0.08
MIN_TARGET_WORDS = 40


@dataclass
class Suggestion:
    source_url: str
    target_url: str
    score: float            # 0–1, higher = stronger match
    anchor: str             # phrase from the source page to link with
    sentence: str           # the source sentence the link fits in
    reason: str

    def to_dict(self) -> dict:
        return {
            "source_url": self.source_url,
            "target_url": self.target_url,
            "score": round(self.score, 3),
            "anchor": self.anchor,
            "sentence": self.sentence,
            "reason": self.reason,
        }


def _find_anchor(source: PageData, target_keywords: list[str],
                 target_title: str) -> tuple[str, str]:
    """Find the best anchor text on the source page for the target.

    Looks for a sentence containing one of the target's keywords and
    returns (anchor_phrase, sentence). Falls back to the target's title
    words when no sentence matches — the anchor is then still real text
    from the site, just from the target page instead of the source.
    """
    keywords = [kw for kw, _ in target_keywords]
    best: tuple[int, str, str] | None = None
    for sentence in source.sentences:
        # Match whole words, not substrings ("cafe" must not match "cafes").
        sentence_words = set(tokenise(sentence))
        hits = [kw for kw in keywords if kw in sentence_words]
        if not hits:
            continue
        # Prefer sentences that mention several keywords, then shorter
        # sentences (tighter, more natural anchor context).
        rank = (len(hits), -len(sentence))
        if best is None or rank > best[0]:
            # Anchor = the longest matching keyword in the sentence,
            # widened into a natural 2-word phrase: two adjacent target
            # keywords stay together ("brewing guide"), or a content word
            # before the keyword is added ("Good coffee"). A word is
            # only ever added when it is itself one of the target's
            # keywords or a real content word before it — never a
            # stopword, and never an unrelated word after it.
            anchor = max(hits, key=len)
            words = re.findall(r"[A-Za-z][A-Za-z\-']+", sentence)
            lowered_words = [w.lower() for w in words]
            if anchor in lowered_words:
                idx = lowered_words.index(anchor)
                keyword_set = set(keywords)
                start, end = idx, idx + 1
                if idx + 1 < len(words) and lowered_words[idx + 1] in keyword_set:
                    end = idx + 2
                elif idx > 0 and lowered_words[idx - 1] not in STOPWORDS:
                    start = idx - 1
                anchor = " ".join(words[start:end])
            best = (rank, anchor, sentence)
    if best:
        return best[1], best[2]
    # Fallback: the target page's own title (shortened to 2–4 words).
    title_words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-']+", target_title)]
    anchor = " ".join(title_words[:4]) if title_words else "read more"
    return anchor, ""


def suggest_links(pages: dict[str, PageData],
                  authority: dict[str, float],
                  orphan_pages: set[str],
                  max_per_page: int = MAX_SUGGESTIONS_PER_PAGE,
                  min_similarity: float = MIN_SIMILARITY) -> list[Suggestion]:
    """Ranked internal-link suggestions for the whole site."""
    if len(pages) < 2:
        return []
    vectors = build_tfidf(pages)
    keywords = {url: page_keywords(page) for url, page in pages.items()}
    titles = {url: page.title or page.h1 or url for url, page in pages.items()}
    existing = {url: page.internal_link_targets for url, page in pages.items()}

    suggestions: list[Suggestion] = []
    for source_url, source in pages.items():
        candidates: list[tuple[float, str]] = []
        for target_url, target in pages.items():
            if target_url == source_url:
                continue
            if target_url in existing[source_url]:
                continue  # already linked — nothing to suggest
            if target.word_count < MIN_TARGET_WORDS:
                continue  # thin page: not worth linking to yet
            similarity = cosine_similarity(vectors[source_url], vectors[target_url])
            if similarity < min_similarity:
                continue
            # Boost orphans (they need links most) and pages whose
            # authority is high relative to their inbound links.
            boost = 1.0
            if target_url in orphan_pages:
                boost += 0.5
            candidates.append((similarity * boost, target_url))
        candidates.sort(key=lambda item: -item[0])
        for score, target_url in candidates[:max_per_page]:
            target = pages[target_url]
            anchor, sentence = _find_anchor(source, keywords[target_url], titles[target_url])
            shared = [kw for kw, _ in keywords[target_url][:5]
                      if kw in tokenise(source.text)][:3]
            topic = ", ".join(shared) if shared else "your site"
            if target_url in orphan_pages:
                reason = (f"Orphan page — nothing links to it yet. "
                          f"Shares the topic '{topic}' with this page.")
            elif shared:
                reason = (f"Closely related — both pages cover "
                          f"'{', '.join(shared)}' — but this page never links to it.")
            else:
                reason = "Topically related page with no link from here yet."
            suggestions.append(Suggestion(
                source_url=source_url,
                target_url=target_url,
                score=min(1.0, round(score, 3)),
                anchor=anchor,
                sentence=sentence,
                reason=reason,
            ))
    # Strongest suggestions first, so the report reads top-down.
    suggestions.sort(key=lambda item: -item.score)
    return suggestions
