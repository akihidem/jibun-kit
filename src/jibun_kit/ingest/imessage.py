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

# "May 11, 2026  3:14:09 PM" / "Jan 06, 2026  9:29:09 PM" 形式。imessage-exporter は
# 月を省略形で出し、既読などの注記を同じ行の末尾に "(Read by ...)" で付けることがある
_DATE_RE = re.compile(
    r"^([A-Z][a-z]+ \d{1,2}, \d{4})\s+(\d{1,2}:\d{2}:\d{2}\s+[AP]M)(?:\s+\(.*\))?\s*$")
_DATE_FMTS = ("%b %d, %Y %I:%M:%S %p", "%B %d, %Y %I:%M:%S %p")
# imessage-exporter が付ける既知のステータス行
_STATUS_PREFIXES = ("Read by", "Edited", "Replying to", "Reactions:", "Tapbacks:")


def _parse_date_line(line: str) -> "datetime | None":
    m = _DATE_RE.match(line.strip())
    if not m:
        return None
    stamp = re.sub(r"\s+", " ", f"{m.group(1)} {m.group(2)}")
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(stamp, fmt)
        except ValueError:
            continue
    return None


def parse_imessage_txt(path: Path):
    """yield (datetime, sender, body)。

    日時行で 1 メッセージを区切る。空行で区切ると、本文に空行を含むメッセージの
    後半が黙って落ちるため（段落を分けた長文が途中で切れる）。
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    current: "tuple[datetime, list[str]] | None" = None

    def flush():
        if current is None:
            return None
        dt, lines = current
        while lines and not lines[0].strip():
            lines.pop(0)
        if len(lines) < 2:
            return None
        sender = lines[0].strip()
        body_lines = [ln for ln in lines[1:]
                      if not any(ln.startswith(p) for p in _STATUS_PREFIXES)]
        body = "\n".join(body_lines).strip()
        return (dt, sender, body) if body else None

    for ln in text.splitlines():
        dt = _parse_date_line(ln)
        if dt is not None:
            done = flush()
            if done:
                yield done
            current = (dt, [])
        elif current is not None:
            current[1].append(ln)
    done = flush()
    if done:
        yield done


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
