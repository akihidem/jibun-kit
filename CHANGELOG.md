# Changelog

このプロジェクトの主な変更を記録する（[Keep a Changelog](https://keepachangelog.com/) 準拠、[SemVer](https://semver.org/)）。

## [Unreleased]

### Added
- **Phase 0** — 土台: `jibun init` / `jibun config`、`Workspace`（root 注入）、`config`（jibun.toml、解決順 CLI > toml > env > default）、de-globalized な `common`、単一 `jibun.md` スターター。
- **Phase 1** — core ingest: `claude-code` / `gmail` / `line`。REGISTRY 駆動の `jibun ingest <source>` dispatch。identity は jibun.toml フォールバック。
- **Phase 2** — 残り ingest: `icloudmail` / `imessage` / `twitter` / `twilog` / `blog`、および `jibun ingest all`。twilog/blog は `[fetch]` extra（遅延 import、dry-run は依存なし）。
- **Phase 3** — `jibun build`: ingest 済みデータ + 4 段方法論プロンプト + 単一 md テンプレ → `_build/<date>/{context-bundle,prompt,raw-input}.md`。provider 非依存（既定は貼り付け案内、`--with-claude` で `claude -p`）。診断スタンス gating。
- **Phase 5** — `jibun app` 対話ウィザード: Act 0 workspace をその場で scaffold / Act 1 GUIDE 駆動の source 提案 & guided ingest（入手方法の案内、identity を対話収集して jibun.toml に永続化、dry-run プレビュー）/ Act 2 インタビュー = 新データソース（`data/interview/`、Ctrl-C 中断 → resume、任意の claude 追い質問）/ Act 3 対話ビルド（セクション別レビュー → フィードバック改訂 → 明示確認で保存、既存 jibun.md は退避）。基盤: 共有 `claude_cli`（egress 単一路、build も使用）、`config.set_toml_values`（toml 最小行編集）、各 ingest の `GUIDE`（`SourceGuide`）。
- **Phase 6** — `jibun app --web`: ブラウザのチャット UI で同じ 3 幕を進めるローカル Web シェル（stdlib `http.server`、127.0.0.1 のみ、外部アセットゼロ）。wizard は worker スレッドで動き `WebPrompter` が Prompter を橋渡し（pending 1 個・回答は handler 臨界区域で exactly-once、重複/2タブは 409）。`X-Jibun-Token` ヘッダ + Host 検査、textContent 限定描画（XSS 面対策）、タブ再訪は transcript 全再生、終了は done 配信後に自動停止。ingest 出力は捕捉して transcript に合流（`--dry-run` プレビューがブラウザでも見える）。

### Fixed
- 取り込み: `claude-code` が `~/.claude/projects/<project>/<session>.jsonl` の配下を探さず 0 件になっていた。`isMeta`・`isCompactSummary`・`[Request interrupted by user` を本人の発言から外した。
- 取り込み: `imessage` が月の省略形（`Jan 06, 2026`）と日時行末尾の既読注記を読めず、本文中の空行より後ろを落としていた。
- 取り込み: `twitter` が分割アーカイブ（`tweets-part1.js` …）の 2 本目以降を読まず、`--until` が指定日を含んでいなかった。
- 取り込み: `icloudmail` / `gmail` に Mail.app が書き出す `*.mbox/` dir を渡すと落ちていた。`gmail` を同じ mbox で再実行するたびに `.1.md` の重複が増えていた。
- 取り込み: `blog` の取り込み済み判定と `sources/<source>-index.md` の重複判定が部分文字列一致で、別の URL・行を取り込み済みと誤認していた。
- `jibun app`: 同じ日に 2 回保存すると退避した元の `jibun.md` が上書きされて消えていた。`claude -p` の出力が空でも保存を勧めていた。壊れた／複数行配列の `jibun.toml`・壊れた `.progress.json` で落ちていた。claude-code の場所を相対パスのまま保存していた。`SystemExit(None)` を失敗扱いしていた。
- `jibun app --web`: `GET /` に `X-Frame-Options: DENY` と `Content-Security-Policy: frame-ancestors 'none'` を付けた（他サイトの iframe に埋め込ませない）。

### Notes
- `data/`・`_build/` は workspace の gitignore 対象。repo 追跡はメタ + レビュー済み jibun.md のみ。
- `jibun app` の claude 利用は操作ごとの明示同意（既定 No）。interview の回答・進捗（`.progress.json`）は `data/` 配下で gitignore 対象。
- `jibun build --effort` は現状 parse のみで `claude -p` に渡していない（既知、別途対応）。
- `telegram` source は v1 では未対応（upstream stub）。
- **2026-06-11: LICENSE 確定・repo public 化** — コード/テンプレートは MIT、方法論プロンプト
  （prompts/build_prompt.md）のみ CC BY-SA 4.0 のデュアル。生成された jibun.md には
  いずれのライセンスも及ばない（生成物は利用者のもの）。スターターテンプレートを
  CC BY-SA にしなかったのは、定型文が利用者の jibun.md に残るため SA が個人文書を
  汚染しないようにする意図。PyPI 配布は引き続き未定。

[Unreleased]: https://github.com/akihidem/jibun-kit/commits/main
