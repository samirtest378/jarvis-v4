"""Google Gmail and Calendar access for the desktop OAuth connection.

Calendar stays read-only. Gmail is read plus send: sending is the one write
the user asked for, and a sent message is visible to them in Sent. Nothing
here deletes or modifies existing mail.
"""

from __future__ import annotations

import asyncio
import base64
import os
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any
from urllib.parse import quote

import httpx


TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"


class GoogleAccountError(RuntimeError):
    """Safe, user-facing failure without response bodies or credentials."""


def google_account_configured() -> bool:
    return bool(os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip() and os.getenv("GOOGLE_REFRESH_TOKEN", "").strip())


class GoogleAccountClient:
    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
    ) -> None:
        self.client_id = (
            os.getenv("GOOGLE_OAUTH_CLIENT_ID", "") if client_id is None else client_id
        ).strip()
        self.client_secret = (
            os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "") if client_secret is None else client_secret
        ).strip()
        self.refresh_token = (
            os.getenv("GOOGLE_REFRESH_TOKEN", "") if refresh_token is None else refresh_token
        ).strip()
        self.transport = transport
        self._access_token = ""
        self._expires_at = 0.0
        self._token_lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.refresh_token)

    async def _token(self) -> str:
        if not self.configured:
            raise GoogleAccountError("Google is not connected. Open Settings → System → Google Account.")
        if self._access_token and time.monotonic() < self._expires_at - 60:
            return self._access_token
        async with self._token_lock:
            if self._access_token and time.monotonic() < self._expires_at - 60:
                return self._access_token
            form = {
                "client_id": self.client_id,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            }
            if self.client_secret:
                form["client_secret"] = self.client_secret
            try:
                async with httpx.AsyncClient(transport=self.transport, timeout=12.0) as client:
                    response = await client.post(TOKEN_ENDPOINT, data=form)
                if response.is_error:
                    raise GoogleAccountError("The Google connection expired or was revoked. Reconnect it in Settings.")
                payload = response.json()
                token = str(payload.get("access_token", "")).strip()
                if not token:
                    raise GoogleAccountError("Google did not return an access token. Reconnect it in Settings.")
                expires_in = max(120, min(int(payload.get("expires_in", 3600)), 86400))
                self._access_token = token
                self._expires_at = time.monotonic() + expires_in
                return token
            except GoogleAccountError:
                raise
            except Exception as exc:
                raise GoogleAccountError("Google could not be reached. Check the internet connection and try again.") from exc

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        token = await self._token()
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=12.0) as client:
                response = await client.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
            if response.status_code == 401:
                self._access_token = ""
                self._expires_at = 0.0
                raise GoogleAccountError("The Google connection needs to be renewed in Settings.")
            if response.is_error:
                raise GoogleAccountError("Google could not return the requested account data.")
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        except GoogleAccountError:
            raise
        except Exception as exc:
            raise GoogleAccountError("Google could not be reached. Check the internet connection and try again.") from exc

    async def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        token = await self._token()
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=20.0) as client:
                response = await client.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})
            if response.status_code == 401:
                self._access_token = ""
                self._expires_at = 0.0
                raise GoogleAccountError("The Google connection needs to be renewed in Settings.")
            if response.status_code == 403:
                # The connection predates sending being added, so the token
                # simply does not carry the scope yet.
                raise GoogleAccountError(
                    "Sending is not part of the current Google connection. Reconnect Google in Settings to allow it."
                )
            if response.is_error:
                raise GoogleAccountError("Google refused the request.")
            body = response.json()
            return body if isinstance(body, dict) else {}
        except GoogleAccountError:
            raise
        except Exception as exc:
            raise GoogleAccountError("Google could not be reached. Check the internet connection and try again.") from exc

    async def send_message(self, to: list[str], subject: str, body: str) -> str:
        """Send a plain-text message as the connected account.

        Returns the Gmail message id. Raises GoogleAccountError if the message
        was not accepted — never report a send that did not happen.
        """
        if not to:
            raise GoogleAccountError("No recipient was given.")
        message = EmailMessage()
        message["To"] = ", ".join(to)
        message["Subject"] = subject
        message.set_content(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        payload = await self._post(f"{GMAIL_API}/users/me/messages/send", {"raw": raw})
        message_id = str(payload.get("id", "")).strip()
        if not message_id:
            raise GoogleAccountError("Gmail did not confirm the message was sent.")
        return message_id

    async def upcoming_events(self, hours: int = 24, limit: int = 8) -> list[dict[str, str]]:
        now = datetime.now(timezone.utc)
        payload = await self._get(
            f"{CALENDAR_API}/calendars/primary/events",
            {
                "timeMin": now.isoformat().replace("+00:00", "Z"),
                "timeMax": (now + timedelta(hours=max(1, min(hours, 168)))).isoformat().replace("+00:00", "Z"),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": max(1, min(limit, 20)),
            },
        )
        events: list[dict[str, str]] = []
        for item in payload.get("items", []):
            if not isinstance(item, dict) or item.get("status") == "cancelled":
                continue
            start = item.get("start") if isinstance(item.get("start"), dict) else {}
            events.append({
                "summary": str(item.get("summary") or "Busy")[:200],
                "start": str(start.get("dateTime") or start.get("date") or "")[:64],
                "location": str(item.get("location") or "")[:200],
            })
        return events

    async def unread_messages(self, limit: int = 5) -> list[dict[str, str]]:
        payload = await self._get(
            f"{GMAIL_API}/users/me/messages",
            {"labelIds": "UNREAD", "maxResults": max(1, min(limit, 10))},
        )
        messages: list[dict[str, str]] = []
        for item in payload.get("messages", []):
            if not isinstance(item, dict):
                continue
            message_id = str(item.get("id", ""))
            if not message_id or len(message_id) > 256:
                continue
            detail = await self._get(
                f"{GMAIL_API}/users/me/messages/{quote(message_id, safe='')}",
                {"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
            )
            headers = detail.get("payload", {}).get("headers", []) if isinstance(detail.get("payload"), dict) else []
            values = {
                str(header.get("name", "")).casefold(): str(header.get("value", ""))
                for header in headers
                if isinstance(header, dict)
            }
            messages.append({
                "from": values.get("from", "Unknown sender")[:240],
                "subject": values.get("subject", "No subject")[:240],
                "date": values.get("date", "")[:160],
            })
        return messages


def format_google_calendar_for_voice(events: list[dict[str, str]], language: str = "en") -> str:
    german = language == "de"
    if not events:
        return "Ihr Google Kalender hat in den nächsten 24 Stunden keine Termine." if german else "Your Google Calendar has no events in the next 24 hours, sir."
    parts = []
    for event in events[:5]:
        start = event.get("start", "")
        label = event.get("summary", "Busy")
        parts.append(f"{label} um {start}" if german and start else f"{label} at {start}" if start else label)
    return ("Google Kalender: " if german else "Google Calendar: ") + "; ".join(parts) + "."


def format_google_mail_for_voice(messages: list[dict[str, str]], language: str = "en") -> str:
    german = language == "de"
    if not messages:
        return "Keine ungelesenen Gmail-Nachrichten." if german else "No unread Gmail messages, sir."
    if german:
        parts = [f"{message.get('subject', 'Ohne Betreff')} von {message.get('from', 'Unbekannter Absender')}" for message in messages[:5]]
        return f"{len(messages)} ungelesene Gmail-{'Nachricht' if len(messages) == 1 else 'Nachrichten'}: " + "; ".join(parts) + "."
    parts = [f"{message.get('subject', 'No subject')} from {message.get('from', 'Unknown sender')}" for message in messages[:5]]
    return f"{len(messages)} unread Gmail message{'s' if len(messages) != 1 else ''}: " + "; ".join(parts) + "."
