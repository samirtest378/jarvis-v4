"""Commands that must be answered without spending a model call."""

from __future__ import annotations

import pytest

import server


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Öffne YouTube", "https://www.youtube.com"),
        ("öffne youtube", "https://www.youtube.com"),
        ("Open YouTube", "https://www.youtube.com"),
        ("starte netflix", "https://www.netflix.com"),
        ("Öffne GitHub.", "https://github.com"),
    ],
)
def test_known_sites_resolve_without_a_model(text, expected):
    command = server.resolve_direct_command(text)
    assert command is not None
    assert command["kind"] == "site"
    assert command["target"] == expected


@pytest.mark.parametrize("text", ["Öffne Spotify", "open spotify", "starte Mail"])
def test_allow_listed_applications_resolve(text):
    command = server.resolve_direct_command(text)
    assert command is not None
    assert command["kind"] == "app"


@pytest.mark.parametrize(
    "text",
    ["Zeig meinen Kalender", "was steht heute an", "show my calendar", "my schedule today"],
)
def test_calendar_phrases_resolve(text):
    assert server.resolve_direct_command(text)["kind"] == "calendar"


@pytest.mark.parametrize(
    "text",
    [
        "meine mails",
        "check my mail",
        "neue e-mails",
        "Öffne meine Email",
        "Öffne meine E-Mail",
        "Öffne mein Postfach",
        "Open my email",
        "Open my inbox",
    ],
)
def test_mail_phrases_resolve(text):
    assert server.resolve_direct_command(text)["kind"] == "mail"


@pytest.mark.parametrize(
    "text",
    [
        # Needs judgement, planning, or writing — must reach the model.
        "Was ist die Hauptstadt von Australien?",
        "Fasse meine Mails von heute zusammen",
        "Plane meinen Tag",
        "Schreib eine E-Mail an meinen Chef",
        "Öffne das Projekt an dem ich gestern gearbeitet habe",
        # Unknown target: guessing a URL would be worse than asking the model.
        "Öffne Zwiebelfisch",
        "open my weird internal tool",
        # Not a command at all.
        "youtube",
        "",
        "   ",
    ],
)
def test_anything_ambiguous_still_goes_to_the_model(text):
    assert server.resolve_direct_command(text) is None


def test_absurdly_long_input_is_never_treated_as_a_direct_command():
    assert server.resolve_direct_command("öffne " + "x" * 200) is None


def test_replies_follow_the_language_of_the_command(monkeypatch):
    monkeypatch.setattr(server, "USER_NAME", "sir")
    german = server.resolve_direct_command("Öffne YouTube")
    english = server.resolve_direct_command("Open YouTube")

    assert server.direct_command_reply(german).startswith("Öffne Youtube")
    assert server.direct_command_reply(english).startswith("Opening Youtube")
    assert server.direct_command_reply({"kind": "calendar", "german": True}) == "Ich sehe im Kalender nach."
    assert server.direct_command_reply({"kind": "calendar", "german": False}) == "Checking your calendar."


def test_articles_are_ignored_so_natural_phrasing_works():
    assert server.resolve_direct_command("open the calendar")["kind"] == "app"
    assert server.resolve_direct_command("öffne mein Spotify")["kind"] == "app"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hallo!", "Hallo — ich bin bereit."),
        ("Vielen Dank.", "Gern."),
        ("Wie geht es dir?", "Bestens — bereit, wenn Sie es sind."),
        ("Kannst du Deutsch?", "Ja. Ich verstehe und antworte auf Deutsch."),
        ("Hello!", "Hello — ready when you are."),
        ("Thank you.", "You’re welcome."),
        ("Are you ready?", "Yes — ready."),
        ("Do you speak German?", "Yes. I understand and reply in German."),
    ],
)
def test_tiny_social_turns_have_an_instant_bilingual_reply(text, expected):
    assert server.instant_conversation_reply(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Hallo, kannst du mir etwas erklären?",
        "Danke, aber das war nicht meine Frage.",
        "How are you able to access my calendar?",
        "Are you ready to explain quantum mechanics?",
    ],
)
def test_substantive_conversation_always_reaches_the_language_model(text):
    assert server.instant_conversation_reply(text) is None
