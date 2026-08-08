"""Browser launch mode stays visible for users and safe in build environments."""

import browser


def test_browser_is_headless_in_ci(monkeypatch):
    monkeypatch.setenv("CI", "true")
    monkeypatch.delenv("JARVIS_BROWSER_HEADLESS", raising=False)

    assert browser._launch_headless() is True


def test_browser_headless_mode_can_be_overridden(monkeypatch):
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("JARVIS_BROWSER_HEADLESS", "false")

    assert browser._launch_headless() is False
