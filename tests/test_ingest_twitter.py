import argparse
from pathlib import Path

from jibun_kit.config import JibunConfig
from jibun_kit.ingest import twitter

EXPORT = Path(__file__).parent / "fixtures" / "twitter"


def _args(**kw):
    base = dict(export_dir=EXPORT, since=None, until=None, dry_run=False, verbose=False)
    base.update(kw)
    return argparse.Namespace(**base)


def test_excludes_retweets(tmp_workspace):
    rc = twitter.run(JibunConfig(), _args(), tmp_workspace)
    assert rc == 0
    out = tmp_workspace.data_root / "twitter" / "2026-05" / "tweets.md"
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "これは自分のツイート" in text
    assert "他人のリツイート" not in text     # RT @ 除外
    assert "tweet_id: 1" in text


def test_dry_run_writes_nothing(tmp_workspace):
    rc = twitter.run(JibunConfig(), _args(dry_run=True), tmp_workspace)
    assert rc == 0
    assert not (tmp_workspace.data_root / "twitter").exists()
