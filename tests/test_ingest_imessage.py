import argparse
from pathlib import Path

from jibun_kit.config import JibunConfig
from jibun_kit.ingest import imessage

FIX = Path(__file__).parent / "fixtures" / "imessage" / "Alice.txt"


def _args(**kw):
    base = dict(file=FIX, raw_dir=None, operator_label=None, dry_run=False, verbose=False)
    base.update(kw)
    return argparse.Namespace(**base)


def test_operator_only_and_status_stripped(tmp_workspace):
    cfg = JibunConfig(imessage_label="Me")
    rc = imessage.run(cfg, _args(), tmp_workspace)
    assert rc == 0
    out = tmp_workspace.data_root / "imessage" / "2026-05" / "Alice.md"
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "ハロー、これは自分" in text
    assert "二つ目の自分の発言" in text
    assert "相手の発言" not in text          # other speaker excluded
    assert "Read by them" not in text         # status line stripped
    idx = (tmp_workspace.sources_root / "imessage-index.md").read_text(encoding="utf-8")
    assert "contact=Alice" in idx
    assert "2 messages" in idx


def test_default_label_is_me(tmp_workspace):
    # 空 config でも既定ラベル "Me" で動く
    rc = imessage.run(JibunConfig(), _args(), tmp_workspace)
    assert rc == 0
    assert (tmp_workspace.data_root / "imessage" / "2026-05" / "Alice.md").is_file()


def test_dry_run_writes_nothing(tmp_workspace):
    rc = imessage.run(JibunConfig(), _args(dry_run=True), tmp_workspace)
    assert rc == 0
    assert not (tmp_workspace.data_root / "imessage").exists()
