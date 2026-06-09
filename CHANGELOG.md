# Changelog

このプロジェクトの主な変更を記録する（[Keep a Changelog](https://keepachangelog.com/) 準拠、[SemVer](https://semver.org/)）。

## [Unreleased]

### Added
- **Phase 0** — 土台: `jibun init` / `jibun config`、`Workspace`（root 注入）、`config`（jibun.toml、解決順 CLI > toml > env > default）、de-globalized な `common`、単一 `jibun.md` スターター。
- **Phase 1** — core ingest: `claude-code` / `gmail` / `line`。REGISTRY 駆動の `jibun ingest <source>` dispatch。identity は jibun.toml フォールバック。
- **Phase 2** — 残り ingest: `icloudmail` / `imessage` / `twitter` / `twilog` / `blog`、および `jibun ingest all`。twilog/blog は `[fetch]` extra（遅延 import、dry-run は依存なし）。
- **Phase 3** — `jibun build`: ingest 済みデータ + 4 段方法論プロンプト + 単一 md テンプレ → `_build/<date>/{context-bundle,prompt,raw-input}.md`。provider 非依存（既定は貼り付け案内、`--with-claude` で `claude -p`）。診断スタンス gating。

### Notes
- `data/`・`_build/` は workspace の gitignore 対象。repo 追跡はメタ + レビュー済み jibun.md のみ。
- `telegram` source は v1 では未対応（upstream stub）。
- 配布形態（PyPI / public）・LICENSE は未確定。

[Unreleased]: https://github.com/akihidem/jibun-kit/commits/main
