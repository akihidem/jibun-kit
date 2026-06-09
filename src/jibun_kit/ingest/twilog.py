"""Twilog (twilog.togetter.com) から自分の過去ツイートを取得。

robots.txt で許可された ``/<user>/date-YYYYMMDD`` を順次クロールする。

利用ルール:
  - 対象は自分自身のアカウントのみ
  - 1 リクエスト 2 秒間隔
  - User-Agent に連絡先（fetch.contact）を含める
  - クロール対象は明示指定した日付範囲のみ

依存: ``jibun-kit[fetch]`` (requests, beautifulsoup4)。
"""

from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from jibun_kit.common import append_index, data_dir, write_session_md
from jibun_kit.config import resolve

HELP = "twilog から自分の過去ツイートを取得（要 [fetch]）"

BASE = "https://twilog.togetter.com"
RATE_LIMIT_SEC = 2.0


def user_agent(contact: str) -> str:
    suffix = f"; contact: {contact}" if contact else ""
    return f"jibun-kit (personal archive tool{suffix})"


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def fetch_day(session, user: str, day: date) -> "str | None":
    """``/<user>/date-YYYYMMDD`` を fetch。存在しない日は 404 → None。"""
    url = f"{BASE}/{user}/date-{day.strftime('%Y%m%d')}"
    resp = session.get(url, timeout=20)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.text


def parse_day_html(html: str):
    """tweet 一覧を yield (timestamp_str, body, tweet_url)。

    twilog の HTML 構造は変わりうるため複数セレクタを試す（best-effort、壊れたら要更新）。
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    selectors = [
        ("article.tl-tweet", "time", ".tweet-text"),
        ("div.tweet-card", "time", ".tweet-body"),
        ("li.status", ".time", ".text"),
    ]
    for container_sel, time_sel, body_sel in selectors:
        items = soup.select(container_sel)
        if not items:
            continue
        for it in items:
            b_el = it.select_one(body_sel)
            if not b_el:
                continue
            t_el = it.select_one(time_sel)
            ts = (t_el.get("datetime") if t_el else None) or (t_el.get_text(strip=True) if t_el else "")
            link_el = it.select_one("a[href*='/status/']")
            url = link_el.get("href") if link_el else ""
            body = b_el.get_text("\n", strip=True)
            if body:
                yield ts, body, url
        return  # 最初に match したセレクタで打ち切り


def add_arguments(parser) -> None:
    parser.add_argument("--user", default=None,
                        help="twilog のユーザー名（未指定なら jibun.toml の identity.twilog_user）")
    parser.add_argument("--date", help="単一日 YYYY-MM-DD")
    parser.add_argument("--since", help="YYYY-MM-DD")
    parser.add_argument("--until", help="YYYY-MM-DD")
    parser.add_argument("--contact", default=None,
                        help="User-Agent に含める連絡先（未指定なら jibun.toml の fetch.contact）")


def run(config, args, ws) -> int:
    user = resolve(args.user, config.twilog_user, default="")
    if not user:
        print("error: twilog user 未設定。jibun.toml の identity.twilog_user か --user を指定してください。",
              file=sys.stderr)
        return 2

    if args.date:
        days = [datetime.strptime(args.date, "%Y-%m-%d").date()]
    elif args.since and args.until:
        start = datetime.strptime(args.since, "%Y-%m-%d").date()
        end = datetime.strptime(args.until, "%Y-%m-%d").date()
        if start > end:
            print("error: since > until", file=sys.stderr)
            return 1
        days = list(daterange(start, end))
    else:
        print("error: --date か --since/--until が必要です。", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"DRY would fetch {len(days)} days for user={user}")
        for d in days[:5]:
            print(f"  {BASE}/{user}/date-{d.strftime('%Y%m%d')}")
        if len(days) > 5:
            print(f"  ... and {len(days) - 5} more")
        return 0

    try:
        import requests  # noqa: PLC0415
    except ImportError:
        print("error: web ingest には追加依存が必要です: pip install 'jibun-kit[fetch]'", file=sys.stderr)
        return 1

    contact = resolve(args.contact, config.contact, default="")
    session = requests.Session()
    session.headers["User-Agent"] = user_agent(contact)

    total_tweets = 0
    total_days = 0
    for d in days:
        if args.verbose:
            print(f"  fetching {d}", file=sys.stderr)
        try:
            html = fetch_day(session, user, d)
        except Exception as e:
            print(f"  ERR {d}: {e}", file=sys.stderr)
            time.sleep(RATE_LIMIT_SEC)
            continue
        if html is None:
            if args.verbose:
                print(f"  404 {d}", file=sys.stderr)
            time.sleep(RATE_LIMIT_SEC)
            continue
        tweets = list(parse_day_html(html))
        if tweets:
            out_path = data_dir(ws, "twilog", d.isoformat()) / f"{d.isoformat()}.md"
            header = {
                "title": f"twilog {user} {d.isoformat()}",
                "user": user,
                "date": d.isoformat(),
                "source-url": f"{BASE}/{user}/date-{d.strftime('%Y%m%d')}",
                "tweets": len(tweets),
            }
            messages = [(ts or d.isoformat(), f"{body}\n\n<!-- {url} -->" if url else body)
                        for ts, body, url in tweets]
            count = write_session_md(out_path, header, messages)
            if count:
                total_tweets += count
                total_days += 1
                append_index(ws, "twilog", f"- {d.isoformat()} / user={user} / {count} tweets")
                if args.verbose:
                    print(f"  wrote {out_path} ({count} tweets)", file=sys.stderr)
        time.sleep(RATE_LIMIT_SEC)

    print(f"\ndone: {total_tweets} tweets across {total_days} days (user={user})")
    return 0
