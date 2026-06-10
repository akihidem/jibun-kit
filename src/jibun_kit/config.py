"""Config 読み込みと解決順 (CLI > jibun.toml > env > default)。

``jibun.toml`` は stdlib :mod:`tomllib` で読む（書き込みは template 文字列で行うので
``tomli-w`` 依存は不要）。identity を一度設定すれば各 ingest がそこから既定値を引く。
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_UNSET = (None, "", [], ())


@dataclass
class JibunConfig:
    """``jibun.toml`` の内容を保持。欠落キーは安全な既定で埋める。"""

    emails: list[str] = field(default_factory=list)
    email_pattern: str = ""
    line_name: str = ""
    imessage_label: str = "Me"
    twilog_user: str = ""
    claude_projects_root: str = ""
    contact: str = ""
    diagnostic_stance: bool = False
    default_effort: str = "high"
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JibunConfig":
        identity = data.get("identity") or {}
        sources = data.get("sources") or {}
        claude = (sources.get("claude_code") or {}) if isinstance(sources, dict) else {}
        fetch = data.get("fetch") or {}
        build = data.get("build") or {}
        return cls(
            emails=list(identity.get("emails") or []),
            email_pattern=identity.get("email_pattern") or "",
            line_name=identity.get("line_name") or "",
            imessage_label=identity.get("imessage_label") or "Me",
            twilog_user=identity.get("twilog_user") or "",
            claude_projects_root=claude.get("projects_root") or "",
            contact=fetch.get("contact") or "",
            diagnostic_stance=bool(build.get("diagnostic_stance", False)),
            default_effort=build.get("default_effort") or "high",
            raw=data,
        )

    @classmethod
    def load(cls, config_path: Path) -> "JibunConfig":
        """``config_path`` を読む。無ければ全既定の空 config を返す。"""
        if config_path.is_file():
            with config_path.open("rb") as f:
                data = tomllib.load(f)
            return cls.from_dict(data)
        return cls()


def resolve(cli_value: Any, config_value: Any, env_var: str | None = None, default: Any = None) -> Any:
    """解決順: CLI > config > env > default。

    空文字 / 空 list / None は「未指定」として次の候補に進む。
    """
    if cli_value not in _UNSET:
        return cli_value
    if config_value not in _UNSET:
        return config_value
    if env_var:
        env = os.environ.get(env_var)
        if env not in (None, ""):
            return env
    return default


# --- 書き込み側（jibun app が identity を対話で永続化するときに使う） ---

_SECTION_RE = re.compile(r"^\[(?P<name>[^\]]+)\]\s*(?:#.*)?$")


def _toml_repr(value: Any) -> str:
    """:func:`set_toml_values` 用の最小 TOML 値表現。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        # JSON の文字列エスケープは TOML basic string としても妥当
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_repr(v) for v in value) + "]"
    raise TypeError(f"unsupported TOML value type: {type(value).__name__}")


def _section_bounds(lines: list[str], section: str) -> tuple[int | None, int]:
    """``[section]`` ヘッダ行の index と節の終端（次ヘッダ or EOF）を返す。無ければ (None, len)。"""
    start = None
    for i, line in enumerate(lines):
        m = _SECTION_RE.match(line.strip())
        if not m:
            continue
        if m.group("name").strip() == section:
            start = i
        elif start is not None:
            return start, i
    return start, len(lines)


def set_toml_values(config_path: Path, updates: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """``jibun.toml`` の既存行を最小編集で更新する（コメント・手編集を保存）。

    updates 例::

        {"identity": {"line_name": "Aki", "emails": ["a@x.com"]},
         "sources.claude_code": {"projects_root": "~/.claude/projects/x"}}

    - 既存キー行は丸ごと置換、無いキーは節ヘッダ直後に挿入、無い節は末尾に追記
    - 手書きの複数行 array に当たったら壊さず ValueError（手動編集を案内）
    - 書き込み前に全文を tomllib で検証。不正なら ValueError でファイル未変更
    - 返り値: 変更/追加した "section.key" のリスト
    """
    text = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    lines = text.splitlines(keepends=True)
    changed: list[str] = []

    for section, kv in updates.items():
        for key, value in kv.items():
            rendered = f"{key} = {_toml_repr(value)}\n"
            start, end = _section_bounds(lines, section)
            if start is None:
                if lines and not lines[-1].endswith("\n"):
                    lines[-1] += "\n"
                lines.extend(["\n", f"[{section}]\n", rendered])
            else:
                key_re = re.compile(rf"^\s*{re.escape(key)}\s*=")
                for i in range(start + 1, end):
                    if lines[i].lstrip().startswith("#") or not key_re.match(lines[i]):
                        continue
                    if lines[i].count("[") != lines[i].count("]"):
                        raise ValueError(
                            f"{section}.{key} は複数行の値のため自動更新できません。"
                            f"jibun.toml を直接編集してください。")
                    lines[i] = rendered
                    break
                else:
                    lines.insert(start + 1, rendered)
            changed.append(f"{section}.{key}")

    new_text = "".join(lines)
    try:
        tomllib.loads(new_text)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"jibun.toml の更新結果が不正な TOML になるため中止: {e}") from e
    config_path.write_text(new_text, encoding="utf-8")
    return changed
