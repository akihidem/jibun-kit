import pytest

from jibun_kit.config import JibunConfig, resolve
from jibun_kit.scaffold import scaffold_workspace
from jibun_kit.workspace import Workspace


def test_load_missing_returns_defaults(tmp_path):
    cfg = JibunConfig.load(tmp_path / "nope.toml")
    assert cfg.emails == []
    assert cfg.imessage_label == "Me"
    assert cfg.diagnostic_stance is False
    assert cfg.default_effort == "high"


def test_from_dict_parses_sections():
    cfg = JibunConfig.from_dict({
        "identity": {"emails": ["a@x.com"], "line_name": "Aki", "twilog_user": "h"},
        "sources": {"claude_code": {"projects_root": "/p"}},
        "fetch": {"contact": "a@x.com"},
        "build": {"diagnostic_stance": True, "default_effort": "low"},
    })
    assert cfg.emails == ["a@x.com"]
    assert cfg.line_name == "Aki"
    assert cfg.claude_projects_root == "/p"
    assert cfg.contact == "a@x.com"
    assert cfg.diagnostic_stance is True
    assert cfg.default_effort == "low"


def test_resolve_order(monkeypatch):
    assert resolve("cli", "cfg", "JK_ENVV", "def") == "cli"        # CLI wins
    assert resolve("", "cfg", "JK_ENVV", "def") == "cfg"           # config next
    monkeypatch.setenv("JK_ENVV", "envval")
    assert resolve("", "", "JK_ENVV", "def") == "envval"           # env next
    monkeypatch.delenv("JK_ENVV", raising=False)
    assert resolve("", "", "JK_ENVV", "def") == "def"              # default last
    assert resolve(None, [], None, "def") == "def"                 # empties skipped


def test_init_scaffolds_and_loads(tmp_path):
    ws = Workspace(tmp_path / "ws")
    scaffold_workspace(ws)
    assert ws.config_path.is_file()
    assert ws.jibun_md.is_file()
    assert (ws.root / ".gitignore").is_file()
    assert ws.data_root.is_dir() and ws.sources_root.is_dir()
    # the template parses as valid TOML and yields template defaults
    cfg = JibunConfig.load(ws.config_path)
    assert cfg.imessage_label == "Me"
    assert cfg.diagnostic_stance is False


def test_init_refuses_clobber_unless_force(tmp_path):
    ws = Workspace(tmp_path / "ws")
    scaffold_workspace(ws)
    with pytest.raises(FileExistsError):
        scaffold_workspace(ws)
    scaffold_workspace(ws, force=True)  # force overwrites without raising
