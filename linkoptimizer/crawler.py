"""Crawling: fetch a site politely and turn it into PageData objects.

Two modes:

* **Live crawl** — start at one URL, follow same-site links breadth-first,
  honouring robots.txt, a page cap and a delay between requests.
* **Local folder** — read a directory of ``.html`` files (a static site
  export, a Jekyll/Hugo build output, or the bundled demo site). No network
  needed, so the tool works fully offline.

A sitemap (``sitemap.xml`` or a sitemap index) can seed the crawl instead
of link-following, which is the fastest way to cover a large site.
"""

from __future__ import annotations

import os
import re
import time
import urllib.error
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import deque
from urllib.parse import urljoin, urlparse

from .parser import PageData, is_same_site, normalise_url, parse_html

USER_AGENT = "InternalLinkOptimizer/1.0 (+https://github.com/hasnaat-anjum/internal-link-optimizer)"
DEFAULT_TIMEOUT = 10
DEFAULT_MAX_PAGES = 200
DEFAULT_DELAY = 0.2


class CrawlResult:
    """Outcome of a crawl: the pages found, plus what went wrong."""

    def __init__(self):
        self.pages: dict[str, PageData] = {}
        self.broken: dict[str, int] = {}   # url -> HTTP status (non-200)
        self.skipped_robots: list[str] = []
        self.errors: dict[str, str] = {}   # url -> short error message

    def __len__(self):
        return len(self.pages)


def _fetch(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[int, str, str]:
    """Fetch one URL. Returns (status, html, final_url_after_redirects)."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            raw = response.read()
            html = raw.decode(charset, errors="replace")
            return response.status, html, response.geturl()
    except urllib.error.HTTPError as exc:
        return exc.code, "", url
    except Exception as exc:  # timeout, DNS failure, refused connection…
        raise RuntimeError(str(exc) or exc.__class__.__name__)


def _robots_allowed(robots_url: str, url: str, cache: dict) -> bool:
    """Check robots.txt (cached per host). Fail-open: if robots.txt cannot
    be fetched, the page is treated as allowed."""
    host = urlparse(robots_url).netloc
    if host not in cache:
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        try:
            parser.read()
        except Exception:
            cache[host] = None
        else:
            cache[host] = parser
    parser = cache[host]
    if parser is None:
        return True
    try:
        return parser.can_fetch(USER_AGENT, url)
    except Exception:
        return True


def parse_sitemap(xml_text: str) -> list[str]:
    """Extract page URLs from a sitemap or sitemap index (no recursion
    into nested sitemaps — pass each sitemap URL explicitly)."""
    urls: list[str] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return urls
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    for loc in root.findall(".//sm:loc", namespace):
        if loc.text:
            urls.append(loc.text.strip())
    if not urls:  # sitemap without a namespace
        for loc in root.iter("loc"):
            if loc.text:
                urls.append(loc.text.strip())
    return urls


def crawl_site(start_url: str, max_pages: int = DEFAULT_MAX_PAGES,
               delay: float = DEFAULT_DELAY, respect_robots: bool = True,
               sitemap_url: str | None = None,
               progress=None) -> CrawlResult:
    """Breadth-first crawl of one site. *progress* is an optional callback
    called with (fetched_count, url) after each page."""
    result = CrawlResult()
    start_url = normalise_url(start_url)
    host = urlparse(start_url).netloc
    robots_cache: dict = {}

    # Seed the queue: from the sitemap when given, else from the start URL.
    queue: deque[str] = deque()
    if sitemap_url:
        try:
            _, xml_text, _ = _fetch(sitemap_url)
            for url in parse_sitemap(xml_text):
                if is_same_site(url, start_url):
                    queue.append(normalise_url(url))
        except Exception as exc:
            result.errors[sitemap_url] = f"sitemap fetch failed: {exc}"
    if not queue:
        queue.append(start_url)

    seen: set[str] = set()
    while queue and len(result.pages) < max_pages:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        if respect_robots and not _robots_allowed(
                f"{urlparse(url).scheme}://{host}/robots.txt", url, robots_cache):
            result.skipped_robots.append(url)
            continue
        try:
            status, html, final_url = _fetch(url)
        except RuntimeError as exc:
            result.errors[url] = str(exc)
            continue
        final_url = normalise_url(final_url)
        if status != 200 or not html:
            result.broken[final_url] = status
            continue
        page = parse_html(html, final_url, status=status)
        result.pages[final_url] = page
        if progress:
            progress(len(result.pages), final_url)
        # Queue same-site links we have not seen yet.
        for link in page.links:
            target = link.url
            if is_same_site(target, start_url) and target not in seen:
                queue.append(target)
        if delay:
            time.sleep(delay)
    return result


def crawl_local_folder(folder: str) -> CrawlResult:
    """Analyse a folder of HTML files as if it were a site. The folder
    root is the "home page"; relative links resolve against file paths,
    so the demo site works with zero network access."""
    result = CrawlResult()
    folder = os.path.abspath(folder)
    html_files: dict[str, str] = {}  # url-path -> filesystem path
    for root, _dirs, files in os.walk(folder):
        for name in files:
            if name.lower().endswith((".html", ".htm")):
                full = os.path.join(root, name)
                rel = os.path.relpath(full, folder).replace(os.sep, "/")
                # index.html at the root is the home page "/".
                url_path = "/" if rel == "index.html" else "/" + rel
                html_files[url_path] = full

    base = "http://local/"
    for url_path, full in sorted(html_files.items()):
        url = normalise_url(urljoin(base, url_path.lstrip("/")))
        try:
            with open(full, encoding="utf-8", errors="replace") as handle:
                html = handle.read()
        except OSError as exc:
            result.errors[url] = str(exc)
            continue
        page = parse_html(html, url, status=200)
        result.pages[url] = page

    # A link to a file that does not exist in the folder is broken.
    for page in result.pages.values():
        for link in page.links:
            target = urlparse(link.url).path or "/"
            if target not in html_files and not target.startswith("http"):
                # Only flag same-site (local) targets.
                if urlparse(link.url).netloc in ("local", ""):
                    result.broken.setdefault(link.url, 404)
    return result
