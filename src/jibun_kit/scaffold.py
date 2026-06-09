"""``jibun init`` — workspace を package template から scaffold する。"""

from __future__ import annotations

from importlib import resources

from jibun_kit.workspace import Workspace


def read_template(name: str) -> str:
    """``src/jibun_kit/templates/<name>`` をパッケージデータとして読む。

    ``templates`` を package 化せず、確実に package である ``jibun_kit`` 経由で辿る。
    """
    return resources.files("jibun_kit").joinpath("templates").joinpath(name).read_text(encoding="utf-8")


def read_prompt(name: str) -> str:
    """``src/jibun_kit/prompts/<name>`` をパッケージデータとして読む。"""
    return resources.files("jibun_kit").joinpath("prompts").joinpath(name).read_text(encoding="utf-8")


def scaffold_workspace(ws: Workspace, *, force: bool = False) -> list[str]:
    """workspace を scaffold し、作成/更新したパスのリストを返す。

    既存の ``jibun.toml`` は ``force=False`` なら上書きしない（:class:`FileExistsError`）。
    既存の ``jibun.md`` / ``.gitignore`` は決して上書きしない（ユーザーの編集を守る）。
    ``data/`` 配下は一切消さない。
    """
    if ws.config_path.exists() and not force:
        raise FileExistsError(
            f"{ws.config_path} already exists. Use --force to overwrite jibun.toml "
            f"(data/ は消しません)."
        )
    created: list[str] = []
    ws.root.mkdir(parents=True, exist_ok=True)

    # data/ (gitignored) と sources/ (tracked) に .gitkeep を置く
    for d in (ws.data_root, ws.sources_root):
        d.mkdir(parents=True, exist_ok=True)
        keep = d / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")
    created.append(str(ws.data_root))
    created.append(str(ws.sources_root))

    # jibun.toml（force のときのみ上書き）
    ws.config_path.write_text(read_template("jibun.toml.template"), encoding="utf-8")
    created.append(str(ws.config_path))

    # jibun.md starter（既存は触らない）
    if not ws.jibun_md.exists():
        ws.jibun_md.write_text(read_template("jibun.starter.md"), encoding="utf-8")
        created.append(str(ws.jibun_md))

    # .gitignore（既存は触らない）
    gi = ws.root / ".gitignore"
    if not gi.exists():
        gi.write_text(read_template("gitignore.template"), encoding="utf-8")
        created.append(str(gi))

    return created
