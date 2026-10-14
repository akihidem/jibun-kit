import argparse

import pytest

from jibun_kit.config import JibunConfig
from jibun_kit.ingest import blog


def test_parse_urls_dedup_and_clean(tmp_path):
    md = tmp_path / "blog.md"
    md.write_text(
        "see https://example.com/post/1 and (https://example.com/post/2).\n"
        "dup https://example.com/post/1\n",
        encoding="utf-8",
    )
    assert blog.parse_blog_urls(md) == [
        "https://example.com/post/1",
        "https://example.com/post/2",
    ]


def test_url_to_slug():
    assert blog.url_to_slug("https://example.com/post/1") == "example.com_post_1"
    assert blog.url_to_slug("https://example.com/") == "example.com"


def test_user_agent_format():
    assert blog.user_agent("") == "jibun-kit (personal archive tool)"
    assert "contact: a@b.c" in blog.user_agent("a@b.c")


def test_dry_run_lists_urls_no_fetch_dep(tmp_workspace, capsys):
    (tmp_workspace.sources_root / "blog.md").write_text(
        "https://example.com/a\n", encoding="utf-8")
    args = argparse.Namespace(blog_md=None, refresh_all=False, contact=None,
                              dry_run=True, verbose=False)
    rc = blog.run(JibunConfig(), args, tmp_workspace)
    assert rc == 0
    assert "https://example.com/a" in capsys.readouterr().out


def test_no_urls_returns_zero(tmp_workspace):
    args = argparse.Namespace(blog_md=None, refresh_all=False, contact=None,
                              dry_run=False, verbose=False)
    rc = blog.run(JibunConfig(), args, tmp_workspace)
    assert rc == 0  # no blog.md -> nothing to do, not an error


def test_already_ingested_exact_url(tmp_path):
    idx = tmp_path / "blog-index.md"
    idx.write_text("# sources/blog-index.md\n\n"
                   "- 2026-05-11 / url=https://example.com/post/10 / slug=x\n",
                   encoding="utf-8")
    assert blog.already_ingested("https://example.com/post/10", idx)
    # 取り込み済み URL の前方一致にすぎない別記事はスキップしない
    assert not blog.already_ingested("https://example.com/post/1", idx)
    assert not blog.already_ingested("https://example.com/post", idx)
    assert not blog.already_ingested("https://example.com/post/1", tmp_path / "none.md")


class _FakeResp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.headers = {}
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        return self.pages.get(url, _FakeResp("", 404))


def _patch_fetch(monkeypatch, pages):
    requests = pytest.importorskip("requests")
    trafilatura = pytest.importorskip("trafilatura")
    sess = _FakeSession(pages)
    monkeypatch.setattr(requests, "Session", lambda: sess)
    monkeypatch.setattr(trafilatura, "extract", lambda html, **kw: html or None)
    monkeypatch.setattr(blog.time, "sleep", lambda s: None)
    return sess


def test_run_fetches_writes_and_skips_ingested(tmp_workspace, monkeypatch):
    (tmp_workspace.sources_root / "blog.md").write_text(
        "https://example.com/post/10\nhttps://example.com/post/1\n"
        "https://example.com/broken\n", encoding="utf-8")
    sess = _patch_fetch(monkeypatch, {
        "https://example.com/post/10": _FakeResp("架空の記事その10"),
        "https://example.com/post/1": _FakeResp("架空の記事その1"),
    })
    args = argparse.Namespace(blog_md=None, refresh_all=False, contact="me@example.com",
                              dry_run=False, verbose=False)
    assert blog.run(JibunConfig(), args, tmp_workspace) == 0
    files = {f.name: f.read_text(encoding="utf-8")
             for f in (tmp_workspace.data_root / "blog").rglob("*.md")}
    assert set(files) == {"example.com_post_10.md", "example.com_post_1.md"}
    assert "架空の記事その1" in files["example.com_post_1.md"]
    assert "contact: me@example.com" in sess.headers["User-Agent"]

    # 2 回目: 取り込み済みの 2 本は取りに行かず、失敗した 1 本だけ再試行する
    sess.calls.clear()
    assert blog.run(JibunConfig(), args, tmp_workspace) == 0
    assert sess.calls == ["https://example.com/broken"]

    # --refresh-all なら全部取り直す
    sess.calls.clear()
    args.refresh_all = True
    assert blog.run(JibunConfig(), args, tmp_workspace) == 0
    assert len(sess.calls) == 3
