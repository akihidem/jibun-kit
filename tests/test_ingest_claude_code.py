import argparse
from pathlib import Path

from jibun_kit import cli
from jibun_kit.config import JibunConfig
from jibun_kit.ingest import claude_code

FIX = Path(__file__).parent / "fixtures" / "claude_code"


def _args(**kw):
    base = dict(projects_root=FIX, session=None, all=True, since=None, until=None,
                dry_run=False, verbose=False)
    base.update(kw)
    return argparse.Namespace(**base)


def test_run_extracts_operator_only(tmp_workspace):
    rc = claude_code.run(JibunConfig(), _args(), tmp_workspace)
    assert rc == 0
    out = tmp_workspace.data_root / "claude-code" / "2026-05" / "sample-session.md"
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "hello this is me" in text          # str user message
    assert "second real message" in text       # list-with-text user message
    # excluded:
    assert "sidechain text" not in text         # isSidechain
    assert "assistant reply" not in text        # type != user
    assert "<system-reminder>" not in text      # meta tag
    assert "toolout" not in text                # tool_result part dropped
    idx = (tmp_workspace.sources_root / "claude-code-index.md").read_text(encoding="utf-8")
    assert "session=sample-session" in idx
    assert "2 messages" in idx


def test_dry_run_writes_nothing(tmp_workspace):
    rc = claude_code.run(JibunConfig(), _args(dry_run=True), tmp_workspace)
    assert rc == 0
    assert not (tmp_workspace.data_root / "claude-code" / "2026-05" / "sample-session.md").exists()
    assert not (tmp_workspace.sources_root / "claude-code-index.md").exists()


def test_missing_projects_root_errors(tmp_workspace):
    # no CLI root, no config root -> unresolved
    rc = claude_code.run(JibunConfig(), _args(projects_root=None), tmp_workspace)
    assert rc == 2


def test_cli_dispatch_end_to_end(tmp_path):
    rc = cli.main(["ingest", "claude-code", "--path", str(tmp_path),
                   "--projects-root", str(FIX), "--all"])
    assert rc == 0
    assert (tmp_path / "data" / "claude-code" / "2026-05" / "sample-session.md").is_file()
