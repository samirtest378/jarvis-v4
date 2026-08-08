"""Focused tests for the pure, read-only ticket dashboard analyzer."""

from __future__ import annotations

import asyncio

import pytest

import server

from ticket_dashboard import (
    MAX_DASHBOARD_TEXT_CHARS,
    TicketDashboardError,
    TicketMetrics,
    analyze_ticket_text,
    extract_ticket_metrics,
    parse_ticket_input,
    summarize_ticket_metrics,
)
from web_reader import WebPage


def test_classifies_pasted_text_without_external_work():
    source = parse_ticket_input("  Gesamt: 12\r\nOffen: 4\x00  ")

    assert source.kind == "text"
    assert source.value == "Gesamt: 12\nOffen: 4"


def test_prepares_only_a_public_https_candidate_for_the_existing_web_reader():
    source = parse_ticket_input("HTTPS://Example.COM:443/support?view=queue#private-fragment")

    assert source.kind == "url"
    assert source.value == "https://example.com/support?view=queue"


@pytest.mark.parametrize(
    "value",
    [
        "http://example.com/tickets",
        "file:///etc/passwd",
        "https://user:password@example.com/tickets",
        "https://example.com:8443/tickets",
        "https://localhost/tickets",
        "https://service.internal/tickets",
        "https://127.0.0.1/tickets",
        "https://10.0.0.5/tickets",
        "https://[::1]/tickets",
        "https://example.com/tickets?access_token=secret",
        "https://example.com/tickets?API-Key=secret",
    ],
)
def test_rejects_non_public_authenticated_or_signed_url_inputs(value):
    with pytest.raises(TicketDashboardError):
        parse_ticket_input(value)


def test_rejects_empty_and_bounded_inputs():
    with pytest.raises(TicketDashboardError, match="empty"):
        parse_ticket_input(" \n ")
    with pytest.raises(TicketDashboardError, match="too large"):
        parse_ticket_input("x" * (MAX_DASHBOARD_TEXT_CHARS + 1))


def test_extracts_all_german_metrics_from_common_dashboard_cards():
    metrics = extract_ticket_metrics(
        """
        Support Übersicht
        Gesamt: 1.234
        Offen
        42
        Ausstehend | 8
        Dringend (3)
        Neue Tickets: 11
        Geschlossen: 1.170
        """
    )

    assert metrics == TicketMetrics(
        total=1234,
        open=42,
        pending=8,
        urgent=3,
        new=11,
        closed=1170,
    )


def test_extracts_english_json_table_and_plural_prose_metrics():
    metrics = extract_ticket_metrics(
        """
        {"total": 1,250, "open": 24, "pending": 6}
        4 urgent tickets require review and 9 new tickets arrived.
        Closed | 1,220
        """
    )

    assert metrics.as_dict() == {
        "total": 1250,
        "open": 24,
        "pending": 6,
        "urgent": 4,
        "new": 9,
        "closed": 1220,
    }


def test_does_not_confuse_individual_ticket_ids_with_kpi_counts():
    metrics = extract_ticket_metrics(
        "Open ticket #1234 was assigned. Closed ticket #99 was reopened."
    )

    assert metrics.found is False
    assert metrics.as_dict() == {}


def test_missing_metrics_stay_missing_instead_of_being_inferred_or_added():
    metrics = extract_ticket_metrics("Open: 7\nUrgent: 2\nNew: 3")

    assert metrics == TicketMetrics(open=7, urgent=2, new=3)
    assert metrics.total is None
    assert metrics.closed is None


def test_summary_is_compact_ordered_and_language_specific():
    metrics = TicketMetrics(total=20, open=4, urgent=1, closed=16)

    assert summarize_ticket_metrics(metrics, "de-DE") == (
        "Tickets — Gesamt: 20 · Offen: 4 · Dringend: 1 · Geschlossen: 16."
    )
    assert summarize_ticket_metrics(metrics, "en-GB") == (
        "Tickets — Total: 20 · Open: 4 · Urgent: 1 · Closed: 16."
    )


def test_analysis_detects_german_and_has_a_deterministic_fallback():
    german = analyze_ticket_text("Offene Tickets: 5\nGeschlossen: 8")
    fallback = analyze_ticket_text("Team queue is available but contains no KPI tiles.")

    assert german.language == "de"
    assert german.summary == "Tickets — Offen: 5 · Geschlossen: 8."
    assert fallback.language == "en"
    assert fallback.metrics.found is False
    assert fallback.summary == "No reliable ticket metrics were found."


def test_url_analysis_never_fetches_or_silently_treats_url_as_dashboard_text():
    with pytest.raises(TicketDashboardError, match="web_reader"):
        analyze_ticket_text("https://example.com/tickets")


def test_rejects_unsupported_summary_language():
    with pytest.raises(TicketDashboardError, match="German, English, or auto"):
        summarize_ticket_metrics(TicketMetrics(total=1), "fr")


def test_api_analyzes_pasted_ticket_text_locally_without_ai_or_web(monkeypatch):
    async def must_not_fetch(_url: str):
        raise AssertionError("pasted text must not make a web request")

    monkeypatch.setattr(server, "read_public_webpage", must_not_fetch)
    result = asyncio.run(server.api_analyze_ticket_dashboard(server.TicketDashboardRequest(
        workspace_name="  Support   Zürich  ",
        snapshot="Gesamt: 18\nOffen: 5\nDringend: 2",
        language="de-DE",
    )))

    assert result["success"] is True
    assert result["title"] == "Support Zürich"
    assert result["source"] == "pasted_snapshot"
    assert result["metrics"]["total"] == 18
    assert result["metrics"]["open"] == 5
    assert result["summary"] == "Tickets — Gesamt: 18 · Offen: 5 · Dringend: 2."
    assert result["safety"] == {
        "read_only": True,
        "used_cookies": False,
        "clicked_or_submitted": False,
        "sent_to_ai_provider": False,
    }


def test_api_reads_only_the_validated_public_page(monkeypatch):
    requested: list[str] = []

    async def read_page(url: str):
        requested.append(url)
        return WebPage(
            url="https://support.example.com/queue",
            title="Customer Support",
            text="Total tickets: 40\nOpen: 7\nPending: 3\nClosed: 30",
        )

    monkeypatch.setattr(server, "read_public_webpage", read_page)
    result = asyncio.run(server.api_analyze_ticket_dashboard(server.TicketDashboardRequest(
        url="https://support.example.com/queue#private",
        language="en",
    )))

    assert requested == ["https://support.example.com/queue"]
    assert result["source"] == "public_webpage"
    assert result["title"] == "Customer Support"
    assert result["metrics"]["total"] == 40
    assert result["safety"]["clicked_or_submitted"] is False
