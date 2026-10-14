from pathlib import Path

import pytest

from conftest import ScriptedPrompter

from jibun_kit.app import act_sources
from jibun_kit.app.act_sources import (
    ACT1_ORDER,
    IDENTITY_ASKS,
    _dispatch_ingest,
    ensure_workspace,
    run_act1,
)
from jibun_kit.config import JibunConfig, set_toml_values
from jibun_kit.ingest import REGISTRY, load_source
from jibun_kit.scaffold import scaffold_workspace
from jibun_kit.workspace import Workspace

FIX = Path(__file__).parent / "fixtures"


def _scaffold(tmp_path) -> Workspace:
    ws = Workspace(tmp_path)
    scaffold_workspace(ws)
    return ws


def test_act1_order_covers_registry():
    assert set(ACT1_ORDER) == set(REGISTRY)


def test_identity_asks_cover_guide_keys():
    for name in REGISTRY:
        for key in load_source(name).GUIDE.identity_keys:
            if key == "sources.claude_code.projects_root":
                continue  # パス回答がそのまま永続値（IdentityAsk 不要）
            assert key in IDENTITY_ASKS, f"{name}: {key}"


def test_ensure_workspace_scaffolds(tmp_path):
    p = ScriptedPrompter([True])  # この場所に作成
    ws = ensure_workspace(p, tmp_path)
    assert ws is not None
    assert ws.config_path.is_file()
    assert ws.jibun_md.is_file()


def test_ensure_workspace_decline(tmp_path):
    p = ScriptedPrompter([False, None])  # 作らない → 別パスも空 Enter
    assert ensure_workspace(p, tmp_path) is None
    assert not (tmp_path / "jibun.toml").exists()


def test_twitter_fixture_ingested(tmp_path):
    ws = _scaffold(tmp_path)
    p = ScriptedPrompter([
        "取り込む",              # choose
        str(FIX / "twitter"),    # export dir
        True,                    # dry-run 確認 → 本取り込み
    ])
    status = act_sources._propose_source(p, ws, "twitter", load_source("twitter").GUIDE)
    assert status == "ingested"
    assert list((ws.data_root / "twitter").rglob("*.md"))


def test_line_identity_persisted_then_ingested(tmp_path):
    ws = _scaffold(tmp_path)
    p = ScriptedPrompter([
        "取り込む",
        "Me",                                        # identity.line_name
        str(FIX / "line" / "2026-05-01-Alice.txt"),  # --file
        True,
    ])
    status = act_sources._propose_source(p, ws, "line", load_source("line").GUIDE)
    assert status == "ingested"
    assert JibunConfig.load(ws.config_path).line_name == "Me"  # toml に永続化
    assert list((ws.data_root / "line").rglob("*.md"))


def test_existing_identity_reused(tmp_path):
    ws = _scaffold(tmp_path)
    set_toml_values(ws.config_path, {"identity": {"line_name": "Me"}})
    p = ScriptedPrompter([
        "取り込む",
        True,  # 設定済みの line_name を使う（再入力なし）
        str(FIX / "line" / "2026-05-01-Alice.txt"),
        True,
    ])
    status = act_sources._propose_source(p, ws, "line", load_source("line").GUIDE)
    assert status == "ingested"


def test_show_how_to_get_then_skip(tmp_path):
    ws = _scaffold(tmp_path)
    p = ScriptedPrompter(["入手方法", "スキップ"])
    status = act_sources._propose_source(p, ws, "twitter", load_source("twitter").GUIDE)
    assert status == "skipped"
    assert "アーカイブをダウンロード" in p.said()  # 入手方法が表示された
    assert not (ws.data_root / "twitter").exists()


def test_invalid_path_three_times_skips(tmp_path):
    ws = _scaffold(tmp_path)
    p = ScriptedPrompter(["取り込む", "/nope/1", "/nope/2", "/nope/3"])
    status = act_sources._propose_source(p, ws, "twitter", load_source("twitter").GUIDE)
    assert status == "skipped"
    assert "3 回" in p.said()


def test_dispatch_ingest_catches_systemexit_and_captures(tmp_path, capsys):
    ws = _scaffold(tmp_path)
    rc, out = _dispatch_ingest(ws, "line", ["--bogus"])
    assert rc == 2          # argparse の usage エラー
    assert "usage" in out   # 出力は捕捉して返す
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""  # 直接は漏らさない


def test_dry_run_preview_reaches_prompter(tmp_path):
    ws = _scaffold(tmp_path)
    p = ScriptedPrompter(["取り込む", str(FIX / "twitter"), True])
    status = act_sources._propose_source(p, ws, "twitter", load_source("twitter").GUIDE)
    assert status == "ingested"
    assert "DRY would write" in p.said()  # dry-run プレビューが transcript に届く


def test_run_act1_resume_skips_done(tmp_path):
    ws = _scaffold(tmp_path)
    done = [n for n in ACT1_ORDER if n != "twitter"]  # twitter だけ未提案の体
    p = ScriptedPrompter(["スキップ"])
    saves: list[int] = []
    run_act1(p, ws, done, save=lambda: saves.append(1))
    assert saves == [1]  # 残っていた twitter の 1 回だけ
    assert set(done) == set(ACT1_ORDER)


def test_multiline_array_in_toml_tells_manual_edit(tmp_path):
    # 手書きの複数行 array で set_toml_values が ValueError → traceback にせず案内してスキップ
    ws = _scaffold(tmp_path)
    text = ws.config_path.read_text(encoding="utf-8").replace(
        "emails = []", 'emails = [\n  "old@example.com",\n]')
    ws.config_path.write_text(text, encoding="utf-8")
    p = ScriptedPrompter(["取り込む", False, "new@example.com"])  # 設定済みは使わず再入力
    status = act_sources._propose_source(p, ws, "gmail", load_source("gmail").GUIDE)
    assert status == "skipped"
    assert "直接編集" in p.said()
    assert ws.config_path.read_text(encoding="utf-8") == text  # ファイルは未変更


def test_broken_toml_tells_manual_edit(tmp_path):
    ws = _scaffold(tmp_path)
    ws.config_path.write_text("[identity\n", encoding="utf-8")
    p = ScriptedPrompter(["取り込む"])
    status = act_sources._propose_source(p, ws, "gmail", load_source("gmail").GUIDE)
    assert status == "failed"
    assert "直接編集" in p.said()


def test_claude_code_projects_root_stored_absolute(tmp_path, monkeypatch):
    ws = _scaffold(tmp_path / "ws")
    (tmp_path / "proj").mkdir()
    monkeypatch.chdir(tmp_path)
    p = ScriptedPrompter(["取り込む", "proj", False])  # 相対パスで回答、取り込みは断る
    act_sources._propose_source(p, ws, "claude-code", load_source("claude-code").GUIDE)
    stored = JibunConfig.load(ws.config_path).claude_projects_root
    assert stored == str((tmp_path / "proj").resolve())


@pytest.mark.parametrize("code, rc", [(None, 0), (0, 0), (3, 3), ("boom", 1)])
def test_dispatch_ingest_systemexit_codes(tmp_path, monkeypatch, code, rc):
    from jibun_kit import cli

    def fake_main(argv):
        raise SystemExit(code)

    monkeypatch.setattr(cli, "main", fake_main)
    ws = _scaffold(tmp_path)
    assert _dispatch_ingest(ws, "gmail", [])[0] == rc
