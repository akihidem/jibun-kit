# jibun-kit

> 自分のデジタル足跡を取り込み、**人間と AI の両方が読める1枚の自己理解 Markdown（`jibun.md`）** を生成するキット。

`jibun-kit` は、あなたが**自ら打った文章・送った言葉**（Claude Code 会話 / 送信メール / LINE・iMessage / X / blog …）をローカルで集め、観察→仮説→（任意で）解釈の**単一 Markdown** にまとめます。
人間向け / AI 向けにファイルを分けません。原本は人間が読める Markdown ひとつ。AI に渡す内容と人間が読む内容を分岐させない、という原則で設計しています。

> ⚠️ Status: **alpha**。ingest（8 source + interview）/ build / 対話モード（`jibun app`）まで動作。配布形態（PyPI / public）と LICENSE は確定前。

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

### 対話で（推奨）

```bash
jibun app
```

1 コマンドで、workspace 作成 → 「どのデータを取り込めるか」の提案・入手方法の案内 → インタビュー → `jibun.md` 生成まで対話で進みます。Ctrl-C で中断しても次回続きから再開できます。詳細は[対話モード](#対話モードjibun-app)。

### 手動で（CLI を個別に）

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
| `interview` | `jibun app` の対話質問への回答（自己申告） | — | stdlib |

`telegram` は v1 では未対応。`interview` は app 専用（`jibun ingest interview` は無い）。

## 対話モード（jibun app）

`jibun app` は 3 幕の対話ウィザード。**export を何も持っていない人でも、質問に答えるだけで jibun.md を作れる**。

1. **取り込み（Act 1）** — 8 source を順に「何が取り込めるか」提案し、持っていなければ入手方法（X のアーカイブ請求、Google Takeout など）を案内。identity（メールアドレス・LINE 表示名など）は対話で聞いて `jibun.toml` に保存し、次回からは聞かない。取り込みは必ず `--dry-run` プレビュー → 確認 → 本実行。
2. **インタビュー（Act 2）** — 組み込み質問 約 15 問（全てスキップ可）。回答は `data/interview/` に自己申告ソースとして記録され、そのまま build の素材になる。
3. **ビルド（Act 3）** — draft を生成し、セクションごとに「ここは合ってる？」と確認 → コメントを反映して改訂 → 納得したら明示確認のうえ `jibun.md` に保存（既存の jibun.md は `_build/<date>/jibun.previous.md` に退避）。

補足:

- **claude はあってもなくてもよい。** PATH に `claude` があり、その操作ごとに y/N（既定 No）で同意したときだけ「追い質問の生成」「draft 生成・改訂」に使う。無ければ・同意しなければ、従来どおり prompt + bundle を自分の AI に貼る案内になる（egress ゼロで完走できる）。
- **中断・再開。** Ctrl-C でいつでも中断。進捗は `data/interview/.progress.json`（gitignore 対象）に逐次保存され、次回 `jibun app` で続きから再開できる。同日にやり直しても前のインタビューは `.2.md` 連番で保護される。

### Web UI（jibun app --web）

```bash
jibun app --web            # http://127.0.0.1:8765/ にチャット UI（ブラウザを自動で開く）
jibun app --web --port 0   # ポート自動割当
jibun app --web --no-browser
```

ターミナルの代わりにブラウザのチャット画面で同じ 3 幕を進めるモード。中身は同一（対話エンジンは UI 非依存で、Web はその「シェル」）。

- **127.0.0.1 のみ**で待ち受け、ページは外部アセットを一切参照しない。データがこの PC から出る経路は従来どおり claude への明示同意だけ
- タブを閉じても大丈夫 — 同じ URL を開き直せば会話が全再生される。終了はターミナルの Ctrl-C（進捗は保存済み）、画面右上の「中断」でも保存して止まる
- WSL ではブラウザが自動で開かないことがある。表示される URL を Windows 側ブラウザで開けばよい（localhost は WSL に転送される）
- 同一マシンの他ユーザーからのアクセス防御は範囲外（個人マシン前提のローカルツール）

## プライバシーモデル

- `data/`（生データ）と `_build/`（bundle）は workspace の `.gitignore` で除外。
- repo に追跡されるのは `sources/*-index.md`（取り込み済みのメタ）と、人手でレビュー済みの `jibun.md` のみ。
- `jibun build` の既定は外部送信なし。`--with-claude` を明示したときだけローカルの `claude` に渡す。
- `jibun app` も同じ原則: claude の利用（追い質問・draft 生成・改訂）は**操作ごとに明示同意**（y/N、既定 No）。同意しなければ外部送信ゼロのまま完走できる。送信経路はコード上も `claude_cli` モジュール 1 か所のみ。
- `jibun app --web` は 127.0.0.1 のみで待ち受け、UI は外部アセットを参照しない（CDN なし）。Web 層は新しい送信経路を作らない。

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
