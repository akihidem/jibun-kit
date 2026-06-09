import argparse
from pathlib import Path

from jibun_kit.config import JibunConfig
from jibun_kit.ingest import line

FIX = Path(__file__).parent / "fixtures" / "line" / "2026-05-01-Alice.txt"


def _args(**kw):
    base = dict(file=FIX, raw_dir=None, operator_name=None, dry_run=False, verbose=False)
    base.update(kw)
    return argparse.Namespace(**base)


def test_operator_only_and_attachments_skipped(tmp_workspace):
    cfg = JibunConfig(line_name="Me")
    rc = line.run(cfg, _args(), tmp_workspace)
    assert rc == 0
    out = tmp_workspace.data_root / "line" / "2026-05" / "Alice.md"
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "こんにちは、これは自分の発言" in text
    assert "二つ目の自分の発言" in text
    assert "相手の発言" not in text        # other speaker excluded
    assert "[スタンプ]" not in text         # attachment body skipped
    idx = (tmp_workspace.sources_root / "line-index.md").read_text(encoding="utf-8")
    assert "contact=Alice" in idx
    assert "2 messages" in idx


def test_no_operator_name_errors(tmp_workspace):
    rc = line.run(JibunConfig(), _args(), tmp_workspace)
    assert rc == 2


def test_cli_operator_name_overrides_config(tmp_workspace):
    # CLI --operator-name beats config; "Nobody" matches no one -> 0 messages, still rc 0
    cfg = JibunConfig(line_name="Me")
    rc = line.run(cfg, _args(operator_name="Nobody"), tmp_workspace)
    assert rc == 0
    assert not (tmp_workspace.data_root / "line").exists()
