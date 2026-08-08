"""Pure, read-only analysis helpers for public ticket dashboards.

This module performs no network or filesystem I/O.  It never opens a browser,
uses cookies, authenticates, clicks controls, or writes to a website.  A URL
returned by :func:`parse_ticket_input` is only a candidate: callers must pass it
to ``web_reader.read_public_webpage`` so that DNS, redirects, response size, and
content type are checked before giving the resulting ``WebPage.text`` to
:func:`analyze_ticket_text`.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qsl, urlsplit, urlunsplit


MAX_DASHBOARD_TEXT_CHARS = 200_000
MAX_DASHBOARD_URL_CHARS = 2_048
METRIC_NAMES = ("total", "open", "pending", "urgent", "new", "closed")


class TicketDashboardError(ValueError):
    """Raised when dashboard input cannot be handled safely or reliably."""


@dataclass(frozen=True)
class TicketInput:
    """A normalized pasted-text input or a URL awaiting the safe web reader."""

    kind: Literal["text", "url"]
    value: str


@dataclass(frozen=True)
class TicketMetrics:
    """Ticket counts found next to explicit German or English KPI labels."""

    total: int | None = None
    open: int | None = None
    pending: int | None = None
    urgent: int | None = None
    new: int | None = None
    closed: int | None = None

    @property
    def found(self) -> bool:
        return any(getattr(self, name) is not None for name in METRIC_NAMES)

    def as_dict(self, *, include_missing: bool = False) -> dict[str, int | None]:
        values = {name: getattr(self, name) for name in METRIC_NAMES}
        if include_missing:
            return values
        return {name: value for name, value in values.items() if value is not None}


@dataclass(frozen=True)
class TicketAnalysis:
    """Deterministic analysis result suitable for an API response."""

    metrics: TicketMetrics
    language: Literal["de", "en"]
    summary: str


_SCHEME_PREFIX = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)
_SENSITIVE_QUERY_KEYS = frozenset({
    "access_token",
    "apikey",
    "api_key",
    "auth",
    "authorization",
    "cookie",
    "jwt",
    "password",
    "passwd",
    "session",
    "sessionid",
    "signature",
    "sig",
    "token",
})


def _normalize_text(value: str) -> str:
    if len(value) > MAX_DASHBOARD_TEXT_CHARS:
        raise TicketDashboardError("The pasted dashboard text is too large.")
    value = value.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[\t\f\v ]+", " ", line).strip() for line in value.split("\n")]
    normalized = "\n".join(lines).strip()
    if not normalized:
        raise TicketDashboardError("Dashboard input is empty.")
    return normalized


def _normalize_url(value: str) -> str:
    if len(value) > MAX_DASHBOARD_URL_CHARS:
        raise TicketDashboardError("The dashboard URL is too long.")
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise TicketDashboardError("The dashboard URL contains invalid whitespace.")
    if "\\" in value:
        raise TicketDashboardError("The dashboard URL contains an invalid path separator.")

    parsed = urlsplit(value)
    if parsed.scheme.casefold() != "https":
        raise TicketDashboardError("Only public HTTPS dashboard URLs are accepted.")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise TicketDashboardError("Dashboard URLs cannot contain credentials.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise TicketDashboardError("The dashboard URL has an invalid port.") from exc
    if port not in (None, 443):
        raise TicketDashboardError("Only the standard HTTPS port is accepted.")

    raw_hostname = parsed.hostname.rstrip(".").casefold()
    if raw_hostname == "localhost" or raw_hostname.endswith((".localhost", ".local", ".internal")):
        raise TicketDashboardError("Local and private dashboard URLs are blocked.")

    try:
        address = ipaddress.ip_address(raw_hostname)
    except ValueError:
        try:
            hostname = raw_hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise TicketDashboardError("The dashboard hostname is invalid.") from exc
        labels = hostname.split(".")
        if len(hostname) > 253 or any(not _DNS_LABEL.fullmatch(label) for label in labels):
            raise TicketDashboardError("The dashboard hostname is invalid.")
        netloc = hostname
    else:
        if not address.is_global:
            raise TicketDashboardError("Local and private dashboard URLs are blocked.")
        hostname = address.compressed
        netloc = f"[{hostname}]" if address.version == 6 else hostname

    try:
        query_items = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=False,
            max_num_fields=100,
        )
    except ValueError as exc:
        raise TicketDashboardError("The dashboard URL query is too complex.") from exc
    for key, _value in query_items:
        normalized_key = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
        if normalized_key in _SENSITIVE_QUERY_KEYS:
            raise TicketDashboardError("Private or signed dashboard URLs are not accepted.")

    # A literal :443 is equivalent to the default and is intentionally removed.
    # Fragments never reach the server and are removed as well.
    return urlunsplit(("https", netloc, parsed.path or "/", parsed.query, ""))


def parse_ticket_input(value: str) -> TicketInput:
    """Classify input without fetching it or causing any external action.

    Explicit URL schemes are treated as URL attempts and fail closed.  This
    prevents an HTTP, file, or authenticated URL from being disguised as pasted
    dashboard text.
    """
    if not isinstance(value, str):
        raise TicketDashboardError("Dashboard input must be text.")
    candidate = value.strip()
    if not candidate:
        raise TicketDashboardError("Dashboard input is empty.")
    if _SCHEME_PREFIX.match(candidate):
        return TicketInput(kind="url", value=_normalize_url(candidate))
    return TicketInput(kind="text", value=_normalize_text(value))


# Count separators accept the common English and German thousands formats, but
# not decimal values.  Ticket counts are bounded to nine digits.
_COUNT = r"(?:\d{1,3}(?:[.,'’ ]\d{3})+|\d{1,9})"
_LABELS = {
    "total": r"(?:total(?:\s+tickets?)?|tickets?\s+(?:total|gesamt)|gesamt(?:anzahl)?|insgesamt|alle\s+tickets?)",
    "open": r"(?:open(?:\s+tickets)?|offen(?:e|en|er|es)?(?:\s+tickets?)?)",
    "pending": r"(?:pending(?:\s+tickets)?|ausstehend(?:e|en|er|es)?(?:\s+tickets?)?|wartend(?:e|en|er|es)?(?:\s+tickets?)?|in\s+bearbeitung)",
    "urgent": r"(?:urgent(?:\s+tickets)?|critical(?:\s+tickets)?|dringend(?:e|en|er|es)?(?:\s+tickets?)?|kritisch(?:e|en|er|es)?(?:\s+tickets?)?)",
    "new": r"(?:new(?:\s+tickets)?|neu(?:e|en|er|es)?(?:\s+tickets?)?)",
    "closed": r"(?:closed(?:\s+tickets)?|resolved(?:\s+tickets)?|geschlossen(?:e|en|er|es)?(?:\s+tickets?)?|erledigt(?:e|en|er|es)?(?:\s+tickets?)?|gelöst(?:e|en|er|es)?(?:\s+tickets?)?)",
}
_PLURAL_LABELS = {
    "total": r"(?:total\s+tickets?|tickets?\s+(?:total|gesamt)|alle\s+tickets?)",
    "open": r"(?:open\s+tickets|offen(?:e|en)\s+tickets?)",
    "pending": r"(?:pending\s+tickets|ausstehend(?:e|en)\s+tickets?|wartend(?:e|en)\s+tickets?)",
    "urgent": r"(?:urgent\s+tickets|critical\s+tickets|dringend(?:e|en)\s+tickets?|kritisch(?:e|en)\s+tickets?)",
    "new": r"(?:new\s+tickets|neu(?:e|en)\s+tickets?)",
    "closed": r"(?:closed\s+tickets|resolved\s+tickets|geschlossen(?:e|en)\s+tickets?|erledigt(?:e|en)\s+tickets?|gelöst(?:e|en)\s+tickets?)",
}


def _parse_count(value: str) -> int:
    return int(re.sub(r"[.,'’ ]", "", value))


def _first_metric_value(text: str, metric: str) -> int | None:
    label = _LABELS[metric]
    plural_label = _PLURAL_LABELS[metric]
    quoted_label = rf"(?<!\w)[\"']?(?:{label})[\"']?(?!\w)"
    quoted_plural = rf"(?<!\w)[\"']?(?:{plural_label})[\"']?(?!\w)"
    patterns = (
        # Explicit labels and table/JSON separators are strongest and may share
        # a line with several other metrics.
        rf"{quoted_label}\s*(?:[:=|]|[—–-])\s*(?P<count>{_COUNT})",
        rf"(?<!\d)(?P<count>{_COUNT})\s*(?:[:=|]|[—–-])\s*{quoted_label}",
        rf"{quoted_label}\s*[([]\s*(?P<count>{_COUNT})\s*[)\]]",
        # Dashboard cards commonly put the label and value on one or two lines.
        rf"(?m)^[ \t]*{quoted_label}[ \t]+(?P<count>{_COUNT})(?:[ \t]+tickets?)?[ \t]*$",
        rf"(?m)^[ \t]*(?P<count>{_COUNT})[ \t]+{quoted_label}(?:[ \t]+tickets?)?[ \t]*$",
        rf"(?m)^[ \t]*{quoted_label}[ \t]*\n[ \t]*(?P<count>{_COUNT})[ \t]*$",
        rf"(?m)^[ \t]*(?P<count>{_COUNT})[ \t]*\n[ \t]*{quoted_label}[ \t]*$",
        # A count next to an explicitly plural status is reliable in prose.
        rf"(?<!\d)(?P<count>{_COUNT})\s+{quoted_plural}",
        rf"{quoted_plural}\s+(?P<count>{_COUNT})(?!\d)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _parse_count(match.group("count"))
    return None


def extract_ticket_metrics(text: str) -> TicketMetrics:
    """Extract explicitly labelled German/English dashboard counts.

    The extractor deliberately does not add status counts or infer a total:
    ``urgent`` and ``new`` frequently overlap with ``open`` and ``pending``.
    Missing or ambiguous values therefore remain ``None`` instead of being
    guessed.
    """
    normalized = _normalize_text(text)
    values = {name: _first_metric_value(normalized, name) for name in METRIC_NAMES}
    return TicketMetrics(**values)


_GERMAN_LANGUAGE_MARKERS = re.compile(
    r"\b(?:gesamt|gesamtanzahl|insgesamt|offen(?:e|en|er|es)?|ausstehend(?:e|en|er|es)?|"
    r"wartend(?:e|en|er|es)?|bearbeitung|dringend(?:e|en|er|es)?|kritisch(?:e|en|er|es)?|"
    r"neu(?:e|en|er|es)?|geschlossen(?:e|en|er|es)?|erledigt(?:e|en|er|es)?|gelöst(?:e|en|er|es)?)\b",
    re.IGNORECASE,
)
_ENGLISH_LANGUAGE_MARKERS = re.compile(
    r"\b(?:total|open|pending|urgent|critical|new|closed|resolved|dashboard)\b",
    re.IGNORECASE,
)


def detect_ticket_language(text: str) -> Literal["de", "en"]:
    """Choose German only when the pasted labels provide stronger evidence."""
    german = len(_GERMAN_LANGUAGE_MARKERS.findall(text))
    english = len(_ENGLISH_LANGUAGE_MARKERS.findall(text))
    return "de" if german > english else "en"


def _summary_language(language: str, text: str = "") -> Literal["de", "en"]:
    normalized = language.strip().casefold().replace("_", "-")
    if normalized == "auto":
        return detect_ticket_language(text)
    if normalized == "de" or normalized.startswith("de-"):
        return "de"
    if normalized == "en" or normalized.startswith("en-"):
        return "en"
    raise TicketDashboardError("Summary language must be German, English, or auto.")


def summarize_ticket_metrics(metrics: TicketMetrics, language: str = "en") -> str:
    """Return a compact summary in a stable field order, without guesses."""
    selected_language = _summary_language(language)
    if not metrics.found:
        if selected_language == "de":
            return "Keine verlässlichen Ticket-Kennzahlen gefunden."
        return "No reliable ticket metrics were found."

    labels = {
        "de": {
            "total": "Gesamt", "open": "Offen", "pending": "Ausstehend",
            "urgent": "Dringend", "new": "Neu", "closed": "Geschlossen",
        },
        "en": {
            "total": "Total", "open": "Open", "pending": "Pending",
            "urgent": "Urgent", "new": "New", "closed": "Closed",
        },
    }[selected_language]
    parts = [
        f"{labels[name]}: {getattr(metrics, name)}"
        for name in METRIC_NAMES
        if getattr(metrics, name) is not None
    ]
    return "Tickets — " + " · ".join(parts) + "."


def analyze_ticket_text(text: str, language: str = "auto") -> TicketAnalysis:
    """Analyze already pasted/read text without any external operation."""
    source = parse_ticket_input(text)
    if source.kind == "url":
        raise TicketDashboardError(
            "Read the public URL through web_reader first, then analyze its returned text."
        )
    selected_language = _summary_language(language, source.value)
    metrics = extract_ticket_metrics(source.value)
    return TicketAnalysis(
        metrics=metrics,
        language=selected_language,
        summary=summarize_ticket_metrics(metrics, selected_language),
    )
