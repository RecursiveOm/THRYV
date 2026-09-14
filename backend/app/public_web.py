"""Bounded, cookie-free public HTTP browsing. Page text never authorizes tools."""

import asyncio
import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree

import aiohttp

from app.database import now
from app.errors import AppError
from app.memory import SECRET_SHAPES

MAX_BYTES = 2_000_000


def public_address(value):
    address = ipaddress.ip_address(value)
    return address.is_global and not address.is_multicast and not address.is_reserved


def public_url(value: str) -> str:
    try:
        if (
            len(value) > 2048
            or any(ord(c) <= 32 or ord(c) == 127 for c in value)
            or "\\" in value
            or SECRET_SHAPES.search(value)
        ):
            raise ValueError
        parts = urlsplit(value)
        host = (parts.hostname or "").encode("idna").decode("ascii").lower()
        if (
            parts.scheme not in {"http", "https"}
            or parts.username is not None
            or parts.password is not None
            or parts.port not in {None, 80, 443}
            or not host
            or host.endswith((".localhost", ".local", ".internal", ".test"))
        ):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if "." not in host or host.endswith("."):
                raise ValueError from None
        else:
            if not public_address(address):
                raise ValueError
        return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))
    except (ValueError, UnicodeError):
        raise AppError(
            "web_blocked", "Only ordinary public HTTP(S) URLs are supported.", 422
        ) from None


class PublicResolver(aiohttp.abc.AbstractResolver):
    async def resolve(self, host, port=0, family=socket.AF_INET):
        addresses = await asyncio.get_running_loop().getaddrinfo(
            host, port, type=socket.SOCK_STREAM, family=family
        )
        # Validate and pin every answer; the connector performs no second DNS lookup.
        if not addresses or any(not public_address(a[4][0]) for a in addresses):
            raise OSError("Non-public destination blocked")
        return [
            {
                "hostname": host,
                "host": a[4][0],
                "port": port,
                "family": a[0],
                "proto": a[2],
                "flags": socket.AI_NUMERICHOST,
            }
            for a in addresses
        ]

    async def close(self):
        pass


class PageParser(HTMLParser):
    def __init__(self, url):
        super().__init__(convert_charrefs=True)
        self.url = url
        self.text = []
        self.main = []
        self.title = []
        self.links = []
        self.stack = []
        self.link = None

    def handle_starttag(self, tag, attrs):
        if len(self.stack) >= 128:
            raise AppError("web_structure", "The page exceeds the HTML nesting limit.", 422)
        if tag not in {
            "br",
            "hr",
            "img",
            "meta",
            "link",
            "input",
            "source",
            "wbr",
            "area",
            "base",
            "embed",
            "param",
            "track",
            "col",
        }:
            self.stack.append(tag)
        if tag == "a" and len(self.links) < 150:
            href = dict(attrs).get("href", "")
            try:
                target = public_url(urljoin(self.url, href))
            except AppError:
                return
            self.link = {"id": len(self.links) + 1, "url": target, "title": ""}
            self.links.append(self.link)

    def handle_endtag(self, tag):
        if tag in self.stack:
            self.stack = self.stack[: len(self.stack) - 1 - self.stack[::-1].index(tag)]
        if tag == "a":
            self.link = None

    def handle_data(self, data):
        value = " ".join(data.split())
        if not value or set(self.stack) & {"script", "style", "noscript", "svg", "form"}:
            return
        if "title" in self.stack:
            self.title.append(value)
        if not set(self.stack) & {"nav", "header", "footer", "title"}:
            self.text.append(value)
            if set(self.stack) & {"main", "article"}:
                self.main.append(value)
        if self.link:
            self.link["title"] = (self.link["title"] + " " + value).strip()[:200]

    def result(self):
        return {
            "title": " ".join(self.title)[:200] or self.url,
            "url": self.url,
            "content": "\n".join(self.main or self.text)[:12000],
            "links": self.links,
            "retrieved_at": now(),
        }


class PublicWeb:
    async def fetch(self, url):
        visited = set()
        connector = aiohttp.TCPConnector(resolver=PublicResolver(), use_dns_cache=False, limit=2)
        try:
            async with aiohttp.ClientSession(
                connector=connector,
                cookie_jar=aiohttp.DummyCookieJar(),
                trust_env=False,
                auto_decompress=False,
                timeout=aiohttp.ClientTimeout(total=12),
                headers={"User-Agent": "THRYV-PublicResearch/3.0", "Accept-Encoding": "identity"},
            ) as client:
                for _ in range(4):
                    url = public_url(url)
                    if url in visited:
                        raise AppError("web_loop", "The page redirected in a loop.", 422)
                    visited.add(url)
                    async with client.get(url, allow_redirects=False) as response:
                        if response.status in {301, 302, 303, 307, 308}:
                            url = urljoin(url, response.headers.get("Location", ""))
                            continue
                        if response.status != 200:
                            raise AppError(
                                "web_unavailable",
                                "The public page is unavailable or requires access.",
                                422,
                            )
                        kind = response.content_type
                        if (
                            kind
                            not in {
                                "text/html",
                                "text/plain",
                                "application/rss+xml",
                                "application/xml",
                                "text/xml",
                            }
                            or response.headers.get("Content-Encoding", "identity") != "identity"
                        ):
                            raise AppError(
                                "web_format",
                                "This page format requires an unsupported browser feature.",
                                422,
                            )
                        data = bytearray()
                        async for chunk in response.content.iter_chunked(16384):
                            data.extend(chunk)
                            if len(data) > MAX_BYTES:
                                raise AppError(
                                    "web_size",
                                    "This page exceeds the public research size limit.",
                                    422,
                                )
                        return url, data.decode("utf-8", errors="replace"), kind
        except (aiohttp.ClientError, OSError, TimeoutError):
            raise AppError(
                "web_unavailable", "The public page could not be reached safely.", 422
            ) from None
        raise AppError("web_redirects", "The page exceeded the redirect limit.", 422)

    async def read(self, url):
        url, body, kind = await self.fetch(url)
        if kind == "text/plain":
            return {
                "title": url,
                "url": url,
                "content": body[:12000],
                "links": [],
                "retrieved_at": now(),
            }
        parser = PageParser(url)
        parser.feed(body)
        page = parser.result()
        if not page["content"]:
            raise AppError(
                "web_empty",
                "No readable public text was available; JavaScript or login may be required.",
                422,
            )
        return page

    async def search(self, query):
        _, body, _ = await self.fetch(
            "https://www.bing.com/search?" + urlencode({"format": "rss", "q": query})
        )
        if "<!DOCTYPE" in body.upper() or "<!ENTITY" in body.upper():
            raise AppError("web_search", "Public search returned an unsupported response.", 422)
        try:
            tree = ElementTree.fromstring(body)
        except ElementTree.ParseError:
            raise AppError("web_search", "Public search is temporarily unavailable.", 422) from None
        results = []
        for item in tree.findall("./channel/item")[:10]:
            try:
                url = public_url(item.findtext("link", ""))
            except AppError:
                continue
            results.append(
                {
                    "url": url,
                    "title": item.findtext("title", "")[:200],
                    "description": item.findtext("description", "")[:600],
                }
            )
        if not results:
            raise AppError("web_search", "Public search returned no usable sources.", 422)
        return results
