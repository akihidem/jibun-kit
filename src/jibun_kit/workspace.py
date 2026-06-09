"""Workspace root resolution and path helpers.

Replaces the import-time module globals (``JIBUN_ROOT`` / ``DATA_ROOT`` / ``SOURCES_ROOT``)
that the original ``jibun/tools/common.py`` used. The root is resolved once
(CLI ``--path`` > ``$JIBUN_ROOT`` env > upward discovery > CWD) and threaded explicitly
into the pure helpers in :mod:`jibun_kit.common`, so tests can inject a tmp workspace
without environment hacks.
"""

from __future__ import annotations

import os
from pathlib import Path

CONFIG_FILENAME = "jibun.toml"


class Workspace:
    """A jibun workspace rooted at a directory that holds ``jibun.toml``."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()

    # --- derived paths ---
    @property
    def data_root(self) -> Path:
        """Raw ingested markdown lives here (gitignored)."""
        return self.root / "data"

    @property
    def sources_root(self) -> Path:
        """Tracked per-source metadata indexes live here."""
        return self.root / "sources"

    @property
    def build_root(self) -> Path:
        """`jibun build` staging output."""
        return self.root / "_build"

    @property
    def jibun_md(self) -> Path:
        """The single dual-readable self-understanding markdown."""
        return self.root / "jibun.md"

    @property
    def config_path(self) -> Path:
        return self.root / CONFIG_FILENAME

    def is_initialized(self) -> bool:
        return self.config_path.is_file()

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"Workspace({self.root})"


def find_workspace_root(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` (or CWD) looking for a directory containing ``jibun.toml``."""
    cur = (start or Path.cwd()).expanduser().resolve()
    for d in (cur, *cur.parents):
        if (d / CONFIG_FILENAME).is_file():
            return d
    return None


def resolve_workspace(cli_path: Path | str | None = None) -> Workspace:
    """Resolve the workspace root.

    Order: explicit ``--path`` > ``$JIBUN_ROOT`` env > upward discovery from CWD > CWD.
    ``$JIBUN_ROOT`` is honored for back-compat with the original ``jibun`` repo author.
    """
    if cli_path is not None:
        return Workspace(cli_path)
    env = os.environ.get("JIBUN_ROOT")
    if env:
        return Workspace(env)
    found = find_workspace_root()
    if found is not None:
        return Workspace(found)
    return Workspace(Path.cwd())
