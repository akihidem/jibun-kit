"""iCloud Mail (Mac Mail.app の mbox export) から自分の送信メールを抽出。

ingest/gmail.py と完全に共通（mbox parser + email フィルタ）。出力 source 名だけ
"icloudmail" に変える。元の `sys.argv` 書き換えラッパーではなく
``gmail.run(..., source_name="icloudmail")`` を呼ぶ。
"""

from __future__ import annotations

from jibun_kit.ingest import gmail

HELP = "送信済み mbox (iCloud / Mail.app) から自分のメールを抽出"


def add_arguments(parser) -> None:
    gmail.add_arguments(parser)


def run(config, args, ws) -> int:
    return gmail.run(config, args, ws, source_name="icloudmail")
