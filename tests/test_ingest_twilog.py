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


_DAY_HTML = ('<article class="tl-tweet">'
             '<time datetime="2026-05-11T09:00:00">09:00</time>'
             '<div class="tweet-text">架空の朝のつぶやき</div>'
             '<a href="/someone/status/1">l</a></article>')


class _FakeResp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_run_writes_days_and_skips_404_and_errors(tmp_workspace, monkeypatch):
    pytest.importorskip("bs4")
    requests = pytest.importorskip("requests")

    class _Sess:
        def __init__(self):
            self.headers = {}

        def get(self, url, timeout=None):
            if url.endswith("date-20260511"):
                return _FakeResp(_DAY_HTML)
            if url.endswith("date-20260512"):
                return _FakeResp("", 500)  # 一時的な失敗は記録して次の日へ
            return _FakeResp("", 404)

    monkeypatch.setattr(requests, "Session", _Sess)
    monkeypatch.setattr(twilog.time, "sleep", lambda s: None)
    args = argparse.Namespace(user="someone", date=None, since="2026-05-11",
                              until="2026-05-13", contact=None, dry_run=False, verbose=False)
    assert twilog.run(JibunConfig(), args, tmp_workspace) == 0
    files = list((tmp_workspace.data_root / "twilog").rglob("*.md"))
    assert [f.name for f in files] == ["2026-05-11.md"]
    text = files[0].read_text(encoding="utf-8")
    assert "架空の朝のつぶやき" in text
    assert "<!-- /someone/status/1 -->" in text
    idx = (tmp_workspace.sources_root / "twilog-index.md").read_text(encoding="utf-8")
    assert "- 2026-05-11 / user=someone / 1 tweets" in idx


def test_since_after_until_errors(tmp_workspace):
    args = argparse.Namespace(user="someone", date=None, since="2026-05-12",
                              until="2026-05-11", contact=None, dry_run=True, verbose=False)
    assert twilog.run(JibunConfig(), args, tmp_workspace) == 1


def test_no_date_args_errors(tmp_workspace):
    args = argparse.Namespace(user="someone", date=None, since=None, until=None,
                              contact=None, dry_run=True, verbose=False)
    assert twilog.run(JibunConfig(), args, tmp_workspace) == 2
