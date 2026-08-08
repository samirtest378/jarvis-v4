from __future__ import annotations

import json

import httpx
import pytest

import google_account
import server


@pytest.mark.asyncio
async def test_google_client_refreshes_once_and_reads_only_calendar_and_mail_metadata(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "123-example.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "refresh-token")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if str(request.url) == google_account.TOKEN_ENDPOINT:
            return httpx.Response(200, json={"access_token": "short-lived-access", "expires_in": 3600})
        assert request.headers["authorization"] == "Bearer short-lived-access"
        if request.url.path.endswith("/calendars/primary/events"):
            return httpx.Response(200, json={"items": [{
                "summary": "Planning",
                "start": {"dateTime": "2026-07-22T10:00:00+02:00"},
                "location": "Office",
            }]})
        if request.url.path.endswith("/users/me/messages"):
            return httpx.Response(200, json={"messages": [{"id": "message-1"}]})
        if request.url.path.endswith("/users/me/messages/message-1"):
            return httpx.Response(200, json={"payload": {"headers": [
                {"name": "From", "value": "Client <client@example.com>"},
                {"name": "Subject", "value": "Proposal"},
                {"name": "Date", "value": "Wed, 22 Jul 2026 08:00:00 +0000"},
            ]}})
        raise AssertionError(f"Unexpected Google request: {request.url}")

    client = google_account.GoogleAccountClient(transport=httpx.MockTransport(handler))
    events = await client.upcoming_events()
    messages = await client.unread_messages()

    assert events == [{"summary": "Planning", "start": "2026-07-22T10:00:00+02:00", "location": "Office"}]
    assert messages[0]["subject"] == "Proposal"
    assert sum(str(request.url) == google_account.TOKEN_ENDPOINT for request in requests) == 1
    assert all(request.method == "GET" for request in requests if str(request.url) != google_account.TOKEN_ENDPOINT)
    assert b"refresh-token" in requests[0].content


@pytest.mark.asyncio
async def test_explicit_google_lookups_are_used_on_windows_when_connected(monkeypatch):
    class FakeGoogle:
        configured = True

        async def upcoming_events(self):
            return [{"summary": "Review", "start": "tomorrow", "location": ""}]

        async def unread_messages(self):
            return [{"subject": "Invoice", "from": "Accounts", "date": ""}]

    monkeypatch.setattr(server.sys, "platform", "win32")
    monkeypatch.setattr(server, "google_account_client", FakeGoogle())

    assert "Google Calendar" in await server._do_calendar_lookup()
    assert "Review" in await server._do_calendar_lookup()
    assert "Gmail" in await server._do_mail_lookup()
    assert "Invoice" in await server._do_mail_lookup()


@pytest.mark.asyncio
async def test_settings_status_reports_google_connection_without_exposing_tokens(monkeypatch):
    monkeypatch.setattr(
        server,
        "google_account_client",
        server.GoogleAccountClient(
            client_id="123-example.apps.googleusercontent.com",
            refresh_token="never-return-this-refresh-token",
        ),
    )
    status = await server.api_settings_status()
    serialized = json.dumps(status)

    assert status["capabilities"]["google_account_connected"] is True
    assert status["capabilities"]["private_notes"] is True
    assert status["env_keys_set"]["google_account"] is True
    assert "never-return-this-refresh-token" not in serialized
