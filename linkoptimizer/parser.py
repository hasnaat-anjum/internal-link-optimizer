"""HTML parsing: turn one fetched page into structured data.

The parser separates *content* links (inside <main>/<article> or plain
body text) from *boilerplate* links (inside <nav>, <header>, <footer> or
<aside>). That distinction matters for SEO: a link in your menu tells
Google almost nothing about topical relevance, while a link inside an
article paragraph does. Suggestions therefore only count content links
when deciding whether two pages are already connected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urldefrag

# Tags whose links count as boilerplate (navigation / chrome), not content.
BOILERPLATE_TAGS = {"nav", "header", "footer", "aside"}
# Tags whose text we never treat as page content.
SKIP_TAGS = {"script", "style", "noscript", "svg"}
# Tags that end a sentence for anchor-text extraction.
BLOCK_TAGS = {
    "p", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "div", "section", "article", "blockquote", "td", "tr", "br",
}


@dataclass
class Link:
    """One link found on a page."""

    href: str                      # raw href attribute, as written
    url: str                       # resolved, normalised absolute URL
    anchor: str                    # link text, stripped
    in_content: bool               # True if inside main content, not nav/footer
    nofollow: bool = False         # rel="nofollow" present


@dataclass
class PageData:
    """Everything the analyser needs about one page."""

    url: str
    status: int = 200
    title: str = ""
    h1: str = ""
    description: str = ""
    text: str = ""                 # visible text of the page
    sentences: list[str] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    word_count: int = 0

    @property
    def content_links(self) -> list[Link]:
        """Links inside the page's main content (not nav/header/footer)."""
        return [link for link in self.links if link.in_content]

    @property
    def internal_link_targets(self) -> set[str]:
        """URLs this page links to (content links only)."""
        return {link.url for link in self.content_links}


def normalise_url(url: str) -> str:
    """Normalise a URL for comparison: drop fragment, trailing slash on
    the bare host, and sort-free lowercase scheme/host. Keeps the path
    and query intact so /page and /page?x=1 stay different pages."""
    url, _ = urldefrag(url.strip())
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    path = parsed.path or "/"
    return parsed._replace(scheme=scheme, netloc=host, path=path).geturl()


def is_same_site(url: str, base: str) -> bool:
    """True when *url* belongs to the same host as *base*."""
    return urlparse(url).netloc.lower() == urlparse(base).netloc.lower()


class _PageParser(HTMLParser):
    """Single-pass parser collecting title, headings, text and links."""

    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.description = ""
        self.text_parts: list[str] = []
        self.links: list[Link] = []
        self._tag_stack: list[str] = []
        self._skip_depth = 0
        self._boilerplate_depth = 0
        self._in_title = False
        self._in_h1 = False
        self._current_link: dict | None = None
        self._link_text: list[str] = []

    # -- tag tracking -------------------------------------------------
    def handle_starttag(self, tag, attrs):
        self._tag_stack.append(tag)
        attrs_dict = dict(attrs)
        if tag in SKIP_TAGS:
            self._skip_depth += 1
        if tag in BOILERPLATE_TAGS:
            self._boilerplate_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "h1" and not self.h1_parts:
            self._in_h1 = True
        if tag == "meta":
            name = attrs_dict.get("name", "").lower()
            if name == "description":
                self.description = attrs_dict.get("content", "").strip()
        if tag == "a":
            href = attrs_dict.get("href", "").strip()
            if href and not href.startswith(("#", "mailto:", "tel:", "javascript:")):
                rel = attrs_dict.get("rel", "").lower()
                self._current_link = {
                    "href": href,
                    "url": normalise_url(urljoin(self.base_url, href)),
                    "nofollow": "nofollow" in rel.split(),
                    "in_content": not any(t in BOILERPLATE_TAGS for t in self._tag_stack),
                }
                self._link_text = []
        if tag in BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "h1":
            self._in_h1 = False
        if tag in SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag in BOILERPLATE_TAGS and self._boilerplate_depth > 0:
            self._boilerplate_depth -= 1
        if tag == "a" and self._current_link is not None:
            anchor = " ".join("".join(self._link_text).split())
            if anchor or self._current_link["href"]:
                self.links.append(Link(
                    href=self._current_link["href"],
                    url=self._current_link["url"],
                    anchor=anchor,
                    in_content=self._current_link["in_content"],
                    nofollow=self._current_link["nofollow"],
                ))
            self._current_link = None
            self._link_text = []
        if tag in BLOCK_TAGS:
            self.text_parts.append("\n")
        # Pop the tag from the stack (tolerate malformed HTML).
        if tag in self._tag_stack:
            while self._tag_stack and self._tag_stack[-1] != tag:
                self._tag_stack.pop()
            if self._tag_stack:
                self._tag_stack.pop()

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        elif self._in_h1:
            self.h1_parts.append(data)
        if self._current_link is not None:
            self._link_text.append(data)
        # Anchor text is part of the visible text too — but navigation,
        # header and footer copy is boilerplate: it appears on every page
        # and would swamp the keyword analysis, so it stays out of the
        # page text used for topical similarity and anchor sentences.
        # The <title> is metadata, not visible text, so it stays out too
        # (it would otherwise glue itself onto the first sentence).
        if self._boilerplate_depth == 0 and not self._in_title:
            self.text_parts.append(data)


def split_sentences(text: str) -> list[str]:
    """Split visible text into sentences, keeping each one short enough
    to be useful as anchor-text context (max ~240 characters).

    Text is split per line first: headings and blocks are separated by
    newlines in the parser, so a heading never glues itself onto the
    sentence that follows it.
    """
    sentences: list[str] = []
    for block in text.split("\n"):
        clean = re.sub(r"\s+", " ", block).strip()
        if not clean:
            continue
        for part in re.split(r"(?<=[.!?])\s+", clean):
            part = part.strip()
            if len(part) < 15:
                continue
            # A fragment with no terminal punctuation is usually a bare
            # heading, not a sentence — it would otherwise win the
            # anchor ranking just by being short.
            if part[-1] not in ".!?…":
                continue
            if len(part) > 240:  # long block: keep the first clause only
                part = part[:240].rsplit(" ", 1)[0] + "…"
            sentences.append(part)
    return sentences


def parse_html(html: str, url: str, status: int = 200) -> PageData:
    """Parse one page's HTML into a :class:`PageData`."""
    parser = _PageParser(url)
    try:
        parser.feed(html)
    except Exception:
        # A malformed page should never kill the whole crawl.
        pass
    text = "\n".join(
        line for line in
        (re.sub(r"\s+", " ", chunk).strip()
         for chunk in "".join(parser.text_parts).split("\n"))
        if line
    )
    words = re.findall(r"[A-Za-z][A-Za-z\-']+", text)
    return PageData(
        url=normalise_url(url),
        status=status,
        title=" ".join("".join(parser.title_parts).split()),
        h1=" ".join("".join(parser.h1_parts).split()),
        description=parser.description,
        text=text,
        sentences=split_sentences(text),
        links=parser.links,
        word_count=len(words),
    )
