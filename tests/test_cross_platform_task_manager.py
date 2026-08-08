from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import server


class _CompletedClaude:
    pid = 4242
    returncode = 0

    def __init__(self, captured: dict):
        self.captured = captured

    async def communicate(self, payload: bytes):
        self.captured["stdin"] = payload
        return b"Built and verified the project.", b""


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["darwin", "win32", "linux"])
async def test_background_project_tasks_use_one_safe_cross_platform_cli_path(monkeypatch, tmp_path: Path, platform):
    captured = {}
    manager = server.ClaudeTaskManager()
    task = server.ClaudeTask(id="task-1", prompt='Build this; echo "unsafe"', working_dir=str(tmp_path))

    async def fake_exec(executable, *args, **kwargs):
        captured.update(executable=executable, args=args, kwargs=kwargs)
        return _CompletedClaude(captured)

    async def no_qa(*_args, **_kwargs):
        return None

    monkeypatch.setattr(server.sys, "platform", platform)
    monkeypatch.setattr(server.shutil, "which", lambda name: "/safe/claude" if name == "claude" else None)
    monkeypatch.setattr(server.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(manager, "_run_qa", no_qa)

    await manager._run_task(task)
    await asyncio.sleep(0)

    assert task.status == "completed"
    assert task.result == "Built and verified the project."
    assert captured["executable"] == "/safe/claude"
    assert captured["args"] == ("-p",)
    assert captured["kwargs"]["cwd"] == str(tmp_path)
    assert "shell" not in captured["kwargs"]
    assert captured["stdin"] == task.prompt.encode("utf-8")
    assert (tmp_path / ".jarvis_output.txt").read_text(encoding="utf-8") == task.result


@pytest.mark.asyncio
async def test_background_project_task_without_cli_fails_honestly(monkeypatch, tmp_path: Path):
    manager = server.ClaudeTaskManager()
    task = server.ClaudeTask(id="task-2", prompt="Build it", working_dir=str(tmp_path))
    monkeypatch.setattr(server.shutil, "which", lambda _name: None)

    await manager._run_task(task)

    assert task.status == "failed"
    assert "not installed" in task.error
    assert task.completed_at is not None
