"""iCloud Mail (Mac Mail.app の mbox export) から自分の送信メールを抽出。

ingest/gmail.py と完全に共通（mbox parser + email フィルタ）。出力 source 名だけ
"icloudmail" に変える。元の `sys.argv` 書き換えラッパーではなく
``gmail.run(..., source_name="icloudmail")`` を呼ぶ。
"""

from __future__ import annotations

from jibun_kit.ingest import SourceGuide, gmail

HELP = "送信済み mbox (iCloud / Mail.app) から自分のメールを抽出"

GUIDE = SourceGuide(
    label="iCloud メール（Mail.app）送信済み",
    captures="Mail.app から書き出した送信済みメールの本文を取り込みます。",
    how_to_get="Mac の Mail.app で送信済みメールボックスを選択 → メニューの「メールボックス > "
               "メールボックスを書き出す…」 → 書き出された mbox のパスを指定します。",
    path_flags={"file": "--mbox"},
    identity_keys=("identity.emails",),
)


def add_arguments(parser) -> None:
    gmail.add_arguments(parser)


def run(config, args, ws) -> int:
    return gmail.run(config, args, ws, source_name="icloudmail")
