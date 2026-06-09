from datetime import datetime

from jibun_kit import common


def test_is_meta_tag():
    assert common.is_meta_tag("<system-reminder>foo")
    assert common.is_meta_tag("  <command-name>/x")  # leading ws stripped
    assert common.is_meta_tag("[tool_result] ...")
    assert not common.is_meta_tag("hello world")
    assert not common.is_meta_tag(123)  # non-str -> False


def test_extract_text_parts():
    assert common.extract_text_parts("plain") == "plain"
    content = [
        {"type": "text", "text": "a"},
        {"type": "tool_result", "content": "x"},  # dropped
        {"type": "text", "text": "b"},
        "not-a-dict",  # ignored
    ]
    assert common.extract_text_parts(content) == "a\n\nb"
    assert common.extract_text_parts({"weird": 1}) == ""  # non-list, non-str


def test_iter_jsonl_skips_broken(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text('{"a": 1}\n\nnot json\n{"b": 2}\n', encoding="utf-8")
    assert list(common.iter_jsonl(p)) == [{"a": 1}, {"b": 2}]


def test_data_dir(tmp_workspace):
    d = common.data_dir(tmp_workspace, "claude-code", "2026-05-11")
    assert d == tmp_workspace.data_root / "claude-code" / "2026-05"
    assert d.is_dir()
    d2 = common.data_dir(tmp_workspace, "x", datetime(2026, 1, 2))
    assert d2.name == "2026-01"


def test_append_index_dedup(tmp_workspace):
    common.append_index(tmp_workspace, "gmail", "- 2026-05-11 foo")
    common.append_index(tmp_workspace, "gmail", "- 2026-05-11 foo")  # dup ignored
    common.append_index(tmp_workspace, "gmail", "- 2026-05-12 bar")
    idx = (tmp_workspace.sources_root / "gmail-index.md").read_text(encoding="utf-8")
    assert idx.count("- 2026-05-11 foo") == 1
    assert "- 2026-05-12 bar" in idx


def test_write_session_md_empty_returns_zero(tmp_path):
    p = tmp_path / "s.md"
    assert common.write_session_md(p, {"title": "t", "date": "2026-05-11"}, []) == 0
    assert not p.exists()


def test_write_session_md_writes_and_skips_blank(tmp_path):
    p = tmp_path / "s.md"
    n = common.write_session_md(
        p,
        {"title": "session x", "date": "2026-05-11"},
        [("2026-05-11T00:00:00Z", "hello"), ("ts2", "   ")],  # blank body skipped
    )
    assert n == 1
    text = p.read_text(encoding="utf-8")
    assert "# session x" in text
    assert "- date: 2026-05-11" in text
    assert "hello" in text
