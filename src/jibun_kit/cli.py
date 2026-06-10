"""jibun — single CLI entrypoint.

Subcommands: ``init`` / ``config`` / ``ingest <source>`` / ``build``.
``build`` is a stub in Phase 0–2; Phase 3 implements it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from jibun_kit import __version__
from jibun_kit.config import JibunConfig
from jibun_kit.workspace import Workspace, resolve_workspace


def _add_path_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--path", type=Path, default=None, metavar="DIR",
        help="workspace root (default: $JIBUN_ROOT or upward search from CWD)",
    )


def cmd_init(args: argparse.Namespace) -> int:
    from jibun_kit.scaffold import scaffold_workspace

    ws = Workspace(args.path) if args.path else Workspace(Path.cwd())
    try:
        created = scaffold_workspace(ws, force=args.force)
    except FileExistsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"Initialized jibun workspace at {ws.root}")
    for c in created:
        print(f"  + {c}")
    print("\nNext: edit jibun.toml (your identity), then `jibun ingest <source>`.")
    print("Tip: run `git init` here yourself if you want version control "
          "(jibun-kit does not touch git).")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    ws = resolve_workspace(args.path)
    cfg = JibunConfig.load(ws.config_path)
    found = "found" if ws.config_path.is_file() else "MISSING (using defaults)"
    print(f"workspace root : {ws.root}")
    print(f"config file    : {ws.config_path} ({found})")
    print("resolved config:")
    print(f"  identity.emails         = {cfg.emails}")
    print(f"  identity.email_pattern  = {cfg.email_pattern!r}")
    print(f"  identity.line_name      = {cfg.line_name!r}")
    print(f"  identity.imessage_label = {cfg.imessage_label!r}")
    print(f"  identity.twilog_user    = {cfg.twilog_user!r}")
    print(f"  sources.claude_code.projects_root = {cfg.claude_projects_root!r}")
    print(f"  fetch.contact           = {cfg.contact!r}")
    print(f"  build.diagnostic_stance = {cfg.diagnostic_stance}")
    print(f"  build.default_effort    = {cfg.default_effort!r}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    from jibun_kit.ingest import REGISTRY, load_source

    source = getattr(args, "source", None)
    if not source:
        print("error: source を指定してください。例: `jibun ingest claude-code`", file=sys.stderr)
        print("  sources: " + ", ".join(sorted(REGISTRY)), file=sys.stderr)
        return 2
    ws = resolve_workspace(args.path)
    cfg = JibunConfig.load(ws.config_path)
    return load_source(source).run(cfg, args, ws)


def cmd_ingest_all(args: argparse.Namespace) -> int:
    """config だけで実行できる source をまとめて取り込む。

    export を渡す必要がある source (gmail/icloudmail/imessage/line/twitter/twilog) は
    入力パスが毎回違うので --all では走らせず、個別実行を促す（黙ってスキップしない）。
    """
    from jibun_kit.ingest import blog, claude_code

    ws = resolve_workspace(args.path)
    cfg = JibunConfig.load(ws.config_path)
    ran: list[str] = []
    skipped: list[str] = []

    # claude-code: config に projects_root があれば全 session
    if cfg.claude_projects_root:
        cc = argparse.Namespace(projects_root=None, session=None, all=True, since=None,
                                until=None, dry_run=args.dry_run, verbose=args.verbose)
        claude_code.run(cfg, cc, ws)
        ran.append("claude-code")
    else:
        skipped.append("claude-code — set [sources.claude_code].projects_root in jibun.toml")

    # blog: workspace の sources/blog.md に URL があれば
    if blog.parse_blog_urls(ws.sources_root / "blog.md"):
        bl = argparse.Namespace(blog_md=None, refresh_all=False, contact=None,
                                dry_run=args.dry_run, verbose=args.verbose)
        blog.run(cfg, bl, ws)
        ran.append("blog")
    else:
        skipped.append("blog — add URLs to sources/blog.md")

    skipped.append("gmail/icloudmail/imessage/line/twitter/twilog — run individually "
                   "(each needs its own --mbox/--file/--export-dir/--since etc.)")

    print(f"\ningest all: ran [{', '.join(ran) if ran else 'none'}]")
    for s in skipped:
        print(f"  skipped: {s}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    from jibun_kit import build as build_mod

    ws = resolve_workspace(args.path)
    cfg = JibunConfig.load(ws.config_path)
    return build_mod.run(cfg, args, ws)


def cmd_app(args: argparse.Namespace) -> int:
    # workspace はここで解決しない（未初期化なら Act 0 がその場で scaffold する）
    from jibun_kit.app import wizard

    return wizard.run(args)


def _build_ingest_subparsers(p_ing: argparse.ArgumentParser) -> None:
    """REGISTRY を駆動して `jibun ingest <source>` の各 sub-subparser を構築。"""
    from jibun_kit.ingest import REGISTRY, load_source

    src_sub = p_ing.add_subparsers(dest="source", metavar="<source>")
    for name in sorted(REGISTRY):
        mod = load_source(name)
        sp = src_sub.add_parser(name, help=getattr(mod, "HELP", f"ingest {name}"))
        # 共通引数（source 別フラグの前に置く）
        sp.add_argument("--path", type=Path, default=None, metavar="DIR",
                        help="workspace root (default: $JIBUN_ROOT or upward search)")
        sp.add_argument("--dry-run", action="store_true", help="report counts, write nothing")
        sp.add_argument("-v", "--verbose", action="store_true")
        mod.add_arguments(sp)
        sp.set_defaults(func=cmd_ingest, source=name)

    # `jibun ingest all`: config から実行できる source をまとめて取り込む
    sp_all = src_sub.add_parser(
        "all", help="config から実行できる source をまとめて取り込む (claude-code, blog)")
    sp_all.add_argument("--path", type=Path, default=None, metavar="DIR",
                        help="workspace root (default: $JIBUN_ROOT or upward search)")
    sp_all.add_argument("--dry-run", action="store_true")
    sp_all.add_argument("-v", "--verbose", action="store_true")
    sp_all.set_defaults(func=cmd_ingest_all)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jibun",
        description="Ingest your own data, generate one dual-readable "
                    "self-understanding markdown (jibun.md).",
    )
    parser.add_argument("--version", action="version", version=f"jibun-kit {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p_init = sub.add_parser("init", help="scaffold a jibun workspace")
    p_init.add_argument("--path", type=Path, default=None, metavar="DIR",
                        help="where to create the workspace (default: CWD)")
    p_init.add_argument("--force", action="store_true",
                        help="overwrite an existing jibun.toml (data/ is never touched)")
    p_init.set_defaults(func=cmd_init)

    p_cfg = sub.add_parser("config", help="print the resolved config")
    _add_path_arg(p_cfg)
    p_cfg.set_defaults(func=cmd_config)

    p_ing = sub.add_parser("ingest", help="ingest a source: `jibun ingest <source> [opts]`")
    _build_ingest_subparsers(p_ing)
    p_ing.set_defaults(func=cmd_ingest)

    p_app = sub.add_parser(
        "app", help="対話ウィザード: 取り込み案内 → インタビュー → jibun.md 生成まで対話で進む")
    _add_path_arg(p_app)
    p_app.set_defaults(func=cmd_app)

    p_build = sub.add_parser("build", help="assemble ingested data into jibun.md")
    _add_path_arg(p_build)
    p_build.add_argument("--with-claude", action="store_true",
                         help="shell out to `claude -p` if available")
    p_build.add_argument("--effort", default=None, help="effort for --with-claude")
    p_build.add_argument("-o", "--output", type=Path, default=None, metavar="FILE")
    p_build.set_defaults(func=cmd_build)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
