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
