"""Claude Code 会話ログから自分（operator）の発言を抽出して ``data/claude-code/`` に書く。

判別ロジック:
  - ``type == "user"`` のみ対象
  - ``isSidechain == True`` は除外
  - ``content`` が str かつメタタグ接頭辞で始まるものは除外
  - ``content`` が list の場合 ``type==text`` のみ抽出、tool_result/tool_use/image は捨てる
  - 残ったテキストが空なら捨てる
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from jibun_kit.common import (
    append_index,
    data_dir,
    extract_text_parts,
    is_meta_tag,
    iter_jsonl,
    write_session_md,
)
from jibun_kit.config import resolve

HELP = "Claude Code の会話ログ (jsonl) から自分の発言を抽出"


def is_operator_message(entry: dict) -> bool:
    if entry.get("type") != "user":
        return False
    if entry.get("isSidechain"):
        return False
    msg = entry.get("message") or {}
    if msg.get("role") != "user":
        return False
    content = msg.get("content")
    if isinstance(content, str):
        return not is_meta_tag(content)
    if isinstance(content, list):
        # text パートが 1 つでもあれば operator 発言の可能性あり
        return any(
            isinstance(p, dict) and p.get("type") == "text" and p.get("text", "").strip()
            for p in content
        )
    return False


def extract_operator_text(entry: dict) -> str:
    msg = entry.get("message") or {}
    return extract_text_parts(msg.get("content"))


def process_session(jsonl_path: Path, ws, dry_run: bool, verbose: bool) -> dict | None:
    session_id = jsonl_path.stem
    header_meta: dict = {}
    messages: list[tuple[str, str]] = []

    for entry in iter_jsonl(jsonl_path):
        # header メタは最初に観察された user entry の値で固定
        if not header_meta and entry.get("type") == "user":
            header_meta = {
                "date": (entry.get("timestamp") or "")[:10],
                "session-id": session_id,
                "cwd": entry.get("cwd", "?"),
                "gitBranch": entry.get("gitBranch", "?"),
                "version": entry.get("version", "?"),
            }
        if not is_operator_message(entry):
            continue
        text = extract_operator_text(entry).strip()
        if not text or is_meta_tag(text):
            continue
        messages.append((entry.get("timestamp", "?"), text))

    if not messages:
        if verbose:
            print(f"  skip (no operator messages): {session_id}", file=sys.stderr)
        return None

    date = header_meta.get("date") or datetime.now().strftime("%Y-%m-%d")

    if dry_run:
        # mkdir せず表示用パスだけ組む（dry-run は副作用ゼロ）
        disp = ws.data_root / "claude-code" / date[:7] / f"{session_id}.md"
        print(f"  would write {disp} ({len(messages)} messages)")
        return {"messages": len(messages)}

    out_path = data_dir(ws, "claude-code", date) / f"{session_id}.md"
    header = {"title": f"session {session_id}", **header_meta, "messages": len(messages)}
    count = write_session_md(out_path, header, messages)
    if count == 0:
        return None

    index_line = (
        f"- {date} / session={session_id} / {count} messages "
        f"/ cwd={header_meta.get('cwd', '?')} / branch={header_meta.get('gitBranch', '?')}"
    )
    append_index(ws, "claude-code", index_line)
    if verbose:
        print(f"  wrote {out_path} ({count} messages)", file=sys.stderr)
    return {"messages": count}


def add_arguments(parser) -> None:
    parser.add_argument("--session", help="特定 session-id のみ処理")
    parser.add_argument("--since", help="YYYY-MM-DD 以降の mtime のみ")
    parser.add_argument("--until", help="YYYY-MM-DD まで")
    parser.add_argument("--all", action="store_true", help="全 jsonl を処理")
    parser.add_argument(
        "--projects-root",
        type=Path,
        default=None,
        help="Claude Code projects root（既定: jibun.toml の sources.claude_code.projects_root）",
    )


def run(config, args, ws) -> int:
    cli_root = str(args.projects_root) if args.projects_root else ""
    root_str = resolve(cli_root, config.claude_projects_root,
                       env_var="CLAUDE_PROJECTS_ROOT", default="")
    if not root_str:
        print(
            "error: Claude projects root が未設定です。jibun.toml の "
            "[sources.claude_code].projects_root を設定するか --projects-root <path> を渡してください。",
            file=sys.stderr,
        )
        return 2
    projects_root = Path(root_str).expanduser()
    if not projects_root.exists():
        print(f"error: projects root not found: {projects_root}", file=sys.stderr)
        return 1

    if args.session:
        targets = [projects_root / f"{args.session}.jsonl"]
    elif args.all or args.since or args.until:
        targets = sorted(projects_root.glob("*.jsonl"))
    else:
        print("error: --session か --all/--since/--until のいずれかが必要です。", file=sys.stderr)
        return 2

    if args.since:
        since_ts = datetime.strptime(args.since, "%Y-%m-%d").timestamp()
        targets = [p for p in targets if p.stat().st_mtime >= since_ts]
    if args.until:
        until_ts = datetime.strptime(args.until, "%Y-%m-%d").timestamp() + 86400
        targets = [p for p in targets if p.stat().st_mtime <= until_ts]

    total_sessions = 0
    total_messages = 0
    for path in targets:
        if not path.exists():
            print(f"  not found: {path}", file=sys.stderr)
            continue
        result = process_session(path, ws, args.dry_run, args.verbose)
        if result:
            total_sessions += 1
            total_messages += result["messages"]

    prefix = "DRY " if args.dry_run else ""
    print(f"\n{prefix}done: {total_sessions} sessions, {total_messages} messages")
    return 0
