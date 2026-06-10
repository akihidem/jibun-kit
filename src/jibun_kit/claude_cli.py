"""ローカル ``claude -p`` 呼び出しの共有ヘルパー。

個人データの egress（外部送信）はこのモジュール経由のみ。呼び出し側は
人間の明示同意を得てから使うこと（``build`` は ``--with-claude`` フラグ、
``app`` は対話中の y/N 確認）。テストはこのモジュールを monkeypatch する。
"""

from __future__ import annotations

import shutil
import subprocess

DEFAULT_TIMEOUT = 600


class ClaudeError(RuntimeError):
    """claude CLI の実行失敗。``returncode=None`` は spawn / timeout 失敗。"""

    def __init__(self, message: str, *, returncode: int | None = None, stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


def find_claude() -> str | None:
    """PATH 上の claude CLI を探す（無ければ None）。"""
    return shutil.which("claude")


def run_claude(prompt_input: str, *, timeout: int = DEFAULT_TIMEOUT,
               claude_path: str | None = None) -> str:
    """``claude -p`` に stdin で渡し、stdout を返す。

    spawn / timeout 失敗 → ``ClaudeError(returncode=None)``、
    非ゼロ終了 → ``ClaudeError(returncode=N, stderr=...)``。
    """
    claude = claude_path or find_claude()
    if not claude:
        raise ClaudeError("`claude` が PATH にありません", returncode=None)
    try:
        result = subprocess.run(
            [claude, "-p"], input=prompt_input, capture_output=True, text=True,
            timeout=timeout,
        )
    except Exception as e:
        raise ClaudeError(f"claude 実行に失敗: {e}", returncode=None) from e
    if result.returncode != 0:
        raise ClaudeError(f"claude returned {result.returncode}",
                          returncode=result.returncode, stderr=result.stderr)
    return result.stdout
