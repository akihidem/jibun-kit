"""Config 読み込みと解決順 (CLI > jibun.toml > env > default)。

``jibun.toml`` は stdlib :mod:`tomllib` で読む（書き込みは template 文字列で行うので
``tomli-w`` 依存は不要）。identity を一度設定すれば各 ingest がそこから既定値を引く。
"""

from __future__ import annotations

import os
import tomllib
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
