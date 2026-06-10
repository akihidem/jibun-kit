"""Gmail / iCloud (mbox) から自分（operator）の送信メールを抽出。

Google Takeout の「Mail → 送信済み」zip を展開した mbox、または Mail.app の
書き出した mbox を入力にとる。From が自分の email のメールのみを月別 markdown に書く。

判別:
  - From ヘッダが自分の email と完全一致（大文字小文字無視）
  - email_pattern (regex) でも指定可（emails と OR）
  - 本文は text/plain を採用、無ければ text/html を簡易剥がし
  - 引用 (``>`` 行 / "On ... wrote:" 以降) と署名 (``--`` 以降) は除外

依存: 標準ライブラリのみ (mailbox, email)。

``run(..., source_name="icloudmail")`` で出力先 source 名を切り替えられる
（``ingest/icloudmail.py`` がこれを使う）。
"""

from __future__ import annotations

import mailbox
import re
import sys
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path

from jibun_kit.common import append_index, data_dir
from jibun_kit.config import resolve
from jibun_kit.ingest import SourceGuide

HELP = "送信済み mbox (Gmail Takeout) から自分のメールを抽出"

GUIDE = SourceGuide(
    label="Gmail 送信済みメール",
    captures="あなたが書いて送ったメールの本文を取り込みます（受信メールは対象外）。",
    how_to_get="Google Takeout (takeout.google.com) で「メール」だけ選択してエクスポート → "
               "届いた zip を展開し、送信済みメールを含む mbox ファイルのパスを指定します。",
    path_flags={"file": "--mbox"},
    identity_keys=("identity.emails",),
)

QUOTE_LINE = re.compile(r"^>")
ON_WROTE = re.compile(r"^\s*(On|>?\s*On)\s+.+\s+wrote:\s*$|^\d{4}年.+に.+さん.*が書きました:\s*$")
SIGNATURE_DELIM = re.compile(r"^--\s*$")
SLUG_NG = re.compile(r"[^A-Za-z0-9._\-ぁ-んァ-ヴー一-龯]")


def slug_subject(s: str, maxlen: int = 60) -> str:
    s = (s or "no-subject").strip()
    s = SLUG_NG.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:maxlen] or "no-subject"


def decode_payload(part: Message) -> str:
    try:
        raw = part.get_payload(decode=True)
        if raw is None:
            return ""
        charset = part.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")
    except Exception:
        try:
            return str(part.get_payload())
        except Exception:
            return ""


def strip_html(html: str) -> str:
    """簡易 HTML タグ剥がし（標準ライブラリで完結）。"""
    text = re.sub(r"<\s*br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"<\s*/\s*p\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    for ent, ch in (("&nbsp;", " "), ("&lt;", "<"), ("&gt;", ">"),
                    ("&amp;", "&"), ("&quot;", '"'), ("&#39;", "'")):
        text = text.replace(ent, ch)
    return text


def get_payload_text(msg: Message) -> str:
    """text/plain を優先、なければ text/html を簡易剥がし。"""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and \
                    "attachment" not in (part.get("Content-Disposition") or ""):
                return decode_payload(part)
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                return strip_html(decode_payload(part))
        return ""
    ctype = msg.get_content_type()
    if ctype == "text/plain":
        return decode_payload(msg)
    if ctype == "text/html":
        return strip_html(decode_payload(msg))
    return ""


def clean_body(body: str) -> str:
    """引用部分・署名を除外、空行を圧縮。"""
    cleaned: list[str] = []
    in_quote = False
    in_signature = False
    for ln in body.splitlines():
        if SIGNATURE_DELIM.match(ln):
            in_signature = True
            continue
        if in_signature:
            continue
        if ON_WROTE.match(ln) or QUOTE_LINE.match(ln):
            in_quote = True
            continue
        if in_quote:
            if ln.strip() == "":
                in_quote = False
            continue
        cleaned.append(ln)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip()
    return text


def is_operator_sender(from_header: str, emails: list[str], pattern: "re.Pattern | None") -> bool:
    if not from_header:
        return False
    m = re.search(r"<([^>]+)>", from_header)
    addr = (m.group(1) if m else from_header).strip().lower()
    if addr in (e.lower() for e in emails):
        return True
    if pattern and pattern.search(addr):
        return True
    return False


def process_message(msg: Message, emails: list[str], pattern: "re.Pattern | None"):
    """自分の送信メールから (datetime, subject, body) を返す。不一致は None。"""
    if not is_operator_sender(msg.get("From", ""), emails, pattern):
        return None
    try:
        dt = parsedate_to_datetime(msg.get("Date"))
    except Exception:
        return None
    if dt is None:
        return None
    subject = msg.get("Subject", "") or ""
    try:
        from email.header import decode_header, make_header
        subject = str(make_header(decode_header(subject)))
    except Exception:
        pass
    body = clean_body(get_payload_text(msg))
    if not body.strip():
        return None
    return dt, subject, body


def add_arguments(parser) -> None:
    parser.add_argument("--mbox", type=Path, required=True, help="送信済み mbox ファイル")
    parser.add_argument(
        "--operator-email", action="append", default=[],
        help="自分の email（複数可、未指定なら jibun.toml の identity.emails）",
    )
    parser.add_argument(
        "--operator-email-pattern", default=None,
        help="自分の email を正規表現で（config の email_pattern より優先）",
    )


def run(config, args, ws, *, source_name: str = "gmail") -> int:
    emails = resolve(args.operator_email, config.emails, default=[])
    pattern_str = resolve(args.operator_email_pattern, config.email_pattern, default="")
    if not emails and not pattern_str:
        print(
            "error: 自分の email が未設定です。jibun.toml の identity.emails を設定するか "
            "--operator-email / --operator-email-pattern を渡してください。",
            file=sys.stderr,
        )
        return 2
    if not args.mbox.exists():
        print(f"error: mbox not found: {args.mbox}", file=sys.stderr)
        return 1

    pattern = re.compile(pattern_str, re.I) if pattern_str else None

    if args.verbose:
        print(f"  loading {args.mbox}", file=sys.stderr)
    box = mailbox.mbox(str(args.mbox))
    by_month: dict[str, list[tuple[str, str, str]]] = {}
    total_messages = 0
    skipped = 0

    for key in box.iterkeys():
        try:
            msg = box[key]
        except Exception as e:
            if args.verbose:
                print(f"  ERR read {key}: {e}", file=sys.stderr)
            continue
        result = process_message(msg, emails, pattern)
        if result is None:
            skipped += 1
            continue
        dt, subject, body = result
        by_month.setdefault(dt.strftime("%Y-%m"), []).append((dt.isoformat(), subject, body))
        total_messages += 1

    print(f"\nscan: {total_messages} operator-sent / {skipped} skipped")

    if args.dry_run:
        for ym, items in sorted(by_month.items()):
            print(f"  {ym}: {len(items)} mails")
        return 0

    written = 0
    for ym, items in sorted(by_month.items()):
        items.sort(key=lambda x: x[0])
        for date_iso, subject, body in items:
            slug = slug_subject(subject)
            base = data_dir(ws, source_name, f"{ym}-01") / f"{date_iso[:10]}__{slug}.md"
            out_path = base
            counter = 1
            while out_path.exists():
                out_path = base.with_suffix(f".{counter}.md")
                counter += 1
            out_path.write_text(
                f"# {subject or '(no subject)'}\n\n"
                f"- date: {date_iso}\n"
                f"- subject: {subject}\n"
                f"- source: {args.mbox}\n\n"
                f"---\n\n{body}\n",
                encoding="utf-8",
            )
            written += 1
        append_index(ws, source_name, f"- {ym} / {len(items)} mails / from={args.mbox.name}")

    print(f"done: {written} files written across {len(by_month)} months")
    return 0
