"""Act 3 — 対話的 build & refine。

:func:`jibun_kit.build.prepare` で素材（prompt + context bundle）を組み、
claude 同意なしなら従来の貼り付け案内、同意ありなら draft 生成 →
セクション別レビュー → フィードバック改訂のループ。改訂時は方法論 prompt +
現ドラフト + フィードバックだけを送り、**bundle は再送しない**。

保存は明示確認のうえでのみ。既存の jibun.md（starter 以外）は
``_build/<date>/jibun.previous.md``（既にあれば ``jibun.previous.2.md`` …）に
退避してから上書きする。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from jibun_kit import build, claude_cli
from jibun_kit.app.prompter import Prompter, confirm_egress
from jibun_kit.scaffold import read_template
from jibun_kit.workspace import Workspace

# この回数を超えて改訂が続いたら一言入れる（続行は妨げない）
_NOTE_ROUNDS = 5


def run_act3(prompter: Prompter, cfg, ws: Workspace) -> int:
    prompter.say("\n=== Act 3: jibun.md のビルド ===")
    art = build.prepare(cfg, ws)
    if art is None:
        prompter.say("ingest 済みデータがまだありません。"
                     "先に Act 1（取り込み）か Act 2（インタビュー）をどうぞ。")
        return 2
    prompter.say(f"素材を組みました: {art.build_dir}"
                 f"（{art.total_bytes:,} bytes / {len(art.data_files)} files）")

    use_claude = False
    if claude_cli.find_claude():
        if art.total_bytes > build.BUNDLE_SIZE_NOTE_BYTES:
            prompter.say(f"note: bundle が大きめ（{art.total_bytes:,} bytes）。"
                         "claude の context に入らない可能性があります。")
        use_claude = confirm_egress(
            prompter,
            "ingest 済みデータ全体（context bundle）を送信して下書きを生成します"
            "（以降の改訂でもドラフトとあなたのコメントを送信します）")
    if not use_claude:
        _paste_instructions(prompter, ws, art)
        return 0
    return _interactive_refine(prompter, ws, art)


def _paste_instructions(prompter: Prompter, ws: Workspace, art) -> None:
    """従来 ``jibun build`` と同じ、自分の AI への貼り付け手順。"""
    prompter.say("\n次の手順で自分の AI に貼ってください:")
    prompter.say(f"  1. {art.build_dir / 'prompt.md'} と "
                 f"{art.build_dir / 'context-bundle.md'} を自分の AI（Claude 等）に渡す")
    prompter.say(f"  2. 出力を {ws.jibun_md} に保存（スターターの各セクションを置換）")
    prompter.say("  ※ 個人データが外部に出るのは、この貼り付けという人間の操作のときだけ。")


def _interactive_refine(prompter: Prompter, ws: Workspace, art) -> int:
    draft = _generate(prompter, ws, art, current_draft=None, feedback=None)
    if draft is None:
        return 0
    round_no = 1
    while True:
        feedback = _review_sections(prompter, draft)
        if feedback is None:
            prompter.say(f"レビューを中断しました。ドラフトは {art.build_dir} にあります。")
            return 0
        if not feedback:
            return _save_final(prompter, ws, art, draft)
        _log_feedback(art.build_dir, round_no, feedback)
        new_draft = _generate(prompter, ws, art, current_draft=draft, feedback=feedback)
        if new_draft is None:
            return 0
        draft = new_draft
        round_no += 1
        if round_no > _NOTE_ROUNDS:
            prompter.say(f"note: 改訂 {round_no - 1} 回目です。"
                         "いったん保存して寝かせるのも手です。")


def _generate(prompter: Prompter, ws: Workspace, art, *,
              current_draft: str | None, feedback) -> str | None:
    """draft の生成（初回）/ 改訂。None = ユーザーが中断（案内済み）。"""
    if current_draft is None:
        payload = (f"{art.prompt}\n\n"
                   "出力は jibun.md の本文のみ。前置き・後書きを書かず、"
                   "コードフェンスで囲まない。\n\n---\n\n"
                   f"{art.bundle}")
        prompter.say("\nclaude で下書きを生成中（数分かかることがあります）...")
    else:
        bullets = "\n".join(f"- {heading}: {comment}" for heading, comment in feedback)
        payload = (
            f"{art.prompt}\n\n---\n\n# 現在のドラフト\n\n{current_draft}"
            f"\n\n---\n\n# 本人からの修正フィードバック\n\n{bullets}"
            "\n\n---\n\n上記フィードバックを反映し、jibun.md の全文を再出力すること。"
            "フィードバックの無いセクションは変えない。前置きを書かず、"
            "コードフェンスで囲まない。"
        )
        prompter.say("\nフィードバックを反映して改訂中 ...")
    while True:
        try:
            out = claude_cli.run_claude(payload)
        except claude_cli.ClaudeError as e:
            prompter.say(f"claude の実行に失敗しました: {e}")
            idx = prompter.choose("どうしますか？",
                                  ["再試行", "貼り付けフローに切り替え", "中断"], default=0)
            if idx == 0:
                continue
            if idx == 1:
                _paste_instructions(prompter, ws, art)
            else:
                prompter.say(f"中断しました。素材とドラフトは {art.build_dir} にあります。")
            return None
        break
    if not _has_body(out):
        # 空・空白のみ・フェンスだけの出力を draft にすると jibun.md を空で上書きしうる
        prompter.say("claude の出力が空でした。ドラフトは作成しません"
                     f"（素材は {art.build_dir} にあります。時間をおいて再実行してください）。")
        return None
    draft = out.strip() + "\n"
    path = _next_draft_path(art.build_dir)
    path.write_text(draft, encoding="utf-8")
    prompter.say(f"draft 保存: {path}")
    return draft


def _has_body(out: str) -> bool:
    """コードフェンス行（```...）以外に中身が 1 行でもあれば True。"""
    return any(line.strip() and not line.strip().startswith("```")
               for line in out.splitlines())


def _split_sections(draft: str) -> list[str]:
    """``^## `` 見出しで分割。先頭要素は前文（タイトル+§0）。見出しが無ければ全文 1 块。"""
    return [s for s in re.split(r"(?m)^(?=## )", draft) if s.strip()]


def _review_sections(prompter: Prompter, draft: str):
    """セクション別レビュー。返り値: [(見出し, コメント)] / [] = 全部 OK / None = 中断。"""
    sections = _split_sections(draft)
    prompter.say(f"\nドラフトを {len(sections)} ブロックに分けて確認します。"
                 "気になる所は遠慮なくどうぞ（改訂は claude がやります）。")
    feedback: list[tuple[str, str]] = []
    for i, sec in enumerate(sections, start=1):
        heading = sec.strip().splitlines()[0]
        prompter.say(f"\n――― ブロック {i}/{len(sections)} ―――\n{sec.rstrip()}")
        idx = prompter.choose("このブロックはどうですか？",
                              ["OK（次へ）", "修正コメントを書く", "レビューを中断"],
                              default=0)
        if idx == 2:
            return None
        if idx == 1:
            comment = prompter.ask("修正してほしい点を教えてください", multiline=True)
            if comment:
                feedback.append((heading, comment))
    return feedback


def _log_feedback(build_dir: Path, round_no: int, feedback) -> None:
    log = build_dir / "feedback.md"
    header = "" if log.exists() else "# 対話ビルドのフィードバックログ\n\n"
    stamp = datetime.now().isoformat(timespec="seconds")
    lines = [f"## round {round_no} ({stamp})", ""]
    lines += [f"- {heading}: {comment}" for heading, comment in feedback]
    with log.open("a", encoding="utf-8") as f:
        f.write(header + "\n".join(lines) + "\n\n")


def _next_draft_path(build_dir: Path) -> Path:
    return _next_numbered_path(build_dir, "jibun.draft")


def _next_backup_path(build_dir: Path) -> Path:
    # 同日 2 回目以降の保存で前回の退避（＝本人の原本の可能性）を上書きしない
    return _next_numbered_path(build_dir, "jibun.previous")


def _next_numbered_path(build_dir: Path, stem: str) -> Path:
    """``<stem>.md`` → ``<stem>.2.md`` → … の未使用パス。"""
    base = build_dir / f"{stem}.md"
    if not base.exists():
        return base
    n = 2
    while (build_dir / f"{stem}.{n}.md").exists():
        n += 1
    return build_dir / f"{stem}.{n}.md"


def _save_final(prompter: Prompter, ws: Workspace, art, draft: str) -> int:
    target = ws.jibun_md
    if not prompter.confirm(f"{target} に保存します。既存の内容は上書きされます。よろしいですか？",
                            default=False):
        prompter.say(f"保存しませんでした。ドラフトは {art.build_dir} にあります"
                     "（納得したら手動で jibun.md へ昇格してください）。")
        return 0
    if target.exists():
        current = target.read_text(encoding="utf-8")
        if current != read_template("jibun.starter.md"):
            backup = _next_backup_path(art.build_dir)
            backup.write_text(current, encoding="utf-8")
            prompter.say(f"既存の jibun.md を退避しました: {backup}")
    target.write_text(draft, encoding="utf-8")
    prompter.say(f"✓ 保存しました: {target}")
    return 0
