# jibun-kit

> 自分のデジタル足跡を取り込み、**人間と AI の両方が読める1枚の自己理解 Markdown（`jibun.md`）** を生成するキット。

自分が打った文章（Claude Code 会話 / 送信メール / LINE・iMessage / X / blog …）を
ローカルで ingest し、観察→仮説→（任意で）解釈の **単一 Markdown** にまとめる。
人間向け / AI 向けにファイルを分けない（kimochi 原則「原本は人間が読める Markdown ひとつ」）。

> ⚠️ Status: **alpha / 開発中**。Phase 0（土台）実装済み。ingest / build は順次。

## 設計の柱

- **単一の dual-readable 出力** — `jibun.md` 1枚を本人と AI が同じものを読む。
- **プライバシー優先** — 生データは `data/` に置き **gitignore**。repo に残るのはメタデータ（`sources/*-index.md`）と、人手でレビュー済みの `jibun.md` のみ。
- **provider 非依存** — `jibun build` は既定で「自分の AI に貼れる context bundle + プロンプト」を出力。`--with-claude` があれば `claude -p` に渡せる。API key 必須にしない。
- **stdlib-first** — core は標準ライブラリのみ。web ingest（twilog/blog）だけ `[fetch]` extra。

## インストール（開発）

```bash
git clone <repo> jibun-kit && cd jibun-kit
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[fetch,test]'
```

## 使い方（予定の流れ）

```bash
jibun init                 # workspace を scaffold（jibun.md / jibun.toml / data/ / sources/）
$EDITOR jibun.toml         # 自分の identity（emails / line_name / twilog_user …）を記入
jibun ingest claude-code   # 各 source を取り込む（Phase 1+）
jibun ingest --all
jibun build                # 取り込んだデータ → jibun.md（Phase 3）
```

## 対応 source

| source | 取り込み元 | 依存 |
|---|---|---|
| `claude-code` | Claude Code の会話 jsonl（user 発言のみ抽出） | stdlib |
| `gmail` / `icloudmail` | Takeout / Mail.app の送信済み mbox | stdlib |
| `imessage` | imessage-exporter の txt | stdlib |
| `line` | LINE トーク履歴 txt | stdlib |
| `twitter` | X 公式 export | stdlib |
| `twilog` | twilog.togetter.com | `[fetch]` |
| `blog` | URL リスト | `[fetch]` |

`telegram` は v1 では未対応。

## ライセンス

コード: MIT（予定）。方法論プロンプト（`prompts/build_prompt.md`）は CC BY-SA 4.0 を検討（dual）。
※確定前。

## 由来

`jibun`（operator 個人の private 自己理解 repo）の ingest 群を一般化して抽出したもの。
個人データ・固有 identity は含めない。
