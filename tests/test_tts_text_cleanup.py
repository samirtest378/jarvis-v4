"""Spoken replies contain prose, never renderer or action syntax."""

import server


def test_tts_cleanup_keeps_normal_complete_sentences() -> None:
    text = "**Erledigt.**\n\nDer Kalender ist bereit."
    assert server.strip_markdown_for_tts(text) == "Erledigt. Der Kalender ist bereit."


def test_tts_cleanup_removes_links_code_emoji_and_private_actions() -> None:
    text = (
        "Details unter [Support](https://example.com/tickets?id=42) ✅\n"
        "Status: `bereit` [ACTION:READ_WEB] https://example.com"
    )
    assert server.strip_markdown_for_tts(text) == "Details unter Support Status: bereit."


def test_tts_cleanup_adds_a_final_pause_without_mangling_prose() -> None:
    assert server.strip_markdown_for_tts("Natürlich kann ich das prüfen") == (
        "Natürlich kann ich das prüfen."
    )
