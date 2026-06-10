"""``jibun app`` — 対話ウィザード（TUI）。

ユーザーが対話しながら自分のデータを入力し、対話的に ``jibun.md`` を生成する。
対話エンジンは UI 非依存（:mod:`jibun_kit.app.prompter` の ``Prompter``）に
切ってあり、将来ターミナル以外の UI を被せられる。
"""

HELP = "対話ウィザードで取り込みから jibun.md 作成まで進める"
