"""Security boundary tests for the loopback desktop backend."""

from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

import server


def _auth_headers(**extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {server.JARVIS_AUTH_TOKEN}", **extra}


def test_backend_accepts_only_loopback_host_and_same_origin():
    assert server._is_allowed_authority("127.0.0.1:8340") is True
    assert server._is_allowed_authority("localhost:8340") is True
    assert server._is_allowed_authority("[::1]:8340") is True
    assert server._is_allowed_authority("evil.example:8340") is False
    assert server._is_allowed_authority("user@127.0.0.1:8340") is False
    assert server._is_trusted_origin(
        "http://127.0.0.1:8340",
        "127.0.0.1:8340",
    ) is True
    assert server._is_trusted_origin(
        "https://evil.example",
        "127.0.0.1:8340",
    ) is False


def test_private_api_requires_token_and_rejects_foreign_browser_origin():
    client = TestClient(server.app, base_url="http://127.0.0.1")

    assert client.get("/api/health").status_code == 200
    assert client.get("/api/usage").status_code == 401
    assert client.get("/api/usage", headers=_auth_headers()).status_code == 200
    assert client.get(
        "/api/usage",
        headers=_auth_headers(Origin="https://evil.example"),
    ).status_code == 403
    assert client.get(
        "/api/usage",
        headers=_auth_headers(Host="evil.example"),
    ).status_code == 400


def test_api_responses_are_private_and_browser_surface_is_hardened():
    client = TestClient(server.app, base_url="http://127.0.0.1")
    response = client.get("/api/usage", headers=_auth_headers())

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cross-origin-opener-policy"] == "same-origin"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.get("/docs", headers=_auth_headers()).status_code == 404
    assert client.get("/openapi.json", headers=_auth_headers()).status_code == 404


def test_oversized_http_and_model_inputs_are_rejected_early():
    client = TestClient(server.app, base_url="http://127.0.0.1")
    response = client.post(
        "/api/settings/test-llm",
        headers=_auth_headers(**{"Content-Length": str(server._MAX_REQUEST_BODY_BYTES + 1)}),
        content=b"{}",
    )
    assert response.status_code == 413

    with pytest.raises(ValidationError):
        server.TaskRequest(prompt="x" * 8001)
    with pytest.raises(ValidationError):
        server.KeyUpdate(key_name="OPENAI_API_KEY", key_value="x" * 16385)
