import json

import pytest
from conftest import RAISE_INTERRUPT, ScriptedPrompter

from jibun_kit import claude_cli
from jibun_kit.app import act_interview
from jibun_kit.app.questions import Question
from jibun_kit.app.state import (
    Answer,
    Progress,
    load_progress,
    progress_path,
    save_progress,
)

DATE = "2026-06-10"
QS = (
    Question("a", "§2", "質問A"),
    Question("b", "§3", "質問B"),
    Question("c", "§6", "質問C"),
)


@pytest.fixture(autouse=True)
def _small_question_set(monkeypatch):
    monkeypatch.setattr(act_interview, "QUESTIONS", QS)
    # 既定では claude 不在（egress 経路に近づかない）。必要なテストで上書きする。
    monkeypatch.setattr(claude_cli, "find_claude", lambda: None)


def _save(ws, progress):
    return lambda: save_progress(ws, progress, now=f"{DATE}T00:00:00")


def test_progress_roundtrip(tmp_workspace):
    pr = Progress(date=DATE, act=2,
                  answers=[Answer(id="a", ts="t", question="q", text="x", section="§2")],
                  skipped=["b"], act1_done=["twitter"])
    save_progress(tmp_workspace, pr, now=f"{DATE}T12:00:00")
    loaded = load_progress(tmp_workspace)
    assert loaded == pr


def test_progress_version_mismatch_returns_none(tmp_workspace):
    p = progress_path(tmp_workspace)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": 99}), encoding="utf-8")
    assert load_progress(tmp_workspace) is None


def test_answers_skip_and_interrupt(tmp_workspace):
    progress = Progress(date=DATE)
    p = ScriptedPrompter(["回答A", None, RAISE_INTERRUPT])  # A 回答 / B スキップ / C で Ctrl-C
    with pytest.raises(KeyboardInterrupt):
        act_interview.run_act2(p, tmp_workspace, progress, _save(tmp_workspace, progress))

    loaded = load_progress(tmp_workspace)
    assert {a.id for a in loaded.answers} == {"a"}
    assert loaded.skipped == ["b"]
    md = (tmp_workspace.root / loaded.session_md).read_text(encoding="utf-8")
    assert "回答A" in md
    assert "**Q (a): 質問A**" in md
    assert "<!-- maps: §2 -->" in md
    # index は件数なしの 1 行（dedup が効く形）
    idx = (tmp_workspace.sources_root / "interview-index.md").read_text(encoding="utf-8")
    assert idx.count("interview /") == 1


def test_resume_asks_only_remaining(tmp_workspace):
    progress = Progress(date=DATE)
    p1 = ScriptedPrompter(["回答A", None, RAISE_INTERRUPT])
    with pytest.raises(KeyboardInterrupt):
        act_interview.run_act2(p1, tmp_workspace, progress, _save(tmp_workspace, progress))

    resumed = load_progress(tmp_workspace)
    # 台本は C の 1 問分だけ。a/b を再質問したら枯渇 AssertionError で落ちる
    p2 = ScriptedPrompter(["回答C"])
    act_interview.run_act2(p2, tmp_workspace, resumed, _save(tmp_workspace, resumed))
    assert {a.id for a in resumed.answers} == {"a", "c"}
    md = (tmp_workspace.root / resumed.session_md).read_text(encoding="utf-8")
    assert "回答A" in md and "回答C" in md
    idx = (tmp_workspace.sources_root / "interview-index.md").read_text(encoding="utf-8")
    assert idx.count("interview /") == 1  # 追記されても 1 行のまま


def test_same_day_second_session_gets_counter(tmp_workspace):
    first = Progress(date=DATE)
    p1 = ScriptedPrompter(["最初のセッション", None, None])
    act_interview.run_act2(p1, tmp_workspace, first, _save(tmp_workspace, first))
    assert first.session_md.endswith(f"{DATE}-interview.md")

    second = Progress(date=DATE)  # 進捗を消して同日にやり直した想定
    p2 = ScriptedPrompter(["夜のセッション", None, None])
    act_interview.run_act2(p2, tmp_workspace, second, _save(tmp_workspace, second))
    assert second.session_md.endswith(f"{DATE}-interview.2.md")
    # 朝のファイルは無傷
    md1 = (tmp_workspace.root / first.session_md).read_text(encoding="utf-8")
    assert "最初のセッション" in md1


def test_claude_followups_parsed_and_recorded(tmp_workspace, monkeypatch):
    monkeypatch.setattr(claude_cli, "find_claude", lambda: "/fake/claude")
    sent: dict = {}

    def fake_run_claude(text, **kw):
        sent["input"] = text
        return "前置きの行\nQ: 深掘り1?\nQ：深掘り2？\nただのノイズ\nQ: 4つ目は出ても捨てる?"

    monkeypatch.setattr(claude_cli, "run_claude", fake_run_claude)
    progress = Progress(date=DATE)
    p = ScriptedPrompter([
        "回答A", None, None,   # 組み込み 3 問（A だけ回答）
        True,                  # egress 同意
        "深掘り回答1",          # claude-1
        None,                  # claude-2 スキップ
        "捨てない3",            # claude-3（cap=3 なので残る）
    ])
    act_interview.run_act2(p, tmp_workspace, progress, _save(tmp_workspace, progress))

    assert "回答A" in sent["input"]  # 回答が追い質問生成に渡った
    ids = [a.id for a in progress.answers]
    assert ids == ["a", "claude-1", "claude-3"]
    assert all(a.claude_generated for a in progress.answers if a.id.startswith("claude-"))
    assert "claude-2" in progress.skipped
    assert [f["text"] for f in progress.claude_followups] == [
        "深掘り1?", "深掘り2？", "4つ目は出ても捨てる?"]
    md = (tmp_workspace.root / progress.session_md).read_text(encoding="utf-8")
    assert "claude生成" in md


def test_consent_default_no_means_no_egress(tmp_workspace, monkeypatch):
    monkeypatch.setattr(claude_cli, "find_claude", lambda: "/fake/claude")
    called: list[int] = []
    monkeypatch.setattr(claude_cli, "run_claude", lambda *a, **k: called.append(1))
    progress = Progress(date=DATE)
    p = ScriptedPrompter(["回答A", None, None, False])  # 同意しない
    act_interview.run_act2(p, tmp_workspace, progress, _save(tmp_workspace, progress))
    assert not called


def test_no_claude_no_consent_question(tmp_workspace):
    # find_claude → None（autouse fixture）。consent の confirm が来たら台本枯渇で落ちる
    progress = Progress(date=DATE)
    p = ScriptedPrompter(["回答A", None, None])
    act_interview.run_act2(p, tmp_workspace, progress, _save(tmp_workspace, progress))
    assert {a.id for a in progress.answers} == {"a"}


def test_followup_zero_parse_continues(tmp_workspace, monkeypatch):
    monkeypatch.setattr(claude_cli, "find_claude", lambda: "/fake/claude")
    monkeypatch.setattr(claude_cli, "run_claude", lambda *a, **k: "Q なしの自由文だけ")
    progress = Progress(date=DATE)
    p = ScriptedPrompter(["回答A", None, None, True])
    act_interview.run_act2(p, tmp_workspace, progress, _save(tmp_workspace, progress))
    assert "生成されませんでした" in p.said()
    assert progress.claude_followups == []


def test_resume_reuses_persisted_followups_without_claude(tmp_workspace):
    # 前回 followup を生成済み → 再開時は claude 不在でも残りを聞ける（再送信なし）
    progress = Progress(date=DATE,
                        answers=[Answer(id="a", ts="t", question="質問A", text="回答A",
                                        section="§2")],
                        skipped=["b", "c"],
                        claude_followups=[{"id": "claude-1", "text": "深掘り?"}])
    progress.session_md = ""  # まだ md 未作成でも動く
    p = ScriptedPrompter(["深掘り回答"])
    act_interview.run_act2(p, tmp_workspace, progress, _save(tmp_workspace, progress))
    assert [a.id for a in progress.answers] == ["a", "claude-1"]


@pytest.mark.parametrize("bad", [
    {"answers": [{"id": "q1"}]},   # 必須キー欠落
    {"act": "x"},
    {"act": None},
    {"skipped": 3},
])
def test_progress_malformed_fields_returns_none(tmp_workspace, bad):
    p = progress_path(tmp_workspace)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": 1, **bad}), encoding="utf-8")
    assert load_progress(tmp_workspace) is None
