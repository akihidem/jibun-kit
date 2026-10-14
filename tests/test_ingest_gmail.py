import argparse
from pathlib import Path

from jibun_kit.config import JibunConfig
from jibun_kit.ingest import gmail

FIX = Path(__file__).parent / "fixtures" / "gmail" / "sample.mbox"


def _args(**kw):
    base = dict(mbox=FIX, operator_email=[], operator_email_pattern=None,
                dry_run=False, verbose=False)
    base.update(kw)
    return argparse.Namespace(**base)


def test_matches_operator_only(tmp_workspace):
    cfg = JibunConfig(emails=["operator@example.com"])
    rc = gmail.run(cfg, _args(), tmp_workspace)
    assert rc == 0
    files = list((tmp_workspace.data_root / "gmail").rglob("*.md"))
    assert len(files) == 1  # only the operator-sent mail
    text = files[0].read_text(encoding="utf-8")
    assert "This is my message body." in text
    assert "Alice wrote this" not in text
    idx = (tmp_workspace.sources_root / "gmail-index.md").read_text(encoding="utf-8")
    assert "1 mails" in idx


def test_no_identity_errors(tmp_workspace):
    rc = gmail.run(JibunConfig(), _args(), tmp_workspace)
    assert rc == 2


def test_pattern_via_config(tmp_workspace):
    cfg = JibunConfig(email_pattern=r"^operator@example\.com$")
    rc = gmail.run(cfg, _args(), tmp_workspace)
    assert rc == 0
    assert list((tmp_workspace.data_root / "gmail").rglob("*.md"))


def test_dry_run_writes_nothing(tmp_workspace):
    cfg = JibunConfig(emails=["operator@example.com"])
    rc = gmail.run(cfg, _args(dry_run=True), tmp_workspace)
    assert rc == 0
    assert not (tmp_workspace.data_root / "gmail").exists()
    assert not (tmp_workspace.sources_root / "gmail-index.md").exists()


def test_source_name_override(tmp_workspace):
    # gmail.run reused by icloudmail (Phase 2) via source_name=
    cfg = JibunConfig(emails=["operator@example.com"])
    rc = gmail.run(cfg, _args(), tmp_workspace, source_name="icloudmail")
    assert rc == 0
    assert list((tmp_workspace.data_root / "icloudmail").rglob("*.md"))
    assert not (tmp_workspace.data_root / "gmail").exists()


def test_rerun_is_idempotent(tmp_workspace):
    # 同じ mbox を 2 回取り込んでも .1.md の重複は増えない
    cfg = JibunConfig(emails=["operator@example.com"])
    assert gmail.run(cfg, _args(), tmp_workspace) == 0
    assert gmail.run(cfg, _args(), tmp_workspace) == 0
    files = list((tmp_workspace.data_root / "gmail").rglob("*.md"))
    assert len(files) == 1


def test_same_day_same_subject_distinct_mails_kept(tmp_workspace, tmp_path):
    # 同じ日・同じ件名でも本文が違うメールは別ファイルとして両方残る
    mbox = tmp_path / "two.mbox"
    mbox.write_text(
        "From operator@example.com Mon May 11 00:00:00 2026\n"
        "From: Me <operator@example.com>\n"
        "Subject: Note\n"
        "Date: Mon, 11 May 2026 09:00:00 +0900\n"
        "Content-Type: text/plain; charset=utf-8\n\n"
        "first body\n\n"
        "From operator@example.com Mon May 11 00:00:00 2026\n"
        "From: Me <operator@example.com>\n"
        "Subject: Note\n"
        "Date: Mon, 11 May 2026 18:00:00 +0900\n"
        "Content-Type: text/plain; charset=utf-8\n\n"
        "second body\n",
        encoding="utf-8",
    )
    cfg = JibunConfig(emails=["operator@example.com"])
    for _ in range(2):  # 再実行しても 2 件のまま
        assert gmail.run(cfg, _args(mbox=mbox), tmp_workspace) == 0
    files = sorted((tmp_workspace.data_root / "gmail").rglob("*.md"))
    assert [f.name for f in files] == ["2026-05-11__Note.1.md", "2026-05-11__Note.md"]
    bodies = " ".join(f.read_text(encoding="utf-8") for f in files)
    assert "first body" in bodies and "second body" in bodies
