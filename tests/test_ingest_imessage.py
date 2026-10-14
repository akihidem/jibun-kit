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


def _run_on(tmp_workspace, tmp_path, content):
    f = tmp_path / "Bob.txt"
    f.write_text(content, encoding="utf-8")
    assert imessage.run(JibunConfig(imessage_label="Me"), _args(file=f), tmp_workspace) == 0
    return {p.parent.name: p.read_text(encoding="utf-8")
            for p in (tmp_workspace.data_root / "imessage").rglob("Bob.md")}


def test_abbreviated_month_and_inline_read_receipt(tmp_workspace, tmp_path):
    # imessage-exporter は月を省略形で出し、既読注記を日時行の末尾に付けることがある
    out = _run_on(tmp_workspace, tmp_path,
                  "Jan 06, 2026  9:29:09 PM\nMe\n一月の架空の発言\n\n"
                  "Sep 02, 2026 10:14:09 AM (Read by them after 1 minute)\nMe\n九月の架空の発言\n")
    assert set(out) == {"2026-01", "2026-09"}
    assert "一月の架空の発言" in out["2026-01"]
    assert "九月の架空の発言" in out["2026-09"]
    assert "Read by" not in out["2026-09"]


def test_blank_line_inside_message_keeps_rest(tmp_workspace, tmp_path):
    out = _run_on(tmp_workspace, tmp_path,
                  "May 11, 2026  3:14:09 PM\nMe\n一段落目\n\n二段落目\n\n"
                  "May 11, 2026  3:15:00 PM\nBob\n相手の架空の発言\n")
    text = out["2026-05"]
    assert "一段落目" in text and "二段落目" in text
    assert "相手の架空の発言" not in text
    assert "- messages: 1" in text
