"""Act 0（workspace 確保）と Act 1（source 提案 & guided ingest）。

Act 1 は GUIDE（:class:`jibun_kit.ingest.SourceGuide`）だけを見て registry 駆動で
進む — 「何が取り込めるか」を提案し、持っていなければ入手方法を案内し、
identity を対話で集めて jibun.toml に永続化し、既存の ingest を argv 経由で呼ぶ。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jibun_kit.app.prompter import Prompter
from jibun_kit.config import JibunConfig, set_toml_values
from jibun_kit.ingest import REGISTRY, SourceGuide, load_source
from jibun_kit.scaffold import scaffold_workspace
from jibun_kit.workspace import Workspace, resolve_workspace

# 摩擦の小さい順に提案する。claude-code は export 作業ゼロなので先頭。
ACT1_ORDER = ("claude-code", "twitter", "line", "gmail", "icloudmail",
              "imessage", "twilog", "blog")

# 礼儀クロール（twilog: 1 ページ 2 秒）なので、これを超える期間は一言確認する
_DATE_RANGE_CONFIRM_DAYS = 60


@dataclass(frozen=True)
class IdentityAsk:
    prompt: str
    kind: str = "str"   # "str" | "list"
    default: str = ""


IDENTITY_ASKS: dict[str, IdentityAsk] = {
    "identity.emails": IdentityAsk(
        "あなたのメールアドレスを教えてください（複数ならカンマ区切り）", kind="list"),
    "identity.line_name": IdentityAsk(
        "LINE 上のあなたの表示名（完全一致）を教えてください"),
    "identity.imessage_label": IdentityAsk(
        "iMessage export 上のあなたのラベルを教えてください", default="Me"),
    "identity.twilog_user": IdentityAsk(
        "twilog のユーザー名（@ は不要）を教えてください"),
    "fetch.contact": IdentityAsk(
        "クロール時に User-Agent へ載せる連絡先（メールアドレス等）を教えてください"),
    # sources.claude_code.projects_root はパス回答がそのまま永続値（_propose_source 内で特別扱い）
}

_KEY_TO_ATTR = {
    "identity.emails": "emails",
    "identity.line_name": "line_name",
    "identity.imessage_label": "imessage_label",
    "identity.twilog_user": "twilog_user",
    "sources.claude_code.projects_root": "claude_projects_root",
    "fetch.contact": "contact",
}

_FETCH_MODULES = {"twilog": ("requests", "bs4"), "blog": ("requests", "trafilatura")}


# --- Act 0 ---

def ensure_workspace(prompter: Prompter, cli_path: Path | None) -> Workspace | None:
    """workspace を解決・確認し、無ければその場で scaffold する。中止なら None。"""
    ws = resolve_workspace(cli_path)
    if ws.is_initialized():
        prompter.say(f"\nworkspace: {ws.root}（jibun.toml を検出）")
        if prompter.confirm("この workspace で進めますか？", default=True):
            return ws
        target = prompter.ask("使うディレクトリのパスを教えてください（空 Enter で中止）")
        if not target:
            return None
        ws = Workspace(Path(target).expanduser())
        if ws.is_initialized():
            return ws
    else:
        prompter.say("\njibun workspace がまだありません。"
                     "jibun.toml / data/ / sources/ / jibun.md の置き場を作ります。")
        if not prompter.confirm(f"{ws.root} に作成しますか？", default=True):
            target = prompter.ask("作成先ディレクトリ（空 Enter で中止）")
            if not target:
                return None
            ws = Workspace(Path(target).expanduser())
            if ws.is_initialized():
                return ws
    try:
        created = scaffold_workspace(ws)
    except FileExistsError:
        return ws  # 直前に初期化された等。既存をそのまま使う
    prompter.say(f"workspace を作成しました: {ws.root}")
    for c in created:
        prompter.say(f"  + {c}")
    return ws


# --- Act 1 ---

def run_act1(prompter: Prompter, ws: Workspace, done: list[str],
             save: Callable[[], None]) -> None:
    """source を順に提案する。``done`` は提案済み source 名（resume 用、破壊的に更新）。"""
    prompter.say("\n=== Act 1: データの取り込み ===")
    prompter.say("あなたが自ら打った文章（会話・メール・ツイート…）を集めます。"
                 "持っているものだけで OK、あとからいつでも追加できます。")
    results: list[tuple[str, str]] = []
    for name in ACT1_ORDER:
        if name in done:
            continue
        guide = load_source(name).GUIDE
        status = _propose_source(prompter, ws, name, guide)
        results.append((guide.label, status))
        done.append(name)
        save()
    if results:
        prompter.say("\n— Act 1 の結果 —")
        for label, status in results:
            mark = {"ingested": "✓", "skipped": "－", "failed": "✗"}[status]
            prompter.say(f" {mark} {label}")


def _propose_source(prompter: Prompter, ws: Workspace, name: str,
                    guide: SourceGuide) -> str:
    """1 source の提案〜取り込み。返り値: "ingested" | "skipped" | "failed"。"""
    prompter.say(f"\n── {guide.label} ──")
    prompter.say(guide.captures)
    while True:
        idx = prompter.choose("どうしますか？",
                              ["取り込む（データが手元にある）", "入手方法を見る", "スキップ"],
                              default=0)
        if idx == 1:
            prompter.say(f"\n{guide.how_to_get}")
            continue
        if idx == 2:
            return "skipped"
        break

    if guide.needs_fetch_extra and not _fetch_extra_available(name):
        prompter.say("この source には追加パッケージが必要です: pip install 'jibun-kit[fetch]'\n"
                     "インストール後にもう一度実行してください。今回はスキップします。")
        return "skipped"

    flags: list[str] = list(guide.fixed_argv)

    # identity を集めて jibun.toml に永続化（次回・他 source が再利用できる）
    cfg = JibunConfig.load(ws.config_path)
    updates: dict[str, dict[str, object]] = {}
    for key in guide.identity_keys:
        if key == "sources.claude_code.projects_root":
            continue  # パス回答がそのまま永続値になる（下のパス入力で扱う）
        current = getattr(cfg, _KEY_TO_ATTR[key], "")
        if current:
            shown = ", ".join(current) if isinstance(current, list) else current
            if prompter.confirm(f"設定済みの {key} = {shown} を使いますか？", default=True):
                continue
        ask = IDENTITY_ASKS[key]
        raw = prompter.ask(ask.prompt, default=ask.default)
        if not raw:
            prompter.say("未入力のため、この source はスキップします。")
            return "skipped"
        value: object = ([v.strip() for v in raw.split(",") if v.strip()]
                         if ask.kind == "list" else raw)
        section, _, leaf = key.rpartition(".")
        updates.setdefault(section, {})[leaf] = value
    if updates:
        set_toml_values(ws.config_path, updates)
        prompter.say("jibun.toml に保存しました（次回からは聞きません）。")

    # データの場所
    if guide.path_flags:
        picked = _ask_path(prompter, guide, name)
        if picked is None:
            return "skipped"
        flag, path = picked
        flags += [flag, str(path)]
        if name == "claude-code":
            set_toml_values(ws.config_path,
                            {"sources.claude_code": {"projects_root": str(path)}})

    # 追加の構造化質問
    for ask_kind in guide.asks:
        if ask_kind == "date_range":
            rng = _ask_date_range(prompter)
            if rng is None:
                return "skipped"
            flags += ["--since", rng[0], "--until", rng[1]]
        elif ask_kind == "urls":
            if not _collect_blog_urls(prompter, ws):
                return "skipped"

    # dry-run プレビュー → 確認 → 本取り込み
    prompter.say("\nまず書き込みなしで確認します（--dry-run）:")
    rc, out = _dispatch_ingest(ws, name, flags + ["--dry-run"])
    if out.strip():
        prompter.say(out.rstrip())
    if rc != 0:
        prompter.say("dry-run が失敗しました（上の出力を参照）。この source はスキップします。")
        return "failed"
    if not prompter.confirm("この内容で取り込みますか？", default=True):
        return "skipped"
    rc, out = _dispatch_ingest(ws, name, flags)
    if out.strip():
        prompter.say(out.rstrip())
    if rc == 0:
        prompter.say("✓ 取り込み完了")
        return "ingested"
    prompter.say("✗ 取り込みに失敗しました（上の出力を参照）。")
    return "failed"


def _dispatch_ingest(ws: Workspace, source: str, flags: list[str]) -> tuple[int, str]:
    """既存 CLI を argv 経由で呼び、(rc, 捕捉した出力) を返す。

    argparse が default / 必須 / 排他を全部処理する（SystemExit は rc に変換）。
    stdout/stderr はバッファで一括捕捉し、表示は呼び出し側が prompter.say で行う
    — Web UI の transcript にも届く。行ごとのストリーミング捕捉にはしないこと
    （TUI では say → print → redirect → 再帰になる）。
    """
    from jibun_kit import cli  # 循環 import 回避（cli → app は app コマンド内のみ）

    argv = ["ingest", source, "--path", str(ws.root), *flags]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            rc = cli.main(argv)
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 1
    return rc, buf.getvalue()


def _fetch_extra_available(name: str) -> bool:
    mods = _FETCH_MODULES.get(name, ())
    return all(importlib.util.find_spec(m) is not None for m in mods)


def _default_path_hint(name: str) -> str:
    """自動検出できる既定パス（あれば ask の default に出す）。"""
    if name == "claude-code":
        d = Path.home() / ".claude" / "projects"
        if d.is_dir():
            return str(d)
    return ""


def _ask_path(prompter: Prompter, guide: SourceGuide, name: str) -> tuple[str, Path] | None:
    kinds = set(guide.path_flags)
    what = ("ファイル" if kinds == {"file"}
            else "ディレクトリ" if kinds == {"dir"}
            else "ファイルまたはディレクトリ")
    default = _default_path_hint(name)
    for _ in range(3):
        raw = prompter.ask(f"{what}のパスを入力してください（空 Enter でスキップ）",
                           default=default)
        if not raw:
            return None
        p = Path(raw).expanduser()
        if p.is_dir() and "dir" in guide.path_flags:
            return guide.path_flags["dir"], p
        if p.is_file() and "file" in guide.path_flags:
            return guide.path_flags["file"], p
        prompter.say(f"  {p} は{what}として見つかりません。")
    prompter.say("3 回見つからなかったので、この source はスキップします。")
    return None


def _ask_date_range(prompter: Prompter) -> tuple[str, str] | None:
    for _ in range(3):
        since = prompter.ask("取得開始日 YYYY-MM-DD（空 Enter でスキップ）")
        if not since:
            return None
        until = prompter.ask("取得終了日 YYYY-MM-DD")
        try:
            s = datetime.strptime(since, "%Y-%m-%d")
            u = datetime.strptime(until, "%Y-%m-%d")
        except ValueError:
            prompter.say("  YYYY-MM-DD 形式で入力してください。")
            continue
        if s > u:
            prompter.say("  開始日が終了日より後になっています。")
            continue
        days = (u - s).days + 1
        if days > _DATE_RANGE_CONFIRM_DAYS and not prompter.confirm(
                f"{days} 日分を 1 ページ 2 秒間隔でクロールします。続けますか？", default=False):
            continue
        return since, until
    return None


def _collect_blog_urls(prompter: Prompter, ws: Workspace) -> bool:
    """URL を聞いて sources/blog.md に追記（重複は足さない）。"""
    from jibun_kit.ingest.blog import parse_blog_urls

    raw = prompter.ask("取り込みたい記事の URL を 1 行ずつ入力してください", multiline=True)
    urls = [u.strip() for u in raw.splitlines() if u.strip().startswith("http")]
    if not urls:
        prompter.say("http(s) の URL が無かったので、この source はスキップします。")
        return False
    blog_md = ws.sources_root / "blog.md"
    existing = set(parse_blog_urls(blog_md))
    new = [u for u in urls if u not in existing]
    if new:
        ws.sources_root.mkdir(parents=True, exist_ok=True)
        if not blog_md.is_file():
            blog_md.write_text("# 自分のブログ記事 URL（jibun ingest blog が取得）\n\n",
                               encoding="utf-8")
        with blog_md.open("a", encoding="utf-8") as f:
            for u in new:
                f.write(f"- {u}\n")
    prompter.say(f"sources/blog.md に {len(new)} 件追記しました"
                 f"（既存と重複 {len(urls) - len(new)} 件はスキップ）。")
    return True
