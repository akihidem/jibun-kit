import threading
import time

from jibun_kit.app.web import WebPrompter


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
