"""LINE トーク履歴 export (.txt) から自分（operator）の発言を抽出。

LINE アプリの「トーク履歴を送信」で出力される .txt（iOS/Android 共通）:

  [LINE] <相手名>とのトーク履歴
  保存日時: 2026/05/12 03:14

  2026/05/11(月)
  03:14\t<送信者名>\t<メッセージ>

複数行メッセージはタブで始まらない継続行として現れる。
自分フィルタ: ``--operator-name``（未指定なら jibun.toml の identity.line_name）。
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from jibun_kit.common import append_index, data_dir, write_session_md
from jibun_kit.config import resolve
from jibun_kit.ingest import SourceGuide

HELP = "LINE トーク履歴 (.txt) から自分の発言を抽出"

GUIDE = SourceGuide(
    label="LINE トーク履歴",
    captures="LINE のトークであなたが送った発言を取り込みます（相手の発言・スタンプ等は除外）。",
    how_to_get="スマホの LINE で対象トークを開く → メニュー > その他 > トーク履歴を送信 → "
               ".txt をこの PC に送り、そのパスを指定します（複数なら dir にまとめても OK）。",
    path_flags={"file": "--file", "dir": "--raw-dir"},
    identity_keys=("identity.line_name",),
)

# 2026/05/11(月) や 2026/5/11(月)
_DATE_LINE = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})\([月火水木金土日]\)$")
# 03:14\tAlice\t本文
_MSG_LINE = re.compile(r"^(\d{1,2}):(\d{2})\t([^\t]+)\t(.*)$")
# 添付・スタンプ等（本文がこれだけのものは除外）
_SKIP_BODIES = {"[スタンプ]", "[写真]", "[動画]", "[ファイル]", "[音声メッセージ]", "[Contact]", "[位置情報]"}


def parse_line_export(path: Path):
    """yield (datetime, sender, body)。複数行メッセージは結合済み。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    cur_date: datetime | None = None
    pending: tuple[datetime, str, list[str]] | None = None

    def flush():
        nonlocal pending
        if pending is None:
            return None
        dt, sender, body_lines = pending
        pending = None
        body = "\n".join(body_lines).strip()
        return (dt, sender, body) if body else None

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        m_date = _DATE_LINE.match(line.strip())
        if m_date:
            r = flush()
            if r:
                yield r
            cur_date = datetime(int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3)))
            continue
        m_msg = _MSG_LINE.match(line)
        if m_msg and cur_date:
            r = flush()
            if r:
                yield r
            h, mm, sender, body = m_msg.groups()
            pending = (cur_date.replace(hour=int(h), minute=int(mm)), sender.strip(), [body])
            continue
        # タブで始まらない継続行は直前メッセージの本文の続き
        if pending is not None and line:
            pending[2].append(line)

    r = flush()
    if r:
        yield r


def process_file(path: Path, operator: str, ws, dry_run: bool, verbose: bool) -> dict:
    contact = path.stem
    # ファイル名から日付接頭辞 (例: 2026-05-12-Alice) を剥がす
    contact = re.sub(r"^\d{4}-\d{1,2}-\d{1,2}[-_]", "", contact)

    by_month: dict[str, list[tuple[str, str]]] = defaultdict(list)
    total = 0
    skipped_attach = 0
    for dt, sender, body in parse_line_export(path):
        if sender != operator:
            continue
        if body in _SKIP_BODIES:
            skipped_attach += 1
            continue
        by_month[dt.strftime("%Y-%m")].append((dt.isoformat(), body))
        total += 1

    if verbose:
        print(f"  {path}: {total} operator messages, {skipped_attach} attachments skipped",
              file=sys.stderr)

    if dry_run or total == 0:
        return {"total": total}

    for ym, msgs in sorted(by_month.items()):
        msgs.sort(key=lambda m: m[0])
        out_path = data_dir(ws, "line", f"{ym}-01") / f"{contact}.md"
        header = {
            "title": f"line {contact} {ym}",
            "contact": contact,
            "month": ym,
            "operator-name": operator,
            "source-export": str(path),
            "messages": len(msgs),
        }
        count = write_session_md(out_path, header, msgs)
        if count:
            append_index(ws, "line", f"- {ym} / contact={contact} / {count} messages")
            if verbose:
                print(f"  wrote {out_path} ({count} messages)", file=sys.stderr)
    return {"total": total}


def add_arguments(parser) -> None:
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--file", type=Path, help="LINE export .txt path")
    g.add_argument("--raw-dir", type=Path, help="LINE export .txt 群の dir")
    parser.add_argument(
        "--operator-name", default=None,
        help="LINE 上の自分の表示名（未指定なら jibun.toml の identity.line_name）",
    )


def run(config, args, ws) -> int:
    operator = resolve(args.operator_name, config.line_name, default="")
    if not operator:
        print(
            "error: LINE の自分の表示名が未設定です。jibun.toml の identity.line_name を "
            "設定するか --operator-name を渡してください。",
            file=sys.stderr,
        )
        return 2

    if args.file:
        files = [args.file]
    else:
        if not args.raw_dir.exists():
            print(f"error: raw-dir not found: {args.raw_dir}", file=sys.stderr)
            return 1
        files = sorted(args.raw_dir.glob("*.txt"))

    if not files:
        print("no .txt files to process", file=sys.stderr)
        return 0

    total = 0
    for f in files:
        total += process_file(f, operator, ws, args.dry_run, args.verbose)["total"]

    prefix = "DRY " if args.dry_run else ""
    print(f"\n{prefix}done: {total} operator messages from {len(files)} files")
    return 0
