import shutil
import subprocess

import pytest

from jibun_kit import claude_cli


def test_find_claude_none(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert claude_cli.find_claude() is None


def test_run_claude_success(monkeypatch):
    def fake_run(cmd, **kw):
        assert cmd == ["/fake/claude", "-p"]
        assert kw["input"] == "hello"
        return subprocess.CompletedProcess(cmd, 0, stdout="draft body", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert claude_cli.run_claude("hello", claude_path="/fake/claude") == "draft body"


def test_run_claude_nonzero_rc(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 3, stdout="", stderr="boom"))
    with pytest.raises(claude_cli.ClaudeError) as ei:
        claude_cli.run_claude("x", claude_path="/fake/claude")
    assert ei.value.returncode == 3
    assert ei.value.stderr == "boom"


def test_run_claude_timeout(monkeypatch):
    def fake_run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 1))

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(claude_cli.ClaudeError) as ei:
        claude_cli.run_claude("x", claude_path="/fake/claude")
    assert ei.value.returncode is None


def test_run_claude_oserror(monkeypatch):
    def fake_run(cmd, **kw):
        raise OSError("no exec")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(claude_cli.ClaudeError) as ei:
        claude_cli.run_claude("x", claude_path="/fake/claude")
    assert ei.value.returncode is None


def test_run_claude_without_cli(monkeypatch):
    monkeypatch.setattr(claude_cli, "find_claude", lambda: None)
    with pytest.raises(claude_cli.ClaudeError):
        claude_cli.run_claude("x")
