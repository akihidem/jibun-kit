import argparse

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
