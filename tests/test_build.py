import argparse

from jibun_kit import build
from jibun_kit.config import JibunConfig


def _seed(ws):
    d = ws.data_root / "claude-code" / "2026-05"
    d.mkdir(parents=True)
    (d / "s.md").write_text("# session s\n\n## ts\n\nmy own words\n", encoding="utf-8")
    (ws.sources_root / "claude-code-index.md").write_text("- idx line here\n", encoding="utf-8")


def _args(**kw):
    base = dict(path=None, with_claude=False, effort=None, output=None)
    base.update(kw)
    return argparse.Namespace(**base)


def test_assembles_bundle_prompt_summary(tmp_workspace):
    _seed(tmp_workspace)
    rc = build.run(JibunConfig(), _args(), tmp_workspace)
    assert rc == 0
    bundles = list(tmp_workspace.build_root.glob("*/context-bundle.md"))
    assert len(bundles) == 1
    bdir = bundles[0].parent
    bundle = bundles[0].read_text(encoding="utf-8")
    assert "my own words" in bundle          # data folded in
    assert "idx line here" in bundle          # index folded in
    prompt = (bdir / "prompt.md").read_text(encoding="utf-8")
    assert "4 段の解釈ラダー" in prompt        # methodology present
    assert "出力テンプレート" in prompt        # starter appended
    summary = (bdir / "raw-input.md").read_text(encoding="utf-8")
    assert "claude-code" in summary           # observation range


def test_no_data_errors(tmp_workspace):
    rc = build.run(JibunConfig(), _args(), tmp_workspace)
    assert rc == 2


def test_diagnostic_stance_gating(tmp_workspace):
    _seed(tmp_workspace)
    # OFF (default)
    build.run(JibunConfig(diagnostic_stance=False), _args(), tmp_workspace)
    off = next(tmp_workspace.build_root.glob("*/prompt.md")).read_text(encoding="utf-8")
    assert "診断スタンス: OFF" in off
    assert "診断スタンス: ON" not in off


def test_diagnostic_stance_on(tmp_workspace):
    _seed(tmp_workspace)
    build.run(JibunConfig(diagnostic_stance=True), _args(), tmp_workspace)
    on = next(tmp_workspace.build_root.glob("*/prompt.md")).read_text(encoding="utf-8")
    assert "診断スタンス: ON" in on


def test_output_path_override_shown(tmp_workspace, capsys):
    _seed(tmp_workspace)
    target = tmp_workspace.root / "custom.md"
    build.run(JibunConfig(), _args(output=target), tmp_workspace)
    assert str(target) in capsys.readouterr().out
