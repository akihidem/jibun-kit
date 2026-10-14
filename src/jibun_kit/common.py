"""Ingest 共通ユーティリティ（de-globalized）。

元 ``jibun/tools/common.py`` から移植。元はモジュール global だった
``JIBUN_ROOT`` / ``DATA_ROOT`` / ``SOURCES_ROOT`` を撤廃し、root は
:class:`jibun_kit.workspace.Workspace` として呼び出し時に注入する
（テスト容易性と複数 workspace 対応のため）。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from jibun_kit.workspace import Workspace

# operator 発言でないと判定するためのメタタグ接頭辞（hook / auto / tool 由来）
META_TAG_PREFIXES: tuple[str, ...] = (
    "<system-reminder>",
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<user-prompt-submit-hook>",
    "<bash-stdout>",
    "<bash-stderr>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "[tool_result]",
    "[Request interrupted by user",
)


def data_dir(ws: "Workspace", source: str, date: str | datetime) -> Path:
    """``ws.data_root/<source>/<YYYY-MM>/`` を返す（``mkdir -p``）。

    ``date`` は ``YYYY-MM-DD`` 文字列か :class:`datetime.datetime`。
    """
    if isinstance(date, datetime):
        ym = date.strftime("%Y-%m")
    else:
        ym = date[:7]
    path = ws.data_root / source / ym
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_meta_tag(content: str) -> bool:
    """``content`` がメタタグ（hook/auto/tool 由来）で始まるか。"""
    if not isinstance(content, str):
        return False
    stripped = content.lstrip()
    return any(stripped.startswith(p) for p in META_TAG_PREFIXES)


def extract_text_parts(content) -> str:
    """``message.content`` が list (Anthropic 形式) のとき ``text`` 要素のみ連結。

    ``str`` なら素通し、``list`` なら ``type == "text"`` の text を ``\\n\\n`` で連結。
    ``tool_result`` / ``tool_use`` / ``image`` は捨てる。
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    texts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text":
            t = part.get("text", "")
            if t:
                texts.append(t)
    return "\n\n".join(texts)


def append_index(ws: "Workspace", source: str, line: str) -> None:
    """``ws.sources_root/<source>-index.md`` に 1 行追記（重複は無視）。"""
    index_path = ws.sources_root / f"{source}-index.md"
    line = line.rstrip()
    if index_path.exists():
        existing = index_path.read_text(encoding="utf-8")
        # 行単位の完全一致で重複判定する。部分文字列で見ると
        # "from=a.mbox" が既存の "from=a.mbox.bak" に含まれる等で新しい行が黙って落ちる。
        if line in existing.splitlines():
            return
        if existing and not existing.endswith("\n"):
            existing += "\n"
    else:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        existing = f"# sources/{source}-index.md\n\n取り込み済みセッション一覧。\n\n"
    index_path.write_text(existing + line + "\n", encoding="utf-8")


def write_session_md(path: Path, header: dict, messages: Iterable[tuple[str, str]]) -> int:
    """セッション markdown を書く。

    ``header``: ``{title, date, source-id, ...}``
    ``messages``: ``(timestamp_str, body)`` の iterable
    return: 書き出した message 件数。0 なら呼び出し側で ``path`` 削除推奨。
    """
    lines: list[str] = []
    lines.append(f"# {header.get('title', 'session')}")
    for k, v in header.items():
        if k == "title":
            continue
        lines.append(f"- {k}: {v}")
    lines.append("")
    count = 0
    for ts, body in messages:
        if not body.strip():
            continue
        lines.append(f"## {ts}")
        lines.append("")
        lines.append(body.rstrip())
        lines.append("")
        lines.append("---")
        lines.append("")
        count += 1
    if count == 0:
        return 0
    path.write_text("\n".join(lines), encoding="utf-8")
    return count


def iter_jsonl(path: Path):
    """jsonl を 1 件ずつ dict で yield。壊れた行は skip。"""
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
