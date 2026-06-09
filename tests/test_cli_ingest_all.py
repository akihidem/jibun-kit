from pathlib import Path

from jibun_kit import cli

CC = Path(__file__).parent / "fixtures" / "claude_code"


def test_ingest_all_runs_claude_from_config(tmp_path, capsys):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "jibun.toml").write_text(
        f'[sources.claude_code]\nprojects_root = "{CC}"\n', encoding="utf-8")
    rc = cli.main(["ingest", "all", "--path", str(ws)])
    assert rc == 0
    assert (ws / "data" / "claude-code" / "2026-05" / "sample-session.md").is_file()
    out = capsys.readouterr().out
    assert "ran [claude-code" in out
    # export-based sources は個別実行を促す（黙ってスキップしない）
    assert "run individually" in out


def test_ingest_all_skips_claude_without_config(tmp_path, capsys):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "jibun.toml").write_text("", encoding="utf-8")
    rc = cli.main(["ingest", "all", "--path", str(ws)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ran [none]" in out
    assert "projects_root" in out  # claude-code skipped with reason
