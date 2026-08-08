"""Background work must be opt-in, so an idle install stays idle."""

from __future__ import annotations

import pytest

import server


@pytest.fixture
def no_opt_ins(monkeypatch):
    for name in (
        "JARVIS_BACKGROUND_SCREEN_CONTEXT",
        "JARVIS_WEATHER_LATITUDE",
        "JARVIS_WEATHER_LONGITUDE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_no_periodic_thread_on_a_default_install(no_opt_ins):
    assert server._background_context_needed() is False


def test_window_title_context_brings_the_thread_back(no_opt_ins, monkeypatch):
    monkeypatch.setattr(server.sys, "platform", "darwin")
    monkeypatch.setenv("JARVIS_BACKGROUND_SCREEN_CONTEXT", "1")
    assert server._background_context_needed() is True


def test_weather_needs_both_coordinates(no_opt_ins, monkeypatch):
    monkeypatch.setenv("JARVIS_WEATHER_LATITUDE", "47.39")
    assert server._background_context_needed() is False
    monkeypatch.setenv("JARVIS_WEATHER_LONGITUDE", "8.05")
    assert server._background_context_needed() is True
