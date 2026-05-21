"""Fetch title + description metadata from a URL.

Used by the Bookmark widget. Best-effort: returns empty fields when the
target page can't be fetched or doesn't expose useful metadata. Never raises
on parse failure — the caller still gets a record they can later edit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

log = logging.getLogger("mnemosyne.link_fetch")

USER_AGENT = (
    "Mozilla/5.0 (compatible; MnemosyneBot/1.0; "
    "+https://mnemosyne.avorial.com)"
)
MAX_BYTES = 1_000_000
TIMEOUT_SECONDS = 10.0


@dataclass
class LinkMeta:
    url: str          # final URL after redirects
    title: str
    description: str


class _MetaExtractor(HTMLParser):
    """Extract <title>, og:title, og:description, and meta description."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_title = False
        self._title_buf: list[str] = []
        self._title = ""
        self._og_title = ""
        self._og_description = ""
        self._meta_description = ""
        self._stop = False

    def handle_starttag(self, tag, attrs) -> None:
        if self._stop:
            return
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            d = {k.lower(): (v or "") for k, v in attrs}
            prop = d.get("property", "").lower()
            name = d.get("name", "").lower()
            content = d.get("content", "")
            if prop == "og:title" and not self._og_title:
                self._og_title = content
            elif prop == "og:description" and not self._og_description:
                self._og_description = content
            elif name == "description" and not self._meta_description:
                self._meta_description = content
        elif tag == "body":
            # Stop once <body> opens — all the meta we want is in <head>.
            self._stop = True

    def handle_data(self, data) -> None:
        if self._in_title:
            self._title_buf.append(data)

    def handle_endtag(self, tag) -> None:
        if tag == "title":
            self._in_title = False
            self._title = "".join(self._title_buf).strip()

    @property
    def title(self) -> str:
        return (self._og_title or self._title).strip()

    @property
    def description(self) -> str:
        return (self._og_description or self._meta_description).strip()


async def fetch_meta(url: str) -> LinkMeta:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"unsupported URL scheme: {parsed.scheme or '(none)'}")

    final_url = url
    body_bytes = b""
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=TIMEOUT_SECONDS,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        ) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                final_url = str(resp.url)
                ctype = resp.headers.get("content-type", "").lower()
                if "html" not in ctype and "xml" not in ctype:
                    return LinkMeta(url=final_url, title="", description="")
                async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                    body_bytes += chunk
                    if len(body_bytes) >= MAX_BYTES:
                        break
    except httpx.HTTPError as e:
        log.warning("link fetch failed for %s: %s", url, e)
        return LinkMeta(url=url, title="", description="")

    encoding = "utf-8"
    text = body_bytes.decode(encoding, errors="replace")
    parser = _MetaExtractor()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        log.exception("HTML parse failed for %s", final_url)
    return LinkMeta(url=final_url, title=parser.title, description=parser.description)
