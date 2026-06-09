import argparse

import pytest

from jibun_kit.config import JibunConfig
from jibun_kit.ingest import twilog


def test_parse_day_html():
    pytest.importorskip("bs4")
    html = ('<article class="tl-tweet">'
            '<time datetime="2026-05-11T14:31:00">14:31</time>'
            '<div class="tweet-text">これは twilog の本文</div>'
            '<a href="/u/status/123">l</a></article>')
    rows = list(twilog.parse_day_html(html))
    assert len(rows) == 1
    ts, body, url = rows[0]
    assert ts == "2026-05-11T14:31:00"
    assert "これは twilog の本文" in body
    assert url == "/u/status/123"


def test_user_agent_format():
    assert twilog.user_agent("me@example.com") == \
        "jibun-kit (personal archive tool; contact: me@example.com)"
    assert twilog.user_agent("") == "jibun-kit (personal archive tool)"


def test_dry_run_needs_no_fetch_dep(tmp_workspace, capsys):
    # dry-run は requests import の前に return するので [fetch] 無しでも動く
    args = argparse.Namespace(user="someone", date="2026-05-11", since=None, until=None,
                              contact=None, dry_run=True, verbose=False)
    rc = twilog.run(JibunConfig(), args, tmp_workspace)
    assert rc == 0
    assert "date-20260511" in capsys.readouterr().out


def test_missing_user_errors(tmp_workspace):
    args = argparse.Namespace(user=None, date="2026-05-11", since=None, until=None,
                              contact=None, dry_run=True, verbose=False)
    rc = twilog.run(JibunConfig(), args, tmp_workspace)
    assert rc == 2
