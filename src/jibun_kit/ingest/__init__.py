"""Ingest source registry.

Maps a CLI source name to the module that exposes
``run(config, args, workspace) -> int`` and ``add_arguments(parser)``.

- Phase 1: claude-code, gmail, line.
- Phase 2: icloudmail, imessage, twitter, twilog, blog.

``telegram`` is intentionally excluded from v1 (upstream stub).
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceGuide:
    """``jibun app`` Act 1 が source を対話的に提案するための宣言情報。

    各 ingest モジュールは ``GUIDE = SourceGuide(...)`` を export する。
    app はこれだけを見て「何が取り込めるか・どう入手するか・何を聞くか」を
    registry 駆動で案内する（モジュール固有の分岐を app 側に書かない）。
    """

    label: str                  # 表示名（例: "X (Twitter) 公式エクスポート"）
    captures: str               # 何が取り込めるか（提案文に使う 1-2 文）
    how_to_get: str             # export の入手手順（そのまま表示、複数行可）
    path_flags: Mapping[str, str] = field(default_factory=dict)
    #   {"file": "--mbox"} / {"dir": "--export-dir"} /
    #   {"file": "--file", "dir": "--raw-dir"} / {} = パス入力不要
    identity_keys: tuple[str, ...] = ()   # 対話で集めて jibun.toml に永続化するキー（ドット表記）
    fixed_argv: tuple[str, ...] = ()      # ingest 実行時に常に付与する固定フラグ
    asks: tuple[str, ...] = ()            # 追加の構造化質問: "date_range" | "urls"
    needs_fetch_extra: bool = False       # [fetch] extra（requests 等）が必要


# name -> dotted module path under jibun_kit.ingest
REGISTRY: dict[str, str] = {
    "claude-code": "jibun_kit.ingest.claude_code",
    "gmail": "jibun_kit.ingest.gmail",
    "icloudmail": "jibun_kit.ingest.icloudmail",
    "imessage": "jibun_kit.ingest.imessage",
    "line": "jibun_kit.ingest.line",
    "twitter": "jibun_kit.ingest.twitter",
    "twilog": "jibun_kit.ingest.twilog",
    "blog": "jibun_kit.ingest.blog",
}


def load_source(name: str):
    """Import and return the ingest module registered under ``name``."""
    return importlib.import_module(REGISTRY[name])
