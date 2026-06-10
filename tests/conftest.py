"""Shared pytest fixtures.

The payoff of de-globalizing common.py: tests inject a tmp workspace, so nothing
touches the real ~/Projects/jibun or needs $JIBUN_ROOT.
"""

from collections import deque

import pytest

from jibun_kit.workspace import Workspace


@pytest.fixture
def tmp_workspace(tmp_path):
    ws = Workspace(tmp_path)
    ws.data_root.mkdir(parents=True, exist_ok=True)
    ws.sources_root.mkdir(parents=True, exist_ok=True)
    return ws


# --- jibun app 用: 台本駆動の Prompter ---

# script に混ぜると、その対話の瞬間に KeyboardInterrupt を起こす（Ctrl-C 模擬）
RAISE_INTERRUPT = object()


class ScriptedPrompter:
    """事前に並べた回答を順に消費する Prompter 実装（テスト専用）。

    - ask: str を返す（None は「空 Enter」= default 採用）
    - confirm: bool
    - choose: int（0-based）または option 文言の部分一致 str
    台本が枯渇したら transcript 付きで AssertionError。
    """

    def __init__(self, script):
        self.script = deque(script)
        self.transcript: list[str] = []

    def _next(self, kind: str, prompt: str):
        self.transcript.append(f"[{kind}] {prompt}")
        if not self.script:
            raise AssertionError(
                f"ScriptedPrompter の台本が枯渇しました: [{kind}] {prompt}\n"
                "--- transcript ---\n" + "\n".join(self.transcript))
        item = self.script.popleft()
        if item is RAISE_INTERRUPT:
            raise KeyboardInterrupt
        return item

    def say(self, text: str) -> None:
        self.transcript.append(f"[say] {text}")

    def said(self) -> str:
        """これまでの say 全文（アサーション用）。"""
        return "\n".join(t for t in self.transcript if t.startswith("[say] "))

    def ask(self, prompt: str, *, default: str = "", multiline: bool = False) -> str:
        item = self._next("ask", prompt)
        if item is None:
            return default
        return str(item) or default

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        item = self._next("confirm", prompt)
        if item is None:
            return default
        assert isinstance(item, bool), f"confirm への台本は bool であること: {item!r}"
        return item

    def choose(self, prompt: str, options, *, default: int = 0) -> int:
        item = self._next("choose", f"{prompt} {list(options)}")
        if item is None:
            return default
        if isinstance(item, int):
            return item
        matches = [i for i, opt in enumerate(options) if str(item) in opt]
        assert matches, f"choose の台本 {item!r} がどの option にも一致しない: {list(options)}"
        return matches[0]
