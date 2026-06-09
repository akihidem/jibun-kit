"""Ingest source registry.

Maps a CLI source name to the module that exposes ``run(config, args, workspace) -> int``
and ``add_arguments(parser)``. Populated as sources are ported:

- Phase 0: empty (ingest is a stub).
- Phase 1: claude-code, gmail, line.
- Phase 2: icloudmail, imessage, twitter, twilog, blog.

``telegram`` is intentionally excluded from v1 (upstream stub).
"""

from __future__ import annotations

# name -> dotted module path under jibun_kit.ingest
REGISTRY: dict[str, str] = {}
