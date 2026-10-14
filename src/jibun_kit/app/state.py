"""``jibun app`` の進捗状態（resume 用）。

``data/interview/.progress.json`` に保存する（``data/`` 配下なので gitignore 済み）。
正本はこの progress（回答本文を含む）。インタビューの session md は
毎回ここから全再生成する — ファイルは常に完成形なので crash-safe。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from jibun_kit.workspace import Workspace

VERSION = 1


@dataclass
class Answer:
    id: str
    ts: str                        # ISO 8601
    question: str                  # md 再生成用に質問文も保持
    text: str
    section: str = ""
    claude_generated: bool = False


@dataclass
class Progress:
    version: int = VERSION
    date: str = ""                 # セッション開始日 YYYY-MM-DD
    act: int = 1
    session_md: str = ""           # workspace root からの相対パス
    answers: list[Answer] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    claude_followups: list[dict] = field(default_factory=list)  # [{"id", "text"}]
    act1_done: list[str] = field(default_factory=list)
    updated: str = ""

    def answered_ids(self) -> set[str]:
        return {a.id for a in self.answers} | set(self.skipped)


def progress_path(ws: Workspace) -> Path:
    return ws.data_root / "interview" / ".progress.json"


def load_progress(ws: Workspace) -> Progress | None:
    """保存済み progress を読む。無い・壊れている・version 不一致なら None。"""
    p = progress_path(ws)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("version") != VERSION:
        return None
    fields = {f for f in Answer.__dataclass_fields__}
    try:
        answers = [Answer(**{k: v for k, v in a.items() if k in fields})
                   for a in data.get("answers", []) if isinstance(a, dict)]
        return Progress(
            version=VERSION,
            date=data.get("date", ""),
            act=int(data.get("act", 1)),
            session_md=data.get("session_md", ""),
            answers=answers,
            skipped=list(data.get("skipped", [])),
            claude_followups=list(data.get("claude_followups", [])),
            act1_done=list(data.get("act1_done", [])),
            updated=data.get("updated", ""),
        )
    except (TypeError, ValueError):
        # 必須キー欠落の answer や "act": "x" / null など、手で壊れた progress は「無い」扱い
        return None


def save_progress(ws: Workspace, progress: Progress, *, now: str) -> None:
    """atomic に保存（tmp に書いて os.replace）。``now`` は ISO 8601。"""
    progress.updated = now
    path = progress_path(ws)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(asdict(progress), ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, path)


def clear_progress(ws: Workspace) -> None:
    progress_path(ws).unlink(missing_ok=True)
