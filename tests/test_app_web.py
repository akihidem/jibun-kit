import argparse
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from jibun_kit import claude_cli, cli
from jibun_kit.app import act_interview, web
from jibun_kit.app.questions import Question
from jibun_kit.app.state import load_progress
from jibun_kit.app.web import AppServer, WebPrompter
from jibun_kit.workspace import Workspace

QS = (Question("a", "§2", "質問A"),)


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setattr(act_interview, "QUESTIONS", QS)
    monkeypatch.setattr(claude_cli, "find_claude", lambda: None)
    monkeypatch.setattr(claude_cli, "run_claude",
                        lambda *a, **k: pytest.fail("unexpected egress"))
    monkeypatch.setattr("webbrowser.open", lambda *a, **k: True)


def wait_for(cond, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return False


def _in_thread(fn):
    """fn を別スレッドで実行し (thread, result_box) を返す。"""
    box: dict = {}

    def target():
        try:
            box["value"] = fn()
        except BaseException as e:  # KeyboardInterrupt を捕まえるため BaseException
            box["exc"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    return t, box


def _pending(p: WebPrompter):
    return p.snapshot(0)["pending"]


# --- WebPrompter 単体（HTTP なし） ---

def test_ask_happy_path():
    p = WebPrompter()
    t, box = _in_thread(lambda: p.ask("名前は？", default="x"))
    assert wait_for(lambda: _pending(p) is not None)
    desc = _pending(p)
    assert desc["ptype"] == "ask" and desc["id"] == 1
    assert desc["text"] == "名前は？" and desc["default"] == "x"
    assert desc["multiline"] is False
    assert p.deliver(1, "  答え  ") == "ok"
    t.join(timeout=5)
    assert box["value"] == "答え"
    snap = p.snapshot(0)
    assert [e["kind"] for e in snap["entries"]] == ["prompt", "answer"]
    assert snap["entries"][1]["display"] == "答え"
    assert snap["pending"] is None


def test_ask_empty_takes_default_and_skip_display():
    p = WebPrompter()
    t, box = _in_thread(lambda: p.ask("q", default="既定値"))
    wait_for(lambda: _pending(p) is not None)
    assert p.deliver(1, "") == "ok"
    t.join(timeout=5)
    assert box["value"] == "既定値"
    assert p.snapshot(0)["entries"][1]["display"] == "既定値"

    t2, box2 = _in_thread(lambda: p.ask("q2"))  # default なし + 空 = スキップ
    wait_for(lambda: _pending(p) is not None)
    assert p.deliver(2, "   ") == "ok"
    t2.join(timeout=5)
    assert box2["value"] == ""
    assert p.snapshot(0)["entries"][3]["display"] == "（スキップ）"


def test_confirm_type_validation():
    p = WebPrompter()
    t, box = _in_thread(lambda: p.confirm("q", default=True))
    wait_for(lambda: _pending(p) is not None)
    assert p.deliver(1, "yes") == "invalid"
    assert p.deliver(1, 1) == "invalid"      # bool/int 罠: int は拒否
    assert _pending(p) is not None           # invalid では pending 維持
    assert p.deliver(1, False) == "ok"
    t.join(timeout=5)
    assert box["value"] is False
    assert p.snapshot(0)["entries"][1]["display"] == "いいえ"


def test_choose_range_and_type():
    p = WebPrompter()
    t, box = _in_thread(lambda: p.choose("q", ["a", "b", "c"]))
    wait_for(lambda: _pending(p) is not None)
    assert _pending(p)["options"] == ["a", "b", "c"]
    assert p.deliver(1, 5) == "invalid"      # 範囲外 → reject、pending 維持
    assert p.deliver(1, -1) == "invalid"
    assert p.deliver(1, True) == "invalid"   # bool は choose でも拒否
    assert _pending(p) is not None
    assert p.deliver(1, 1) == "ok"
    t.join(timeout=5)
    assert box["value"] == 1
    assert p.snapshot(0)["entries"][1]["display"] == "b"


def test_stale_and_duplicate_answers():
    p = WebPrompter()
    t, _ = _in_thread(lambda: p.ask("q"))
    wait_for(lambda: _pending(p) is not None)
    assert p.deliver(999, "x") == "stale"    # 知らない id
    assert p.deliver("1", "x") == "stale"    # 型違い id
    assert p.deliver(1, "x") == "ok"
    assert p.deliver(1, "y") == "stale"      # 二重回答（2 タブの負け側）
    t.join(timeout=5)


def test_abort_while_blocked():
    p = WebPrompter()
    t, box = _in_thread(lambda: p.ask("q"))
    wait_for(lambda: _pending(p) is not None)
    p.request_abort()
    t.join(timeout=5)
    assert isinstance(box.get("exc"), KeyboardInterrupt)
    snap = p.snapshot(0)
    assert snap["pending"] is None
    assert any("中断" in e.get("text", "") for e in snap["entries"])


def test_abort_while_idle_fires_on_next_prompt():
    p = WebPrompter()
    p.request_abort()  # pending なし（claude 実行中相当）
    t, box = _in_thread(lambda: p.confirm("q"))
    t.join(timeout=5)
    assert isinstance(box.get("exc"), KeyboardInterrupt)


def test_snapshot_cursor():
    p = WebPrompter()
    p.say("a")
    p.say("b")
    snap = p.snapshot(0)
    assert snap["next"] == 2 and len(snap["entries"]) == 2
    assert p.snapshot(2)["entries"] == []
    p.say("c")
    snap2 = p.snapshot(2)
    assert snap2["next"] == 3 and snap2["entries"][0]["text"] == "c"


# --- ライブサーバ統合 ---

def _start_server(tmp_path, grace=0.5):
    args = argparse.Namespace(path=tmp_path, port=0, web=True, no_browser=True)
    server = AppServer(args, grace=grace)
    box: dict = {}

    def run():
        box["rc"] = server.serve()

    server.start_wizard()
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return server, t, box


def _api(port, path, token, *, body=None, method=None, host=None):
    """(status, payload) を返す urllib ラッパー。"""
    url = f"http://127.0.0.1:{port}{path}"
    headers = {}
    if token is not None:
        headers["X-Jibun-Token"] = token
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        url, data=data, headers=headers,
        method=method or ("POST" if body is not None else "GET"))
    if host:
        req.add_header("Host", host)  # urllib は Host が既にあれば上書きしない
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
            ctype = resp.headers.get("Content-Type", "")
            return resp.status, json.loads(raw) if ctype.startswith("application/json") else raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def _pending_via(server):
    return server.prompter.snapshot(0)["pending"]


def _wait_pending(server, ptype=None):
    def cond():
        p = _pending_via(server)
        return p is not None and (ptype is None or p["ptype"] == ptype)
    assert wait_for(cond), f"pending ({ptype}) が来ない"
    return _pending_via(server)


def _wait_done_fetched(server, tok, box, expected_rc):
    """done を /api/state で受け取るまで待つ。直後の自動停止と競合したら rc で判定。"""
    def cond():
        try:
            s, j = _api(server.port, "/api/state?since=0", tok)
        except OSError:  # サーバが先に止まった = done は配信済み（grace 経過）
            return box.get("rc") == expected_rc
        return s == 200 and isinstance(j, dict) and bool(j.get("done"))
    assert wait_for(cond), "done が来ない"


def test_happy_path_done_and_autostop(tmp_path):
    server, t, box = _start_server(tmp_path)
    tok = server.prompter.state.token

    status, html = _api(server.port, "/", None)
    assert status == 200
    assert tok in html              # token 埋め込み
    assert "https://" not in html   # 外部参照ゼロ
    assert "{{TOKEN}}" not in html

    p1 = _wait_pending(server, "confirm")  # Act0: workspace 作成確認
    status, _ = _api(server.port, "/api/answer", tok,
                     body={"prompt_id": p1["id"], "value": True})
    assert status == 200

    p2 = _wait_pending(server, "choose")   # メニュー
    idx = next(i for i, o in enumerate(p2["options"]) if "終了" in o)
    status, _ = _api(server.port, "/api/answer", tok,
                     body={"prompt_id": p2["id"], "value": idx})
    assert status == 200

    _wait_done_fetched(server, tok, box, 0)
    t.join(timeout=5)                      # done 配信 → 自動シャットダウン
    assert not t.is_alive()
    assert box["rc"] == 0
    assert (tmp_path / "jibun.toml").is_file()  # Act0 の scaffold は本当に走った


def test_replay_from_zero_mid_wizard(tmp_path):
    server, _t, _box = _start_server(tmp_path)
    tok = server.prompter.state.token
    p1 = _wait_pending(server, "confirm")
    _api(server.port, "/api/answer", tok, body={"prompt_id": p1["id"], "value": True})
    _wait_pending(server, "choose")
    s, j = _api(server.port, "/api/state?since=0", tok)  # 別タブ相当の全再生
    assert s == 200
    kinds = [e["kind"] for e in j["entries"]]
    assert "prompt" in kinds and "answer" in kinds
    assert j["pending"]["ptype"] == "choose"


def test_token_and_host_guards(tmp_path):
    server, _t, _box = _start_server(tmp_path)
    tok = server.prompter.state.token
    assert _api(server.port, "/api/state?since=0", None)[0] == 403
    assert _api(server.port, "/api/state?since=0", "wrong")[0] == 403
    p1 = _wait_pending(server, "confirm")
    assert _api(server.port, "/api/answer", "wrong",
                body={"prompt_id": p1["id"], "value": True})[0] == 403
    assert _api(server.port, "/", None, host="evil.example")[0] == 403
    assert _api(server.port, "/api/state?since=0", tok)[0] == 200  # 正規は通る
    assert _api(server.port, "/nope", tok)[0] == 404
    assert _api(server.port, "/api/answer", tok)[0] == 405  # GET は不可


def test_duplicate_answer_409_advances_once(tmp_path):
    server, _t, _box = _start_server(tmp_path)
    tok = server.prompter.state.token
    p1 = _wait_pending(server, "confirm")
    assert _api(server.port, "/api/answer", tok,
                body={"prompt_id": p1["id"], "value": True})[0] == 200
    # 2 タブの負け側（同じ prompt にもう一度）
    assert _api(server.port, "/api/answer", tok,
                body={"prompt_id": p1["id"], "value": False})[0] == 409
    p2 = _wait_pending(server, "choose")
    assert p2["id"] == p1["id"] + 1  # wizard は 1 回だけ進んだ


def test_choose_out_of_range_400_then_answerable(tmp_path):
    server, t, box = _start_server(tmp_path)
    tok = server.prompter.state.token
    p1 = _wait_pending(server, "confirm")
    _api(server.port, "/api/answer", tok, body={"prompt_id": p1["id"], "value": True})
    p2 = _wait_pending(server, "choose")
    assert _api(server.port, "/api/answer", tok,
                body={"prompt_id": p2["id"], "value": 99})[0] == 400
    assert _api(server.port, "/api/answer", tok, body={"bogus": 1})[0] == 400
    idx = next(i for i, o in enumerate(p2["options"]) if "終了" in o)
    assert _api(server.port, "/api/answer", tok,
                body={"prompt_id": p2["id"], "value": idx})[0] == 200  # pending は生きていた
    t.join(timeout=5)
    assert box["rc"] == 0


def test_abort_saves_progress_rc130(tmp_path):
    server, t, box = _start_server(tmp_path)
    tok = server.prompter.state.token
    p1 = _wait_pending(server, "confirm")
    _api(server.port, "/api/answer", tok, body={"prompt_id": p1["id"], "value": True})
    menu = _wait_pending(server, "choose")
    idx = next(i for i, o in enumerate(menu["options"]) if "インタビュー" in o)
    _api(server.port, "/api/answer", tok, body={"prompt_id": menu["id"], "value": idx})
    q = _wait_pending(server, "ask")  # 質問A
    _api(server.port, "/api/answer", tok, body={"prompt_id": q["id"], "value": "回答A"})
    _wait_pending(server, "choose")   # 次のメニューで中断
    assert _api(server.port, "/api/abort", tok, body={})[0] == 200
    _wait_done_fetched(server, tok, box, 130)
    t.join(timeout=5)
    assert box["rc"] == 130
    saved = load_progress(Workspace(tmp_path))
    assert saved is not None and [a.id for a in saved.answers] == ["a"]


def test_autostop_without_any_poll(tmp_path):
    # ブラウザを一度も開かなくても grace 超過で必ず終了する
    server, t, box = _start_server(tmp_path, grace=0.3)
    p1 = _wait_pending(server, "confirm")
    assert server.prompter.deliver(p1["id"], True) == "ok"
    p2 = _wait_pending(server, "choose")
    idx = next(i for i, o in enumerate(p2["options"]) if "終了" in o)
    assert server.prompter.deliver(p2["id"], idx) == "ok"
    t.join(timeout=5)
    assert not t.is_alive()
    assert box["rc"] == 0


# --- 配線・packaging ---

def test_webui_html_packaged():
    html = web._load_html()
    assert "{{TOKEN}}" in html
    assert "https://" not in html  # 外部アセットなし


def test_cli_routes_web(monkeypatch, tmp_path):
    called: dict = {}

    def fake_run_web(args):
        called["args"] = args
        return 0

    monkeypatch.setattr(web, "run_web", fake_run_web)
    rc = cli.main(["app", "--web", "--no-browser", "--port", "0", "--path", str(tmp_path)])
    assert rc == 0
    assert called["args"].web is True and called["args"].port == 0


def test_cli_without_web_routes_wizard(monkeypatch, tmp_path):
    import jibun_kit.app.wizard as wizard_mod
    monkeypatch.setattr(wizard_mod, "run", lambda args, prompter=None: 0)
    assert cli.main(["app", "--path", str(tmp_path)]) == 0


def test_index_sends_framing_protection(tmp_path):
    # 他サイトの iframe に埋め込ませない（clickjacking 対策）
    server, _t, _box = _start_server(tmp_path)
    req = urllib.request.Request(f"http://127.0.0.1:{server.port}/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Content-Security-Policy") == "frame-ancestors 'none'"
