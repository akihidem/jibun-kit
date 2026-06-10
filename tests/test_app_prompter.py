from jibun_kit.app.prompter import StdioPrompter, confirm_egress


def _feed(monkeypatch, answers):
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(it))


def test_confirm_variants(monkeypatch):
    p = StdioPrompter()
    _feed(monkeypatch, ["y"])
    assert p.confirm("q") is True
    _feed(monkeypatch, ["はい"])
    assert p.confirm("q") is True
    _feed(monkeypatch, ["いいえ"])
    assert p.confirm("q", default=True) is False
    _feed(monkeypatch, [""])
    assert p.confirm("q", default=True) is True
    _feed(monkeypatch, [""])
    assert p.confirm("q", default=False) is False


def test_confirm_reasks_on_garbage(monkeypatch, capsys):
    p = StdioPrompter()
    _feed(monkeypatch, ["maybe", "n"])
    assert p.confirm("q") is False
    assert "y / n" in capsys.readouterr().out


def test_choose_reasks_then_accepts(monkeypatch, capsys):
    p = StdioPrompter()
    _feed(monkeypatch, ["abc", "9", "2"])
    assert p.choose("pick", ["a", "b", "c"]) == 1
    out = capsys.readouterr().out
    assert "1〜3" in out


def test_choose_empty_takes_default(monkeypatch):
    p = StdioPrompter()
    _feed(monkeypatch, [""])
    assert p.choose("pick", ["a", "b"], default=1) == 1


def test_ask_default(monkeypatch):
    p = StdioPrompter()
    _feed(monkeypatch, [""])
    assert p.ask("q", default="x") == "x"
    _feed(monkeypatch, ["  hello  "])
    assert p.ask("q") == "hello"


def test_ask_multiline_ends_on_blank(monkeypatch):
    p = StdioPrompter()
    _feed(monkeypatch, ["a", "b", ""])
    assert p.ask("q", multiline=True) == "a\nb"
    _feed(monkeypatch, [""])
    assert p.ask("q", multiline=True, default="") == ""


def test_confirm_egress_default_no(monkeypatch, capsys):
    p = StdioPrompter()
    _feed(monkeypatch, [""])
    assert confirm_egress(p, "テスト送信") is False
    out = capsys.readouterr().out
    assert "外部送信" in out
    assert "テスト送信" in out
    assert "[y/N]" in out
