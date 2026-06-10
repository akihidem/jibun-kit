import argparse
from pathlib import Path

import pytest
from conftest import RAISE_INTERRUPT, ScriptedPrompter

from jibun_kit import claude_cli, cli
from jibun_kit.app import act_interview, wizard
from jibun_kit.app.questions import Question
from jibun_kit.app.state import load_progress
from jibun_kit.workspace import Workspace

FIX = Path(__file__).parent / "fixtures"
QS = (
    Question("a", "§2", "質問A"),
    Question("b", "§3", "質問B"),
    Question("c", "§6", "質問C"),
)


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setattr(act_interview, "QUESTIONS", QS)
    monkeypatch.setattr(claude_cli, "find_claude", lambda: None)
    monkeypatch.setattr(claude_cli, "run_claude",
                        lambda *a, **k: pytest.fail("unexpected egress"))


def _args(tmp_path) -> argparse.Namespace:
    return argparse.Namespace(path=tmp_path)


def test_decline_workspace_exits_clean(tmp_path):
    p = ScriptedPrompter([False, None])  # 作らない → 別パスも空 Enter
    assert wizard.run(_args(tmp_path), prompter=p) == 0
    assert not (tmp_path / "jibun.toml").exists()


def test_full_happy_path_without_claude(tmp_path):
    p = ScriptedPrompter([
        True,                                     # Act0: ここに workspace 作成
        "データの取り込み",                        # menu → Act1
        "スキップ",                                # claude-code
        "取り込む", str(FIX / "twitter"), True,    # twitter: path → dry-run 確認
        "スキップ", "スキップ", "スキップ",          # line, gmail, icloudmail
        "スキップ", "スキップ", "スキップ",          # imessage, twilog, blog
        "インタビュー",                            # menu → Act2
        "私はテストを書いて暮らしています", None, None,  # A 回答 / B・C スキップ
        "ビルド",                                  # menu → Act3（claude 不在 → 貼り付け案内）
        "終了",                                    # menu
    ])
    rc = wizard.run(_args(tmp_path), prompter=p)
    assert rc == 0
    ws = Workspace(tmp_path)
    bundle = next(ws.build_root.glob("*/context-bundle.md")).read_text(encoding="utf-8")
    assert "これは自分のツイート" in bundle            # Act1 の取り込みが合流
    assert "私はテストを書いて暮らしています" in bundle  # Act2 の回答も合流
    assert "interview" in bundle
    # 取り込み結果サマリと貼り付け案内が出ている
    assert "Act 1 の結果" in p.said()
    assert str(ws.jibun_md) in p.said()


def test_interrupt_saves_progress_and_resume(tmp_path):
    p1 = ScriptedPrompter([
        True,             # Act0 scaffold
        "インタビュー",    # menu → Act2
        "回答A",
        RAISE_INTERRUPT,  # 質問B の途中で Ctrl-C
    ])
    rc = wizard.run(_args(tmp_path), prompter=p1)
    assert rc == 130
    ws = Workspace(tmp_path)
    saved = load_progress(ws)
    assert {a.id for a in saved.answers} == {"a"}

    # 再開: a は再質問されない（台本に b/c の分しか無い）
    p2 = ScriptedPrompter([
        True,            # workspace 確認
        True,            # 再開する
        "インタビュー",
        "回答B", "回答C",
        "終了",
    ])
    rc = wizard.run(_args(tmp_path), prompter=p2)
    assert rc == 0
    saved = load_progress(ws)
    assert {a.id for a in saved.answers} == {"a", "b", "c"}
    md = (ws.root / saved.session_md).read_text(encoding="utf-8")
    assert "回答A" in md and "回答B" in md and "回答C" in md


def test_resume_declined_starts_fresh(tmp_path):
    p1 = ScriptedPrompter([True, "インタビュー", "回答A", RAISE_INTERRUPT])
    wizard.run(_args(tmp_path), prompter=p1)
    ws = Workspace(tmp_path)

    p2 = ScriptedPrompter([
        True,
        False,           # 再開しない → progress 破棄
        "インタビュー",
        "新しい回答A", None, None,
        "終了",
    ])
    rc = wizard.run(_args(tmp_path), prompter=p2)
    assert rc == 0
    saved = load_progress(ws)
    assert [a.text for a in saved.answers] == ["新しい回答A"]
    # 最初のセッションの md は .2.md 連番で保護される
    assert saved.session_md.endswith(".2.md")


def test_build_without_data_offers_guidance(tmp_path):
    p = ScriptedPrompter([
        True,        # Act0 scaffold
        "ビルド",     # いきなり Act3
        "終了",
    ])
    rc = wizard.run(_args(tmp_path), prompter=p)
    assert rc == 0
    assert "まだありません" in p.said()


def test_cli_app_smoke(tmp_path, monkeypatch):
    answers = iter(["y", "4"])  # workspace 作成 → menu 番号 4 = 終了
    monkeypatch.setattr("builtins.input", lambda _="": next(answers))
    rc = cli.main(["app", "--path", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "jibun.toml").is_file()
