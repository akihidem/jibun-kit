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


def _tweet(tid, created_at, text):
    return {"tweet": {"id_str": tid, "created_at": created_at, "full_text": text,
                      "retweeted": False}}


def _write_part(path, n, tweets):
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"window.YTD.tweets.part{n} = " + json.dumps(tweets, ensure_ascii=False),
                    encoding="utf-8")


def test_reads_split_archive_parts(tmp_workspace, tmp_path):
    # 大きいアーカイブは tweets.js / tweets-part1.js ... に分かれる
    d = tmp_path / "export" / "data"
    _write_part(d / "tweets.js", 0, [_tweet("1", "Sun May 10 01:00:00 +0000 2026", "本体の架空")])
    _write_part(d / "tweets-part1.js", 1,
                [_tweet("2", "Mon May 11 01:00:00 +0000 2026", "分割1の架空")])
    _write_part(d / "tweets-part2.js", 2,
                [_tweet("3", "Tue May 12 01:00:00 +0000 2026", "分割2の架空")])
    assert twitter.run(JibunConfig(), _args(export_dir=tmp_path / "export"), tmp_workspace) == 0
    text = (tmp_workspace.data_root / "twitter" / "2026-05" / "tweets.md").read_text(
        encoding="utf-8")
    for s in ("本体の架空", "分割1の架空", "分割2の架空"):
        assert s in text
    assert "- tweets: 3" in text


def test_until_includes_that_day(tmp_workspace, tmp_path):
    d = tmp_path / "export" / "data"
    _write_part(d / "tweets.js", 0, [
        _tweet("1", "Sun May 31 16:00:00 +0000 2026", "末日の架空"),
        _tweet("2", "Mon Jun 01 00:00:00 +0000 2026", "翌日の架空"),
    ])
    rc = twitter.run(JibunConfig(), _args(export_dir=tmp_path / "export", until="2026-05-31"),
                     tmp_workspace)
    assert rc == 0
    files = list((tmp_workspace.data_root / "twitter").rglob("*.md"))
    text = "".join(f.read_text(encoding="utf-8") for f in files)
    assert "末日の架空" in text
    assert "翌日の架空" not in text
