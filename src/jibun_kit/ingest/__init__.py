"""Ingest source registry.

Maps a CLI source name to the module that exposes
``run(config, args, workspace) -> int`` and ``add_arguments(parser)``.

- Phase 1: claude-code, gmail, line.
- Phase 2: icloudmail, imessage, twitter, twilog, blog.

``telegram`` is intentionally excluded from v1 (upstream stub).
"""

from __future__ import annotations

import importlib

# name -> dotted module path under jibun_kit.ingest
REGISTRY: dict[str, str] = {
    "claude-code": "jibun_kit.ingest.claude_code",
    "gmail": "jibun_kit.ingest.gmail",
    "line": "jibun_kit.ingest.line",
}


def load_source(name: str):
    """Import and return the ingest module registered under ``name``."""
    return importlib.import_module(REGISTRY[name])
