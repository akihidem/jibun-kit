"""``jibun build`` — ingest 済みデータ + 方法論プロンプトを束ね、単一 ``jibun.md`` を作る。

provider 非依存: 既定は「context bundle + prompt + 手順」を出力し、ユーザーが自分の AI に
貼って ``jibun.md`` を作る。``--with-claude`` があれば PATH の ``claude -p`` に渡して draft を生成。
個人の足跡を勝手に外部 API に送らない（egress は人間が起動する貼り付け or 明示フラグのときだけ）。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from jibun_kit.scaffold import read_prompt, read_template

HELP = "ingest 済みデータを単一 jibun.md に束ねる"


def collect_sources(ws):
    """``data/**/*.md`` と ``sources/*-index.md`` を集める。"""
    data_files = sorted(ws.data_root.rglob("*.md")) if ws.data_root.exists() else []
    index_files = sorted(ws.sources_root.glob("*-index.md")) if ws.sources_root.exists() else []
    return data_files, index_files


def assemble_bundle(ws, data_files: list[Path], index_files: list[Path]) -> str:
    parts = [
        "# context bundle (jibun build)",
        "",
        "ingest 済みの「自分が打った発言」の本文とメタデータ。これを一次資料に jibun.md を書く。",
    ]
    if index_files:
        parts.append("\n## sources インデックス")
        for p in index_files:
            parts.append(f"\n<!-- {p.relative_to(ws.root)} -->")
            parts.append(p.read_text(encoding="utf-8"))
    parts.append("\n## ingest データ")
    for p in data_files:
        parts.append(f"\n<!-- {p.relative_to(ws.root)} -->")
        parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts)


def observation_summary(ws, data_files: list[Path]) -> str:
    """ソース別の件数・バイト数（反証可能性の錨＝観察範囲の明示）。"""
    by_source: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "bytes": 0})
    for p in data_files:
        try:
            source = p.relative_to(ws.data_root).parts[0]
        except (ValueError, IndexError):
            source = "?"
        by_source[source]["files"] += 1
        by_source[source]["bytes"] += p.stat().st_size
    lines = ["# observation summary", "", "ソース別の観察範囲（jibun.md §1 の素材）:", ""]
    for src, st in sorted(by_source.items()):
        lines.append(f"- {src}: {st['files']} files, {st['bytes']:,} bytes")
    return "\n".join(lines) + "\n"


def render_prompt(config) -> str:
    """方法論プロンプト + 診断スタンス + 出力テンプレートを連結。"""
    base = read_prompt("build_prompt.md")
    marker = "ON" if config.diagnostic_stance else "OFF"
    if config.diagnostic_stance:
        detail = "本人は自己検証できる専門家。§7 で診断レベルの言及をしてよい。"
    else:
        detail = "理論的言及（語彙としての参照）までで止め、§7 診断レベルは出力しない（見出しごと省略）。"
    starter = read_template("jibun.starter.md")
    return (
        f"{base}\n\n"
        f"## このビルドの診断スタンス: {marker}\n{detail}\n\n"
        f"## 出力テンプレート（この構成で jibun.md を書く）\n\n"
        f"```markdown\n{starter}\n```\n"
    )


def _run_with_claude(args, ws, build_dir: Path, prompt: str, bundle: str, target_md: Path) -> int:
    claude = shutil.which("claude")
    if not claude:
        print("\n--with-claude: `claude` が PATH に無いので貼り付けフローにフォールバックします。",
              file=sys.stderr)
        print(f"  {build_dir / 'prompt.md'} と {build_dir / 'context-bundle.md'} を自分の AI に渡してください。")
        return 0
    combined = f"{prompt}\n\n---\n\n{bundle}"
    draft_path = build_dir / "jibun.draft.md"
    print(f"\n--with-claude: claude -p に渡して {draft_path} を生成中 ...")
    try:
        result = subprocess.run(
            [claude, "-p"], input=combined, capture_output=True, text=True, timeout=600,
        )
    except Exception as e:
        print(f"error: claude 実行に失敗: {e}", file=sys.stderr)
        return 1
    if result.returncode != 0:
        print(f"error: claude returned {result.returncode}: {result.stderr[:500]}", file=sys.stderr)
        return 1
    draft_path.write_text(result.stdout, encoding="utf-8")
    print(f"  draft 生成: {draft_path}")
    print(f"  レビューして問題なければ {target_md} に昇格してください（自動では上書きしません）。")
    return 0


def run(config, args, ws) -> int:
    data_files, index_files = collect_sources(ws)
    if not data_files:
        print(f"error: {ws.data_root} に ingest 済みデータがありません。"
              f"まず `jibun ingest <source>` を実行してください。", file=sys.stderr)
        return 2

    stamp = datetime.now().strftime("%Y-%m-%d")
    build_dir = ws.build_root / stamp
    build_dir.mkdir(parents=True, exist_ok=True)

    bundle = assemble_bundle(ws, data_files, index_files)
    bundle_path = build_dir / "context-bundle.md"
    bundle_path.write_text(bundle, encoding="utf-8")

    (build_dir / "raw-input.md").write_text(observation_summary(ws, data_files), encoding="utf-8")

    prompt = render_prompt(config)
    prompt_path = build_dir / "prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")

    total_bytes = sum(p.stat().st_size for p in data_files)
    target_md = args.output or ws.jibun_md
    print(f"context bundle: {bundle_path} ({total_bytes:,} bytes / {len(data_files)} files)")
    print(f"prompt        : {prompt_path}")
    print(f"summary       : {build_dir / 'raw-input.md'}")
    if total_bytes > 800_000:
        print(f"  note: bundle が大きめ（{total_bytes:,} bytes）。AI の context に入らなければ "
              f"data/ を絞るか期間を区切ってください。")

    if args.with_claude:
        return _run_with_claude(args, ws, build_dir, prompt, bundle, target_md)

    print("\n次の手順:")
    print(f"  1. {prompt_path} と {bundle_path} を自分の AI（Claude 等）に渡す")
    print(f"  2. 出力を {target_md} に保存（スターターの各セクションを置換）")
    print("  ※ 個人データが外部に出るのは、この貼り付けという人間の操作のときだけ。")
    return 0
