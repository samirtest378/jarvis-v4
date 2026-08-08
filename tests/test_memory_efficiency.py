"""Memory learning must not compete with ordinary conversation."""

from __future__ import annotations

import pytest

import memory


@pytest.mark.parametrize(
    "text",
    [
        "Warum ist der Himmel blau?",
        "Was ist zwei plus zwei?",
        "Explain quantum computing in one sentence.",
        "Nenne die Hauptstadt von Kanada.",
        "Öffne bitte YouTube.",
    ],
)
def test_normal_questions_do_not_trigger_a_second_model_call(text):
    assert memory.should_extract_memories(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "Mein Name ist Sahid.",
        "Ich bevorzuge kurze Antworten.",
        "Mein Ziel ist eine sehr schnelle App.",
        "My name is Sahid.",
        "I prefer concise answers.",
        "I am working on JARVIS v4.",
    ],
)
def test_durable_personal_facts_can_be_learned_when_idle(text):
    assert memory.should_extract_memories(text) is True


@pytest.mark.asyncio
async def test_irrelevant_turn_skips_provider_entirely():
    class ProviderThatMustNotRun:
        class messages:
            @staticmethod
            async def create(**_kwargs):
                raise AssertionError("ordinary chat must not launch memory extraction")

    result = await memory.extract_memories(
        "Was ist zwei plus zwei?",
        "Zwei plus zwei ist vier.",
        ProviderThatMustNotRun(),
    )

    assert result == []


def test_duplicate_memories_are_strengthened_instead_of_repeated(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "memory.db")
    memory.init_db()

    first = memory.remember("Ich bevorzuge kurze Antworten.", "preference", importance=5)
    second = memory.remember("  ich bevorzuge kurze Antworten  ", "preference", importance=8)

    assert first == second
    stored = memory.get_recent_memories()
    assert len(stored) == 1
    assert stored[0]["importance"] == 8


def test_memory_context_excludes_unrelated_facts_and_tasks(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "memory.db")
    memory.init_db()
    memory.remember("Mein Lieblingseditor ist Visual Studio Code.", "preference", importance=10)
    memory.create_task("Steuerunterlagen sortieren", priority="high")

    assert memory.build_memory_context("Warum ist der Himmel blau?") == ""
    relevant = memory.build_memory_context("Welchen Editor bevorzuge ich?")
    assert "Visual Studio Code" in relevant
    assert "Steuerunterlagen" not in relevant
