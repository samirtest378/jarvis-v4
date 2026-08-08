"""Small, read-only reader for public HTTPS pages.

The reader deliberately has no browser session, cookies, authentication, or
write methods.  Every redirect is validated again to prevent a public page
from forwarding JARVIS into the user's local network.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Awaitable, Callable
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx


MAX_RESPONSE_BYTES = 1024 * 1024
MAX_TEXT_CHARS = 20_000
MAX_REDIRECTS = 3
ALLOWED_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml", "text/plain"})
Resolver = Callable[[str], Awaitable[list[str]]]


class WebReadError(ValueError):
    """Raised when a page cannot be read within the safety policy."""


@dataclass(frozen=True)
class WebPage:
    url: str
    title: str
    text: str


class _ReadableHTML(HTMLParser):
    _ignored = frozenset({
        "script", "style", "noscript", "template", "form", "input", "button",
        "textarea", "select", "option", "iframe", "object", "embed", "svg", "canvas",
    })
    _breaks = frozenset({
        "address", "article", "aside", "blockquote", "br", "div", "footer", "h1", "h2",
        "h3", "h4", "h5", "h6", "header", "li", "main", "nav", "p", "section", "td",
        "th", "title", "tr",
    })

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._title_depth = 0
        self._parts: list[str] = []
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag in self._ignored:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "title":
            self._title_depth += 1
        if tag in self._breaks:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in self._ignored and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if tag == "title" and self._title_depth:
            self._title_depth -= 1
        if tag in self._breaks:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if self._title_depth:
            self._title_parts.append(data)
        self._parts.append(data)

    def result(self) -> tuple[str, str]:
        title = _clean_text(" ".join(self._title_parts), 300)
        body = _clean_text(" ".join(self._parts), MAX_TEXT_CHARS)
        return title, body


def _clean_text(value: str, limit: int) -> str:
    value = value.replace("\x00", " ")
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line)[:limit].strip()


async def _system_resolver(hostname: str) -> list[str]:
    def resolve() -> list[str]:
        return sorted({item[4][0] for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)})

    try:
        return await asyncio.to_thread(resolve)
    except socket.gaierror as exc:
        raise WebReadError("The website address could not be resolved.") from exc


def _public_address(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False


async def _validate_url(raw_url: str, resolver: Resolver) -> str:
    candidate = raw_url.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme.casefold() != "https":
        raise WebReadError("Only public HTTPS websites can be read.")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise WebReadError("Website credentials are not accepted.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise WebReadError("The website port is invalid.") from exc
    if port not in (None, 443):
        raise WebReadError("Only the standard HTTPS port can be read.")

    hostname = parsed.hostname.rstrip(".").casefold()
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        raise WebReadError("Local and private websites are blocked.")
    addresses = await resolver(hostname)
    if not addresses or any(not _public_address(address) for address in addresses):
        raise WebReadError("Local and private websites are blocked.")

    netloc = f"[{hostname}]" if ":" in hostname else hostname
    return urlunsplit(("https", netloc, parsed.path or "/", parsed.query, ""))


async def read_public_webpage(
    url: str,
    *,
    resolver: Resolver = _system_resolver,
    transport: httpx.AsyncBaseTransport | None = None,
) -> WebPage:
    """Read visible text from a public HTTPS page using GET requests only."""
    current = await _validate_url(url, resolver)
    headers = {
        "User-Agent": "JARVIS-v4-ReadOnly/1.0",
        "Accept": "text/html, application/xhtml+xml, text/plain;q=0.9",
    }
    timeout = httpx.Timeout(12.0, connect=6.0)
    async with httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
        transport=transport,
    ) as client:
        for redirect_count in range(MAX_REDIRECTS + 1):
            async with client.stream("GET", current) as response:
                # Re-check the address the HTTP stack actually connected to.
                # This closes the DNS-rebinding gap between our lookup and the
                # client's own lookup when the transport exposes peer details.
                stream = response.extensions.get("network_stream")
                if stream is not None:
                    peer = stream.get_extra_info("server_addr")
                    if peer and not _public_address(str(peer[0])):
                        raise WebReadError("Local and private websites are blocked.")
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location or redirect_count >= MAX_REDIRECTS:
                        raise WebReadError("The website redirected too many times.")
                    current = await _validate_url(urljoin(current, location), resolver)
                    continue
                if response.status_code >= 400:
                    raise WebReadError(f"The website returned HTTP {response.status_code}.")

                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
                if content_type not in ALLOWED_CONTENT_TYPES:
                    raise WebReadError("This website did not return readable text.")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise WebReadError("The website response is too large.")
                    chunks.append(chunk)
                encoding = response.encoding or "utf-8"
                payload = b"".join(chunks).decode(encoding, errors="replace")

            if content_type == "text/plain":
                title, text = "", _clean_text(payload, MAX_TEXT_CHARS)
            else:
                parser = _ReadableHTML()
                parser.feed(payload)
                parser.close()
                title, text = parser.result()
            if not text:
                raise WebReadError("The website contains no readable text.")
            return WebPage(url=current, title=title, text=text)

    raise WebReadError("The website could not be read.")
