"""Spoken replies contain prose, never renderer or action syntax."""

import server


def test_tts_cleanup_keeps_normal_complete_sentences() -> None:
    text = "**Erledigt.**\n\nDer Kalender ist bereit."
    assert server.strip_markdown_for_tts(text) == "Erledigt\nDer Kalender ist bereit"


def test_tts_cleanup_removes_links_code_emoji_and_private_actions() -> None:
    text = (
        "Details unter [Support](https://example.com/tickets?id=42) ✅\n"
        "Status: `bereit` [ACTION:READ_WEB] https://example.com"
    )
    assert server.strip_markdown_for_tts(text) == "Details unter Support Status bereit"


def test_tts_cleanup_does_not_add_a_spoken_symbol() -> None:
    assert server.strip_markdown_for_tts("Natürlich kann ich das prüfen") == "Natürlich kann ich das prüfen"


def test_tts_cleanup_silences_requested_symbols_for_every_voice_provider() -> None:
    cleaned = server.strip_markdown_for_tts('. , : -- = ) ( / & % ç * " +')
    assert cleaned == ""
    assert not any(symbol in server.strip_markdown_for_tts("Status: 10% + bereit.") for symbol in ".,:=-)(/&%ç*\"+")
