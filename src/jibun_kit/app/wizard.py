"""``jibun app`` のトップレベル進行（Act 0 → メニュー → Act 1/2/3）。

中断（Ctrl-C / EOF）はどこで起きても安全: 進捗は各 Act が回答・source 単位で
保存済みなので、ここでは案内だけ出して rc 130 で抜ける。
"""

from __future__ import annotations

import argparse
from datetime import datetime

from jibun_kit.app import act_build, act_interview, act_sources
from jibun_kit.app.prompter import Prompter, StdioPrompter
from jibun_kit.app.state import Progress, clear_progress, load_progress, save_progress
from jibun_kit.config import JibunConfig

_MENU = (
    "データの取り込み（source の提案を受ける）",
    "インタビューに答える（回答がそのまま素材になる）",
    "jibun.md をビルドする",
    "終了",
)


def run(args: argparse.Namespace, prompter: Prompter | None = None) -> int:
    prompter = prompter or StdioPrompter()
    try:
        return _run_wizard(prompter, getattr(args, "path", None))
    except (KeyboardInterrupt, EOFError):
        # 進捗は各 act が逐次 save 済み。ここでは案内だけ。
        print("\n\n進捗を保存しました。`jibun app` でいつでも続きから再開できます。")
        return 130


def _run_wizard(prompter: Prompter, cli_path) -> int:
    prompter.say("jibun app — 対話しながら、自己理解の 1 枚 jibun.md を作ります。")
    ws = act_sources.ensure_workspace(prompter, cli_path)
    if ws is None:
        prompter.say("中止しました。")
        return 0

    progress = load_progress(ws)
    if progress is not None:
        if not prompter.confirm(
                f"前回の続き（{progress.date} / 回答 {len(progress.answers)} 件）から再開しますか？",
                default=True):
            clear_progress(ws)
            progress = None
    if progress is None:
        progress = Progress(date=datetime.now().strftime("%Y-%m-%d"))

    def save() -> None:
        save_progress(ws, progress, now=datetime.now().isoformat(timespec="seconds"))

    while True:
        default = min(max(progress.act, 1), 3) - 1
        idx = prompter.choose("\n何をしますか？", _MENU, default=default)
        if idx == 0:
            progress.act = 1
            save()
            act_sources.run_act1(prompter, ws, progress.act1_done, save)
            progress.act = 2
            save()
        elif idx == 1:
            progress.act = 2
            save()
            act_interview.run_act2(prompter, ws, progress, save)
            progress.act = 3
            save()
        elif idx == 2:
            progress.act = 3
            save()
            try:
                cfg = JibunConfig.load(ws.config_path)  # Act 1 の toml 更新を反映
            except ValueError as e:  # 手編集で壊れた toml（TOMLDecodeError）
                prompter.say(f"jibun.toml を読めませんでした（{e}）。"
                             "jibun.toml を直接編集して直してから、もう一度選んでください。")
                continue
            act_build.run_act3(prompter, cfg, ws)
        else:
            prompter.say("おつかれさまでした。`jibun app` でいつでも続きができます。")
            return 0
