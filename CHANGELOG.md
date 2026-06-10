# Changelog

このプロジェクトの主な変更を記録する（[Keep a Changelog](https://keepachangelog.com/) 準拠、[SemVer](https://semver.org/)）。

## [Unreleased]

### Added
- **Phase 0** — 土台: `jibun init` / `jibun config`、`Workspace`（root 注入）、`config`（jibun.toml、解決順 CLI > toml > env > default）、de-globalized な `common`、単一 `jibun.md` スターター。
- **Phase 1** — core ingest: `claude-code` / `gmail` / `line`。REGISTRY 駆動の `jibun ingest <source>` dispatch。identity は jibun.toml フォールバック。
- **Phase 2** — 残り ingest: `icloudmail` / `imessage` / `twitter` / `twilog` / `blog`、および `jibun ingest all`。twilog/blog は `[fetch]` extra（遅延 import、dry-run は依存なし）。
- **Phase 3** — `jibun build`: ingest 済みデータ + 4 段方法論プロンプト + 単一 md テンプレ → `_build/<date>/{context-bundle,prompt,raw-input}.md`。provider 非依存（既定は貼り付け案内、`--with-claude` で `claude -p`）。診断スタンス gating。
- **Phase 5** — `jibun app` 対話ウィザード: Act 0 workspace をその場で scaffold / Act 1 GUIDE 駆動の source 提案 & guided ingest（入手方法の案内、identity を対話収集して jibun.toml に永続化、dry-run プレビュー）/ Act 2 インタビュー = 新データソース（`data/interview/`、Ctrl-C 中断 → resume、任意の claude 追い質問）/ Act 3 対話ビルド（セクション別レビュー → フィードバック改訂 → 明示確認で保存、既存 jibun.md は退避）。基盤: 共有 `claude_cli`（egress 単一路、build も使用）、`config.set_toml_values`（toml 最小行編集）、各 ingest の `GUIDE`（`SourceGuide`）。

### Notes
- `data/`・`_build/` は workspace の gitignore 対象。repo 追跡はメタ + レビュー済み jibun.md のみ。
- `jibun app` の claude 利用は操作ごとの明示同意（既定 No）。interview の回答・進捗（`.progress.json`）は `data/` 配下で gitignore 対象。
- `jibun build --effort` は現状 parse のみで `claude -p` に渡していない（既知、別途対応）。
- `telegram` source は v1 では未対応（upstream stub）。
- 配布形態（PyPI / public）・LICENSE は未確定。

[Unreleased]: https://github.com/akihidem/jibun-kit/commits/main
