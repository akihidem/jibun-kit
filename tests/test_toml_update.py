import tomllib

import pytest

from jibun_kit.config import JibunConfig, set_toml_values
from jibun_kit.scaffold import read_template


@pytest.fixture
def toml_path(tmp_path):
    p = tmp_path / "jibun.toml"
    p.write_text(read_template("jibun.toml.template"), encoding="utf-8")
    return p


def test_update_existing_key(toml_path):
    changed = set_toml_values(toml_path, {"identity": {"line_name": "Aki"}})
    assert changed == ["identity.line_name"]
    assert JibunConfig.load(toml_path).line_name == "Aki"
    # template のコメントは生存する
    assert "# LINE トーク履歴上の自分の表示名" in toml_path.read_text(encoding="utf-8")


def test_update_list_value(toml_path):
    set_toml_values(toml_path, {"identity": {"emails": ["a@x.com", "b@y.com"]}})
    assert JibunConfig.load(toml_path).emails == ["a@x.com", "b@y.com"]


def test_update_dotted_section(toml_path):
    set_toml_values(toml_path, {"sources.claude_code": {"projects_root": "~/.claude/projects/x"}})
    assert JibunConfig.load(toml_path).claude_projects_root == "~/.claude/projects/x"


def test_insert_missing_key_into_section(toml_path):
    set_toml_values(toml_path, {"identity": {"brand_new": "v"}})
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    assert data["identity"]["brand_new"] == "v"
    # 既存キーも壊れていない
    assert data["identity"]["imessage_label"] == "Me"


def test_append_missing_section(toml_path):
    set_toml_values(toml_path, {"app": {"locale": "ja"}})
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    assert data["app"]["locale"] == "ja"


def test_bool_and_escaping(toml_path):
    set_toml_values(toml_path, {
        "build": {"diagnostic_stance": True},
        "fetch": {"contact": 'say "hi" \\ こんにちは'},
    })
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    assert data["build"]["diagnostic_stance"] is True
    assert data["fetch"]["contact"] == 'say "hi" \\ こんにちは'


def test_multiline_array_refused(tmp_path):
    p = tmp_path / "jibun.toml"
    p.write_text('[identity]\nemails = [\n  "a@x.com",\n]\n', encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="複数行"):
        set_toml_values(p, {"identity": {"emails": ["b@y.com"]}})
    assert p.read_text(encoding="utf-8") == before  # ファイル未変更


def test_two_sections_one_call(toml_path):
    changed = set_toml_values(toml_path, {
        "identity": {"twilog_user": "aki"},
        "fetch": {"contact": "me@example.com"},
    })
    assert set(changed) == {"identity.twilog_user", "fetch.contact"}
    cfg = JibunConfig.load(toml_path)
    assert cfg.twilog_user == "aki"
    assert cfg.contact == "me@example.com"
