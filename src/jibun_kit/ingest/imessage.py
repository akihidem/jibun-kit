"""iMessage 取り込み（imessage-exporter の txt 出力をパース）。

Mac 側で imessage-exporter (https://github.com/ReagentX/imessage-exporter) で
txt 化したものを受領する前提。フォーマット例:

  May 11, 2026  3:14:09 PM
  Me
  ハロー
  Read by them after 1 minute

  （空行区切り。1 メッセージ = 日時行 / 送信者行 / 本文行(複数可) / 任意のステータス行）

自分フィルタ: ``--operator-label``（未指定なら jibun.toml の identity.imessage_label、既定 "Me"）。
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

HELP = "iMessage (imessage-exporter txt) から自分の発言を抽出"

GUIDE = SourceGuide(
    label="iMessage（imessage-exporter）",
    captures="iMessage であなたが送ったメッセージを取り込みます。",
    how_to_get="Mac で imessage-exporter（brew install imessage-exporter）を txt 形式で実行 → "
               "出力 dir（または単一 txt）のパスを指定します。",
    path_flags={"file": "--file", "dir": "--raw-dir"},
    identity_keys=("identity.imessage_label",),
)

# "May 11, 2026  3:14:09 PM" 形式
_DATE_RE = re.compile(r"^([A-Z][a-z]+ \d{1,2}, \d{4})\s+(\d{1,2}:\d{2}:\d{2}\s+[AP]M)\s*$")
# imessage-exporter が付ける既知のステータス行
_STATUS_PREFIXES = ("Read by", "Edited", "Replying to", "Reactions:", "Tapbacks:")


def parse_imessage_txt(path: Path):
    """yield (datetime, sender, body)。blank line 区切り。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    for chunk in re.split(r"\n\s*\n", text):
        lines = chunk.splitlines()
        if len(lines) < 3:
            continue
        m = _DATE_RE.match(lines[0].strip())
        if not m:
            continue
        try:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%B %d, %Y %I:%M:%S %p")
        except ValueError:
            continue
        sender = lines[1].strip()
        body_lines = [ln for ln in lines[2:] if not any(ln.startswith(p) for p in _STATUS_PREFIXES)]
        body = "\n".join(body_lines).strip()
        if body:
            yield dt, sender, body


def process_file(path: Path, operator_label: str, ws, dry_run: bool, verbose: bool) -> dict:
    contact = path.stem
    by_month: dict[str, list[tuple[str, str]]] = defaultdict(list)
    total = 0
    for dt, sender, body in parse_imessage_txt(path):
        if sender != operator_label:
            continue
        by_month[dt.strftime("%Y-%m")].append((dt.isoformat(), body))
        total += 1

    if dry_run or total == 0:
        if verbose:
            print(f"  {path}: {total} operator messages across {len(by_month)} months",
                  file=sys.stderr)
        return {"total": total}

    for ym, msgs in sorted(by_month.items()):
        msgs.sort(key=lambda m: m[0])
        out_path = data_dir(ws, "imessage", f"{ym}-01") / f"{contact}.md"
        header = {
            "title": f"imessage {contact} {ym}",
            "contact": contact,
            "month": ym,
            "operator-label": operator_label,
            "source-raw": str(path),
            "messages": len(msgs),
        }
        count = write_session_md(out_path, header, msgs)
        if count:
            append_index(ws, "imessage", f"- {ym} / contact={contact} / {count} messages")
            if verbose:
                print(f"  wrote {out_path} ({count} messages)", file=sys.stderr)
    return {"total": total}


def add_arguments(parser) -> None:
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--raw-dir", type=Path, help="imessage-exporter 出力 dir")
    g.add_argument("--file", type=Path, help="単一 txt ファイル")
    parser.add_argument(
        "--operator-label", default=None,
        help="imessage-exporter の自分の表示名（未指定なら jibun.toml の identity.imessage_label、既定 Me）",
    )


def run(config, args, ws) -> int:
    operator_label = resolve(args.operator_label, config.imessage_label, default="Me")

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
        total += process_file(f, operator_label, ws, args.dry_run, args.verbose)["total"]

    prefix = "DRY " if args.dry_run else ""
    print(f"\n{prefix}done: {total} operator messages from {len(files)} files")
    return 0
