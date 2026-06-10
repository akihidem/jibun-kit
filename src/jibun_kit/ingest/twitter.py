"""Twitter / X の公式 export zip から自分のツイートを抽出。

入力: ``<export-dir>/data/tweets.js``（公式 export「Your archive」を展開したもの）。

判別:
  - retweeted == True は除外
  - full_text が "RT @" で始まるものは除外
  - reply は include（自分の発言なので残す）
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from jibun_kit.common import append_index, data_dir, write_session_md
from jibun_kit.ingest import SourceGuide

HELP = "Twitter/X 公式 export から自分のツイートを抽出"

GUIDE = SourceGuide(
    label="X (Twitter) 公式エクスポート",
    captures="過去の全ツイート（あなたが打った文章）を取り込みます。",
    how_to_get="X のアプリ/Web で「設定とプライバシー > アカウント > データのアーカイブをダウンロード」"
               "を申請 → 後日届く zip を展開し、その dir のパスを指定します（中に data/tweets.js があります）。",
    path_flags={"dir": "--export-dir"},
)

# tweets.js 先頭の代入文プレフィクス
_PREFIX = re.compile(r"^\s*window\.YTD\.tweets\.part\d+\s*=\s*", re.S)
# created_at: "Sun May 11 14:31:00 +0000 2026"
_CREATED_AT_FMT = "%a %b %d %H:%M:%S %z %Y"


def load_tweets_js(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    m = _PREFIX.match(text)
    if m:
        text = text[m.end():]
    return json.loads(text)


def is_retweet(tweet: dict) -> bool:
    if tweet.get("retweeted"):
        return True
    return (tweet.get("full_text") or tweet.get("text") or "").startswith("RT @")


def parse_created_at(s: str) -> "datetime | None":
    try:
        return datetime.strptime(s, _CREATED_AT_FMT)
    except (ValueError, TypeError):
        return None


def extract_tweets(raw: list[dict]):
    """yield (datetime|None, body, tweet_id) for 自分の non-RT tweets。"""
    for item in raw:
        tweet = item.get("tweet", item)
        if is_retweet(tweet):
            continue
        text = tweet.get("full_text") or tweet.get("text") or ""
        if not text.strip():
            continue
        yield parse_created_at(tweet.get("created_at", "")), text, tweet.get("id_str") or tweet.get("id", "")


def add_arguments(parser) -> None:
    parser.add_argument("--export-dir", type=Path, required=True,
                        help="Twitter export を展開した dir (tweets.js を含む)")
    parser.add_argument("--since", help="YYYY-MM-DD 以降のみ")
    parser.add_argument("--until", help="YYYY-MM-DD まで")


def run(config, args, ws) -> int:
    if not args.export_dir.exists():
        print(f"error: export dir not found: {args.export_dir}", file=sys.stderr)
        return 1

    candidates = [args.export_dir / "data" / "tweets.js", args.export_dir / "tweets.js"]
    tweets_js = next((p for p in candidates if p.exists()), None)
    if tweets_js is None:
        found = list(args.export_dir.rglob("tweets*.js"))
        tweets_js = found[0] if found else None
    if tweets_js is None:
        print(f"error: tweets.js not found under {args.export_dir}", file=sys.stderr)
        return 1
    if args.verbose:
        print(f"  loading {tweets_js}", file=sys.stderr)

    raw = load_tweets_js(tweets_js)
    since_dt = datetime.strptime(args.since, "%Y-%m-%d") if args.since else None
    until_dt = datetime.strptime(args.until, "%Y-%m-%d") if args.until else None

    buckets: dict[str, list[tuple[str, str]]] = defaultdict(list)
    total = 0
    for dt, text, tid in extract_tweets(raw):
        if dt is None:
            ym, ts_str = "unknown", "unknown"
        else:
            dt_naive = dt.replace(tzinfo=None)
            if since_dt and dt_naive < since_dt:
                continue
            if until_dt and dt_naive > until_dt:
                continue
            ym, ts_str = dt.strftime("%Y-%m"), dt.isoformat()
        body = f"{text}\n\n<!-- tweet_id: {tid} -->" if tid else text
        buckets[ym].append((ts_str, body))
        total += 1

    if args.dry_run:
        print(f"DRY would write {total} tweets across {len(buckets)} months")
        for ym, msgs in sorted(buckets.items()):
            print(f"  {ym}: {len(msgs)}")
        return 0

    written_months = 0
    written_tweets = 0
    for ym, msgs in sorted(buckets.items()):
        if ym == "unknown":
            out_path = data_dir(ws, "twitter", "1970-01-01") / "unknown.md"
        else:
            out_path = data_dir(ws, "twitter", f"{ym}-01") / "tweets.md"
        msgs.sort(key=lambda m: m[0])
        header = {
            "title": f"twitter {ym}",
            "month": ym,
            "source-export": str(tweets_js),
            "tweets": len(msgs),
        }
        count = write_session_md(out_path, header, msgs)
        if count:
            written_months += 1
            written_tweets += count
            append_index(ws, "twitter", f"- {ym} / {count} tweets / from={tweets_js.parent}")
            if args.verbose:
                print(f"  wrote {out_path} ({count} tweets)", file=sys.stderr)

    print(f"\ndone: {written_tweets} tweets across {written_months} months")
    return 0
