"""The language of each request must determine the language of its answer."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import memory
import server


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Wie geht es dir heute?", "de"),
        ("Kannst du mir bitte helfen?", "de"),
        ("Öffne meine E-Mail.", "de"),
        ('Was bedeutet "How are you doing today?"', "de"),
        ("Bitte erkläre den API response auf Deutsch.", "de"),
        ("How are you today?", "en"),
        ("Can you help me please?", "en"),
        ("Open my email.", "en"),
        ('What does "Wie geht es dir heute?" mean?', "en"),
        ("Bitte erkläre den API response in English.", "en"),
    ],
)
def test_turn_language_detects_short_natural_questions(text, expected):
    assert server.detect_turn_language(text) == expected


def test_missing_key_message_also_follows_the_current_turn_language():
    assert server.missing_language_model_reply("Wie ist dein Status?").startswith(
        "Es ist noch kein Sprachmodell-Schlüssel"
    )


def test_fast_task_and_usage_summaries_follow_the_turn_language(monkeypatch):
    tasks = [{"title": "Rechnung prüfen", "priority": "high", "due_date": "2026-08-02"}]
    assert memory.format_tasks_for_voice(tasks, "de").startswith("Eine Aufgabe")
    assert memory.format_tasks_for_voice(tasks, "en").startswith("One task")

    monkeypatch.setattr(server, "_session_start", server.time.time() - 120)
    monkeypatch.setattr(server, "_session_tokens", {"input": 0, "output": 0, "api_calls": 2, "tts_calls": 0})
    monkeypatch.setattr(server, "_get_usage_for_period", lambda _seconds: {
        "input_tokens": 0,
        "output_tokens": 0,
        "api_calls": 2,
        "tts_calls": 0,
    })
    assert server.get_usage_summary("de").startswith("Diese Sitzung")
    assert server.get_usage_summary("en").startswith("This session")
    assert server.missing_language_model_reply("What is your status?").startswith(
        "No language-model key"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "opposite_history", "expected", "forbidden"),
    [
        ("Wie spät ist es?", "What time is it?", "GERMAN", "ENGLISH"),
        ("What time is it?", "Wie spät ist es?", "ENGLISH", "GERMAN"),
    ],
)
async def test_current_question_locks_response_language(
    monkeypatch, question, opposite_history, expected, forbidden
):
    captured = {}

    class FakeMessages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(text="ok")],
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )

    class FakeClient:
        messages = FakeMessages()

    class FakeTaskManager:
        @staticmethod
        def get_active_tasks_summary():
            return "No active tasks."

    monkeypatch.setattr(server, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(server, "build_memory_context", lambda _text: "")
    monkeypatch.setattr(server, "get_lookup_status", lambda: "")

    await server.generate_response(
        question,
        FakeClient(),
        FakeTaskManager(),
        [],
        [
            {"role": "user", "content": opposite_history},
            {"role": "assistant", "content": "Earlier answer"},
            {"role": "user", "content": question},
        ],
    )

    directive = captured["system"].split("CURRENT TURN LANGUAGE — HIGHEST PRIORITY:", 1)[1]
    assert directive.startswith(f" {expected}.")
    assert f"Answer this request entirely in natural {expected.title()}" in directive
    assert f"Do not switch to {forbidden.title()}" in directive


@pytest.mark.parametrize(
    ("draft", "expected", "conflicts"),
    [
        ("Das ist die richtige Antwort.", "de", False),
        ("That is the correct answer.", "de", True),
        ("That is the correct answer.", "en", False),
        ("Das ist die richtige Antwort.", "en", True),
        ("Ja.", "de", False),
        ("Done.", "en", False),
        ("Öffne YouTube. [ACTION:BROWSE] https://youtube.com", "de", False),
    ],
)
def test_response_language_guard_only_flags_clear_conflicts(draft, expected, conflicts):
    assert server.response_language_conflicts(draft, expected) is conflicts


@pytest.mark.asyncio
async def test_wrong_language_draft_is_repaired_once(monkeypatch):
    calls = []
    drafts = iter(("That answer is in the wrong language.", "Diese Antwort ist jetzt auf Deutsch."))

    class FakeMessages:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(text=next(drafts))],
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )

    class FakeClient:
        messages = FakeMessages()

    class FakeTaskManager:
        @staticmethod
        def get_active_tasks_summary():
            return "No active tasks."

    monkeypatch.setattr(server, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(server, "build_memory_context", lambda _text: "")
    monkeypatch.setattr(server, "get_lookup_status", lambda: "")

    answer = await server.generate_response(
        "Was ist die richtige Antwort?",
        FakeClient(),
        FakeTaskManager(),
        [],
        [{"role": "user", "content": "Was ist die richtige Antwort?"}],
    )

    assert answer == "Diese Antwort ist jetzt auf Deutsch."
    assert len(calls) == 2
    assert "LANGUAGE REPAIR" in calls[1]["system"]
