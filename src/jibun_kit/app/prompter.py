"""UI 非依存の対話抽象。

wizard / 各 Act は ``Prompter`` だけに依存する（``print``/``input`` を直接呼ばない）。
ターミナル実装は :class:`StdioPrompter`。テストは ScriptedPrompter
（``tests/conftest.py``）を注入する。将来 Web UI を被せるときも
この protocol を実装すればよい。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

_YES = {"y", "yes", "はい"}
_NO = {"n", "no", "いいえ"}


class Prompter(Protocol):
    def say(self, text: str) -> None: ...

    def ask(self, prompt: str, *, default: str = "", multiline: bool = False) -> str: ...

    def confirm(self, prompt: str, *, default: bool = False) -> bool: ...

    def choose(self, prompt: str, options: Sequence[str], *, default: int = 0) -> int: ...


class StdioPrompter:
    """標準入出力の :class:`Prompter` 実装。"""

    def say(self, text: str) -> None:
        print(text)

    def ask(self, prompt: str, *, default: str = "", multiline: bool = False) -> str:
        if multiline:
            print(prompt)
            print("  （複数行 OK。空行で確定）")
            lines: list[str] = []
            while True:
                line = input("> " if not lines else "  ")
                if line == "":
                    break
                lines.append(line)
            return "\n".join(lines).strip() or default
        suffix = f" [{default}]" if default else ""
        return input(f"{prompt}{suffix}\n> ").strip() or default

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        suffix = "[Y/n]" if default else "[y/N]"
        while True:
            answer = input(f"{prompt} {suffix}\n> ").strip().lower()
            if not answer:
                return default
            if answer in _YES:
                return True
            if answer in _NO:
                return False
            print("  y / n で答えてください。")

    def choose(self, prompt: str, options: Sequence[str], *, default: int = 0) -> int:
        print(prompt)
        for i, opt in enumerate(options, start=1):
            mark = "*" if (i - 1) == default else " "
            print(f" {mark}{i}) {opt}")
        while True:
            answer = input(f"番号を選択 [{default + 1}]\n> ").strip()
            if not answer:
                return default
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                return int(answer) - 1
            print(f"  1〜{len(options)} の番号で答えてください。")


def confirm_egress(prompter: Prompter, what: str) -> bool:
    """外部送信（egress）の明示同意。既定 No。

    kit の原則: 個人データが PC の外に出るのは人間が明示に同意したときだけ。
    送る内容（what）を必ず具体的に書いて呼ぶこと。
    """
    prompter.say(f"\n⚠ 外部送信の確認: {what}。")
    return prompter.confirm(
        "ローカルの claude CLI 経由で Anthropic に送信されます。実行しますか？",
        default=False)
