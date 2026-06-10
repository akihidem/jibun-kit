"""Act 2 — インタビュー。回答そのものが新しいデータソース（自己申告）になる。

記録の正本は progress（state.py）。session md は回答のたびに
:func:`jibun_kit.common.write_session_md` で全再生成する — 1 回の ``write_text``
なのでディスク上のファイルは常に完成形（crash-safe）。
``build.collect_sources`` は ``data/**/*.md`` を拾うので、interview は
自動的に context bundle へ合流する。

claude による追い質問はハイブリッドの任意機能: PATH に claude があり、
本人が egress に同意したときだけ。生成した質問自体も progress に永続化し、
再開時に再生成（= 再送信）しない。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from jibun_kit import claude_cli
from jibun_kit.app.prompter import Prompter, confirm_egress
from jibun_kit.app.questions import QUESTIONS
from jibun_kit.app.state import Answer, Progress
from jibun_kit.common import append_index, data_dir, write_session_md
from jibun_kit.workspace import Workspace

_Q_LINE = re.compile(r"^\s*Q[:：]\s*(.+)$")
_MAX_FOLLOWUPS = 3

_FOLLOWUP_PROMPT = """\
あなたは自己理解インタビューの聞き手。以下は本人への質問とその回答。
回答を踏まえて、自己理解を深めるための追い質問を 2〜3 個、日本語で出すこと。

出力規則（厳守）:
- 各質問は「Q: 」で始まる 1 行にする
- 前置き・番号・JSON・コードフェンスは書かない
- 本人が答えやすい、具体的で開かれた質問にする

# ここまでの回答
"""


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def session_md_path(ws: Workspace, date: str) -> Path:
    """同日の既存セッションを壊さない interview md パスを決める（``.2.md`` 連番）。"""
    d = data_dir(ws, "interview", date)
    base = d / f"{date}-interview.md"
    if not base.exists():
        return base
    n = 2
    while (d / f"{date}-interview.{n}.md").exists():
        n += 1
    return d / f"{date}-interview.{n}.md"


def rewrite_session_md(ws: Workspace, progress: Progress) -> Path:
    """progress を正として session md を全再生成する。"""
    path = ws.root / progress.session_md
    messages: list[tuple[str, str]] = []
    for a in progress.answers:
        mark = ", claude生成" if a.claude_generated else ""
        parts = [f"**Q ({a.id}{mark}): {a.question}**"]
        if a.section:
            parts.append(f"<!-- maps: {a.section} -->")
        parts += ["", a.text]
        messages.append((a.ts, "\n".join(parts)))
    header = {
        "title": f"interview {progress.date}",
        "date": progress.date,
        "source-id": f"interview-{progress.date}",
        "questions": str(len(progress.answers)),
    }
    write_session_md(path, header, messages)
    return path


def _record(ws: Workspace, progress: Progress) -> None:
    """回答 1 件ごとの永続化: session md 再生成 + index 追記（dedup される）。"""
    if not progress.session_md:
        path = session_md_path(ws, progress.date)
        progress.session_md = str(path.relative_to(ws.root))
    path = rewrite_session_md(ws, progress)
    # 件数を含めない行にする（append_index の完全一致 dedup を活かし、1 行に保つ）
    append_index(ws, "interview", f"- {progress.date} / interview / file={path.name}")


def run_act2(prompter: Prompter, ws: Workspace, progress: Progress, save) -> None:
    """組み込み質問 → （任意で）claude 追い質問。``save`` は progress 保存コールバック。"""
    prompter.say("\n=== Act 2: インタビュー ===")
    prompter.say("あなた自身に少し質問します。回答はそのまま jibun.md の素材（自己申告データ）に"
                 "なります。\nスキップは空のまま Enter。Ctrl-C でいつでも中断でき、次回続きから再開します。")
    if progress.session_md:
        prompter.say("（再開モード: 回答ファイルは app が再生成します。"
                     "手動で編集する場合は build の前に行ってください）")
    answered = progress.answered_ids()
    pending = [q for q in QUESTIONS if q.id not in answered]
    total = len(QUESTIONS)
    for q in pending:
        n = len(progress.answered_ids()) + 1
        text = prompter.ask(f"\nQ {n}/{total}: {q.text}", multiline=True)
        if not text:
            progress.skipped.append(q.id)
        else:
            progress.answers.append(Answer(id=q.id, ts=_now_iso(), question=q.text,
                                           text=text, section=q.section))
            _record(ws, progress)
        save()

    _maybe_claude_followups(prompter, ws, progress, save)

    if progress.answers:
        prompter.say(f"\nインタビューを記録しました: {progress.session_md}"
                     f"（回答 {len(progress.answers)} 件）")
    else:
        prompter.say("\n回答はありませんでした（全部スキップでも大丈夫、いつでも再開できます）。")


def _maybe_claude_followups(prompter: Prompter, ws: Workspace, progress: Progress,
                            save) -> None:
    if not progress.answers:
        return
    followups = list(progress.claude_followups)
    if not followups:
        # 新規生成は claude があり、かつ本人が egress に同意したときだけ
        if not claude_cli.find_claude():
            return
        if not confirm_egress(
                prompter,
                f"ここまでの回答 {len(progress.answers)} 件を送り、追い質問を 2〜3 個生成します"):
            return
        prompter.say("追い質問を生成中 ...")
        qa = "\n\n".join(f"Q: {a.question}\nA: {a.text}" for a in progress.answers)
        try:
            out = claude_cli.run_claude(_FOLLOWUP_PROMPT + qa)
        except claude_cli.ClaudeError as e:
            prompter.say(f"生成に失敗しました（{e}）。追い質問はスキップします。")
            return
        texts = [m.group(1).strip() for ln in out.splitlines() if (m := _Q_LINE.match(ln))]
        texts = texts[:_MAX_FOLLOWUPS]
        if not texts:
            prompter.say("追い質問は生成されませんでした。")
            return
        followups = [{"id": f"claude-{i}", "text": t} for i, t in enumerate(texts, start=1)]
        progress.claude_followups = followups
        save()  # 質問自体を永続化（再開時に再生成 = 再送信しない）

    answered = progress.answered_ids()
    for f in followups:
        if f["id"] in answered:
            continue
        text = prompter.ask(f"\n（追い質問）{f['text']}", multiline=True)
        if not text:
            progress.skipped.append(f["id"])
        else:
            progress.answers.append(Answer(id=f["id"], ts=_now_iso(), question=f["text"],
                                           text=text, section="§2", claude_generated=True))
            _record(ws, progress)
        save()
