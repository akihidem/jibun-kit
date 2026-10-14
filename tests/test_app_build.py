import pytest
from conftest import ScriptedPrompter

from jibun_kit import claude_cli
from jibun_kit.app import act_build
from jibun_kit.app.act_build import _split_sections, run_act3
from jibun_kit.config import JibunConfig

DRAFT_V1 = ("# jibun.md\n\n前文です\n\n"
            "## 1. 観察\n\nv1 の観察\n\n"
            "## 2. 仮説\n\nv1 の仮説\n")
DRAFT_V2 = ("# jibun.md\n\n前文です\n\n"
            "## 1. 観察\n\nv2 の観察（直した）\n\n"
            "## 2. 仮説\n\nv1 の仮説\n")


def _seed(ws):
    d = ws.data_root / "claude-code" / "2026-05"
    d.mkdir(parents=True)
    (d / "s.md").write_text("# session s\n\n## ts\n\nmy own words\n", encoding="utf-8")
    (ws.sources_root / "claude-code-index.md").write_text("- idx line\n", encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_real_claude(monkeypatch):
    monkeypatch.setattr(claude_cli, "find_claude", lambda: None)
    monkeypatch.setattr(claude_cli, "run_claude",
                        lambda *a, **k: pytest.fail("unexpected egress"))


def test_split_sections():
    secs = _split_sections(DRAFT_V1)
    assert len(secs) == 3
    assert secs[0].startswith("# jibun.md")      # 前文ブロック
    assert secs[1].startswith("## 1. 観察")
    assert _split_sections("見出しの無いドラフト") == ["見出しの無いドラフト"]


def test_no_data_returns_2(tmp_workspace):
    p = ScriptedPrompter([])
    assert run_act3(p, JibunConfig(), tmp_workspace) == 2


def test_without_claude_paste_flow(tmp_workspace):
    _seed(tmp_workspace)
    p = ScriptedPrompter([])  # claude 不在 → 同意質問なしで貼り付け案内
    rc = run_act3(p, JibunConfig(), tmp_workspace)
    assert rc == 0
    bdir = next(tmp_workspace.build_root.iterdir())
    assert (bdir / "prompt.md").exists()
    assert (bdir / "context-bundle.md").exists()
    assert "貼り付け" in p.said() or "貼って" in p.said()
    assert not tmp_workspace.jibun_md.exists()


def test_consent_declined_paste_flow(tmp_workspace, monkeypatch):
    _seed(tmp_workspace)
    monkeypatch.setattr(claude_cli, "find_claude", lambda: "/fake/claude")
    p = ScriptedPrompter([False])  # egress 同意しない
    rc = run_act3(p, JibunConfig(), tmp_workspace)
    assert rc == 0
    assert not tmp_workspace.jibun_md.exists()


def test_refine_loop_then_save(tmp_workspace, monkeypatch):
    _seed(tmp_workspace)
    monkeypatch.setattr(claude_cli, "find_claude", lambda: "/fake/claude")
    calls: list[str] = []

    def fake_run_claude(text, **kw):
        calls.append(text)
        return DRAFT_V1 if len(calls) == 1 else DRAFT_V2

    monkeypatch.setattr(claude_cli, "run_claude", fake_run_claude)
    p = ScriptedPrompter([
        True,            # egress 同意
        "OK",            # round1: 前文 OK
        "修正",          # round1: §1 にコメント
        "観察が浅いので深掘りして",
        "OK",            # round1: §2 OK
        "OK", "OK", "OK",  # round2: 全部 OK
        True,            # 最終保存
    ])
    rc = run_act3(p, JibunConfig(), tmp_workspace)
    assert rc == 0
    assert len(calls) == 2
    assert "# context bundle" in calls[0]       # 初回は bundle 込み
    assert "# context bundle" not in calls[1]   # 改訂で bundle は再送しない
    assert "観察が浅いので深掘りして" in calls[1]  # フィードバックが渡る
    assert "現在のドラフト" in calls[1]
    saved = tmp_workspace.jibun_md.read_text(encoding="utf-8")
    assert "v2 の観察" in saved
    bdir = next(tmp_workspace.build_root.iterdir())
    assert (bdir / "jibun.draft.md").exists()
    assert (bdir / "jibun.draft.2.md").exists()
    fb = (bdir / "feedback.md").read_text(encoding="utf-8")
    assert "round 1" in fb and "観察が浅いので" in fb


def test_decline_final_save_keeps_target(tmp_workspace, monkeypatch):
    _seed(tmp_workspace)
    monkeypatch.setattr(claude_cli, "find_claude", lambda: "/fake/claude")
    monkeypatch.setattr(claude_cli, "run_claude", lambda *a, **k: DRAFT_V1)
    p = ScriptedPrompter([True, "OK", "OK", "OK", False])  # 保存は断る
    rc = run_act3(p, JibunConfig(), tmp_workspace)
    assert rc == 0
    assert not tmp_workspace.jibun_md.exists()
    bdir = next(tmp_workspace.build_root.iterdir())
    assert (bdir / "jibun.draft.md").exists()  # ドラフトは残る


def test_existing_jibun_md_backed_up(tmp_workspace, monkeypatch):
    _seed(tmp_workspace)
    tmp_workspace.jibun_md.write_text("以前の自分の jibun.md\n", encoding="utf-8")
    monkeypatch.setattr(claude_cli, "find_claude", lambda: "/fake/claude")
    monkeypatch.setattr(claude_cli, "run_claude", lambda *a, **k: DRAFT_V1)
    p = ScriptedPrompter([True, "OK", "OK", "OK", True])
    rc = run_act3(p, JibunConfig(), tmp_workspace)
    assert rc == 0
    bdir = next(tmp_workspace.build_root.iterdir())
    backup = (bdir / "jibun.previous.md").read_text(encoding="utf-8")
    assert backup == "以前の自分の jibun.md\n"
    assert "v1 の観察" in tmp_workspace.jibun_md.read_text(encoding="utf-8")


def test_claude_error_abort_keeps_artifacts(tmp_workspace, monkeypatch):
    _seed(tmp_workspace)
    monkeypatch.setattr(claude_cli, "find_claude", lambda: "/fake/claude")

    def boom(*a, **k):
        raise claude_cli.ClaudeError("claude returned 3", returncode=3, stderr="overflow")

    monkeypatch.setattr(claude_cli, "run_claude", boom)
    p = ScriptedPrompter([True, "中断"])
    rc = run_act3(p, JibunConfig(), tmp_workspace)
    assert rc == 0
    bdir = next(tmp_workspace.build_root.iterdir())
    assert (bdir / "context-bundle.md").exists()  # 素材は残る
    assert not tmp_workspace.jibun_md.exists()


def test_claude_error_retry_then_success(tmp_workspace, monkeypatch):
    _seed(tmp_workspace)
    monkeypatch.setattr(claude_cli, "find_claude", lambda: "/fake/claude")
    state = {"n": 0}

    def flaky(*a, **k):
        state["n"] += 1
        if state["n"] == 1:
            raise claude_cli.ClaudeError("timeout", returncode=None)
        return DRAFT_V1

    monkeypatch.setattr(claude_cli, "run_claude", flaky)
    p = ScriptedPrompter([True, "再試行", "OK", "OK", "OK", True])
    rc = run_act3(p, JibunConfig(), tmp_workspace)
    assert rc == 0
    assert state["n"] == 2
    assert tmp_workspace.jibun_md.exists()


def test_second_save_same_day_keeps_original_backup(tmp_workspace, monkeypatch):
    # 同日に 2 回保存しても、最初の退避（本人の原本）は上書きされない
    _seed(tmp_workspace)
    tmp_workspace.jibun_md.write_text("手書きの原本\n", encoding="utf-8")
    monkeypatch.setattr(claude_cli, "find_claude", lambda: "/fake/claude")
    for draft in (DRAFT_V1, DRAFT_V2):
        monkeypatch.setattr(claude_cli, "run_claude", lambda *a, _d=draft, **k: _d)
        p = ScriptedPrompter([True, "OK", "OK", "OK", True])
        assert run_act3(p, JibunConfig(), tmp_workspace) == 0
    bdir = next(tmp_workspace.build_root.iterdir())
    assert (bdir / "jibun.previous.md").read_text(encoding="utf-8") == "手書きの原本\n"
    assert "v1 の観察" in (bdir / "jibun.previous.2.md").read_text(encoding="utf-8")
    assert "v2 の観察" in tmp_workspace.jibun_md.read_text(encoding="utf-8")


@pytest.mark.parametrize("out", ["", "   \n\n", "```markdown\n```\n"])
def test_empty_claude_output_not_offered_for_save(tmp_workspace, monkeypatch, out):
    # 空・空白のみ・フェンスだけの出力はドラフトにせず、保存も提案しない
    _seed(tmp_workspace)
    tmp_workspace.jibun_md.write_text("既存の内容\n", encoding="utf-8")
    monkeypatch.setattr(claude_cli, "find_claude", lambda: "/fake/claude")
    monkeypatch.setattr(claude_cli, "run_claude", lambda *a, **k: out)
    p = ScriptedPrompter([True])  # egress 同意のみ。以降の質問があれば台本枯渇で失敗
    rc = run_act3(p, JibunConfig(), tmp_workspace)
    assert rc == 0
    assert "出力が空" in p.said()
    assert tmp_workspace.jibun_md.read_text(encoding="utf-8") == "既存の内容\n"
    bdir = next(tmp_workspace.build_root.iterdir())
    assert not (bdir / "jibun.draft.md").exists()
