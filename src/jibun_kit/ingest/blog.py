"""``<workspace>/sources/blog.md`` の URL リストからブログ本文を取得・保存。

入力: ``sources/blog.md`` 内の ``https?://`` URL を全て対象。
出力: ``data/blog/<YYYY-MM>/<slug>.md``（本文 + URL + 取得日時）、``sources/blog-index.md``。

  - 対象は自分が運営/寄稿しているブログのみ（sources/blog.md に書いたもの）
  - 1 リクエスト 1.5 秒間隔、User-Agent に連絡先（fetch.contact）
  - 取り込み済み URL は --refresh-all なしならスキップ

依存: ``jibun-kit[fetch]`` (requests, trafilatura)。
"""

from __future__ import annotations

import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from jibun_kit.common import append_index, data_dir
from jibun_kit.config import resolve
from jibun_kit.ingest import SourceGuide

HELP = "sources/blog.md の URL から本文を取得（要 [fetch]）"

GUIDE = SourceGuide(
    label="ブログ記事",
    captures="あなたが書いたブログ記事の本文を URL から取得して取り込みます。",
    how_to_get="取り込みたい記事の URL をこの後の質問で 1 行ずつ教えてください"
               "（sources/blog.md に追記し、そこから取得します）。",
    identity_keys=("fetch.contact",),
    asks=("urls",),
    needs_fetch_extra=True,
)

URL_RE = re.compile(r"https?://[^\s\)\]<>\"']+")
RATE_LIMIT_SEC = 1.5


def user_agent(contact: str) -> str:
    suffix = f"; contact: {contact}" if contact else ""
    return f"jibun-kit (personal archive tool{suffix})"


def parse_blog_urls(blog_md_path: Path) -> list[str]:
    if not blog_md_path.exists():
        return []
    urls = URL_RE.findall(blog_md_path.read_text(encoding="utf-8"))
    cleaned: list[str] = []
    seen: set[str] = set()
    for u in urls:
        u = u.rstrip(",.;:)]>\"'")
        if u in seen:
            continue
        seen.add(u)
        cleaned.append(u)
    return cleaned


def url_to_slug(url: str) -> str:
    parsed = urlparse(url)
    parts = [parsed.netloc] + [p for p in parsed.path.split("/") if p]
    slug = "_".join(parts) or "index"
    slug = re.sub(r"[^A-Za-z0-9._-]", "-", slug)[:120]
    return slug or "index"


def already_ingested(url: str, index_path: Path) -> bool:
    """index の ``url=<URL> /`` 欄と完全一致する行があるか。

    部分文字列で見ると ``https://ex.com/post/1`` が ``https://ex.com/post/10`` の
    取り込み済み行に含まれてしまい、未取得の記事が黙ってスキップされる。
    """
    if not index_path.exists():
        return False
    for ln in index_path.read_text(encoding="utf-8").splitlines():
        for field in ln.split(" / "):
            if field.strip() == f"url={url}":
                return True
    return False


def add_arguments(parser) -> None:
    parser.add_argument("--blog-md", type=Path, default=None,
                        help="URL リストの md（既定: <workspace>/sources/blog.md）")
    parser.add_argument("--refresh-all", action="store_true", help="取り込み済み URL も再取得")
    parser.add_argument("--contact", default=None,
                        help="User-Agent に含める連絡先（未指定なら jibun.toml の fetch.contact）")


def run(config, args, ws) -> int:
    blog_md = args.blog_md or (ws.sources_root / "blog.md")
    urls = parse_blog_urls(blog_md)
    if not urls:
        print(f"no URLs in {blog_md} — まず sources/blog.md に URL を書いてください。", file=sys.stderr)
        return 0

    if args.dry_run:
        print(f"DRY found {len(urls)} URLs:")
        for u in urls:
            print(f"  {u}")
        return 0

    try:
        import requests  # noqa: PLC0415
        import trafilatura  # noqa: PLC0415
    except ImportError:
        print("error: web ingest には追加依存が必要です: pip install 'jibun-kit[fetch]'", file=sys.stderr)
        return 1

    index_path = ws.sources_root / "blog-index.md"
    contact = resolve(args.contact, config.contact, default="")
    session = requests.Session()
    session.headers["User-Agent"] = user_agent(contact)

    total = 0
    for url in urls:
        if not args.refresh_all and already_ingested(url, index_path):
            if args.verbose:
                print(f"  skip (already ingested): {url}", file=sys.stderr)
            continue
        if args.verbose:
            print(f"  fetching {url}", file=sys.stderr)
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            print(f"  ERR fetch {url}: {e}", file=sys.stderr)
            time.sleep(RATE_LIMIT_SEC)
            continue
        extracted = trafilatura.extract(
            resp.text, output_format="markdown", include_links=True, include_comments=False,
        )
        if not extracted:
            print(f"  ERR extract empty: {url}", file=sys.stderr)
            time.sleep(RATE_LIMIT_SEC)
            continue
        today = datetime.now().date()
        slug = url_to_slug(url)
        out_path = data_dir(ws, "blog", today.isoformat()) / f"{slug}.md"
        out_path.write_text(
            f"# {url}\n\n"
            f"- url: {url}\n"
            f"- fetched: {datetime.now().isoformat(timespec='seconds')}\n\n"
            f"---\n\n{extracted}\n",
            encoding="utf-8",
        )
        append_index(ws, "blog", f"- {today.isoformat()} / url={url} / slug={slug}")
        total += 1
        if args.verbose:
            print(f"  wrote {out_path}", file=sys.stderr)
        time.sleep(RATE_LIMIT_SEC)

    print(f"\ndone: {total} blog posts ingested")
    return 0
