# jibun-kit

> 自分のデジタル足跡を取り込み、**人間と AI の両方が読める1枚の自己理解 Markdown（`jibun.md`）** を生成するキット。

`jibun-kit` は、あなたが**自ら打った文章・送った言葉**（Claude Code 会話 / 送信メール / LINE・iMessage / X / blog …）をローカルで集め、観察→仮説→（任意で）解釈の**単一 Markdown** にまとめます。
人間向け / AI 向けにファイルを分けません。原本は人間が読める Markdown ひとつ。AI に渡す内容と人間が読む内容を分岐させない、という原則で設計しています。

> ⚠️ Status: **alpha**。ingest（8 source）と build まで動作。配布形態（PyPI / public）と LICENSE は確定前。

## 設計の柱

- **単一の dual-readable 出力** — `jibun.md` 1枚を本人と AI が同じものを読む。AI 向けメモも別ファイルにせず同じ原本の §5 に畳み込む。
- **プライバシー優先** — 生データは `data/` に置き **gitignore**。repo に残るのはメタデータ（`sources/*-index.md`）と、人手でレビュー済みの `jibun.md` のみ。
- **provider 非依存** — `jibun build` は既定で「自分の AI に貼れる context bundle + プロンプト」を出力。`--with-claude` があれば `claude -p` に渡す。**個人の足跡を勝手に外部 API に送らない**（egress は人間の貼り付け操作のときだけ）。
- **stdlib-first** — core は標準ライブラリのみ。web ingest（twilog/blog）だけ `[fetch]` extra。

## インストール

```bash
git clone <repo-url> jibun-kit && cd jibun-kit
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[fetch,test]'   # core だけなら: pip install -e .
```

Python 3.11+（stdlib `tomllib` 利用）。

## クイックスタート

```bash
# 1. workspace を scaffold（jibun.md / jibun.toml / data/ / sources/）
jibun init

# 2. 自分の identity を記入
$EDITOR jibun.toml          # emails / line_name / imessage_label / twilog_user / fetch.contact

# 3. 手元の export を取り込む（持っているものだけでよい）
jibun ingest claude-code --projects-root ~/.claude/projects/<your>
jibun ingest gmail   --mbox path/to/sent.mbox
jibun ingest line    --file path/to/talk.txt
jibun ingest twitter --export-dir path/to/twitter-export/
# config だけで回せる source をまとめて:
jibun ingest all

# 4. 取り込んだデータ → jibun.md の素材を組む
jibun build                  # _build/<date>/{prompt,context-bundle,raw-input}.md を出力
#  → prompt.md と context-bundle.md を自分の AI に貼り、出力を jibun.md に保存
jibun build --with-claude    # PATH に claude があれば claude -p で draft 生成
```

各コマンドは `--dry-run` で書き込みなしの確認、`-v` で詳細ログ。設定の解決結果は `jibun config` で確認。

## 対応 source

| source | 取り込み元 | identity（jibun.toml） | 依存 |
|---|---|---|---|
| `claude-code` | Claude Code の会話 jsonl（自分の発言のみ抽出） | `sources.claude_code.projects_root` | stdlib |
| `gmail` | Google Takeout の送信済み mbox | `identity.emails` | stdlib |
| `icloudmail` | Mail.app の送信済み mbox | `identity.emails` | stdlib |
| `imessage` | imessage-exporter の txt | `identity.imessage_label` | stdlib |
| `line` | LINE トーク履歴 txt | `identity.line_name` | stdlib |
| `twitter` | X 公式 export（tweets.js） | —（export-dir 指定） | stdlib |
| `twilog` | twilog.togetter.com | `identity.twilog_user` + `fetch.contact` | `[fetch]` |
| `blog` | `sources/blog.md` の URL | `fetch.contact` | `[fetch]` |

`telegram` は v1 では未対応。

## プライバシーモデル

- `data/`（生データ）と `_build/`（bundle）は workspace の `.gitignore` で除外。
- repo に追跡されるのは `sources/*-index.md`（取り込み済みのメタ）と、人手でレビュー済みの `jibun.md` のみ。
- `jibun build` の既定は外部送信なし。`--with-claude` を明示したときだけローカルの `claude` に渡す。

## 診断スタンス（倫理）

自己理解の解釈は「観察→仮説→理論的言及→診断的言及」の4段。**診断レベルの言及は既定で OFF**（`build.diagnostic_stance = false`）で、`jibun.md` §7 は省略されます。
ON は「本人が自己検証できる専門家（臨床家等）」を前提とした上級者向け。**これは臨床評価ではなく、仮説であって診断ではありません。**

## 開発

```bash
pip install -e '.[fetch,test]'
pytest -q
```

## ライセンス

確定前。コードは MIT、方法論プロンプト（`prompts/build_prompt.md`）は CC BY-SA 4.0 の dual を検討中。

## 由来

`jibun`（個人の private 自己理解 repo）の ingest 群を一般化して抽出したもの。個人データ・固有 identity はこのキットに含めません。
