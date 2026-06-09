import argparse
from pathlib import Path

from jibun_kit.config import JibunConfig
from jibun_kit.ingest import icloudmail

MBOX = Path(__file__).parent / "fixtures" / "gmail" / "sample.mbox"


def test_routes_output_to_icloudmail(tmp_workspace):
    cfg = JibunConfig(emails=["operator@example.com"])
    args = argparse.Namespace(mbox=MBOX, operator_email=[], operator_email_pattern=None,
                              dry_run=False, verbose=False)
    rc = icloudmail.run(cfg, args, tmp_workspace)
    assert rc == 0
    # 出力が icloudmail/ に落ち、gmail/ には落ちない（隠れ argv ハック撤去の担保）
    assert list((tmp_workspace.data_root / "icloudmail").rglob("*.md"))
    assert not (tmp_workspace.data_root / "gmail").exists()
    idx = (tmp_workspace.sources_root / "icloudmail-index.md").read_text(encoding="utf-8")
    assert "1 mails" in idx
