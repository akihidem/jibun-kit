"""``jibun app --web`` — ローカル Web シェル。

wizard（Act 0〜3）はそのまま、:class:`WebPrompter` が Prompter protocol を
ブラウザとの橋渡しに変える。wizard は worker スレッドで動き、ask/confirm/choose
ごとに pending 記述子を発行して Queue でブロック、HTTP handler が回答を検証して
put する。**egress はこの層では発生しない**（claude 同意フローは acts 内のまま、
サーバは 127.0.0.1 のみで待ち受け、UI は外部アセットを参照しない）。
"""

from __future__ import annotations

import queue
import secrets
import threading

# 中断 sentinel: deliver/request_abort が put し、prompter メソッドが
# KeyboardInterrupt に変換する（wizard.run が rc 130 に変換 = TUI Ctrl-C と同経路）
_ABORT = object()


class _WebState:
    """サーバと wizard スレッドが共有する状態。``lock`` がすべてを守る。"""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.transcript: list[dict] = []      # append-only（再アクセスは since=0 で全再生）
        self.pending: dict | None = None      # 常に最大 1 個（wizard は逐次）
        self.done = False
        self.rc: int | None = None
        self.token = secrets.token_urlsafe(16)
        self.next_id = 1
        # Queue 深さは常に <= 1: put は pending を原子的にクリアした臨界区域のみで
        # 行われ、次の pending は wizard が前の回答を消費した後にしか発行されない。
        self.answers: queue.Queue = queue.Queue()
        self.abort_requested = False
        self.final_seen = threading.Event()   # done 入り応答をブラウザへ送れたら set


class WebPrompter:
    """Prompter protocol のブラウザ橋渡し実装。検証・正規化はすべてここ。

    HTTP なしで単体テストできるよう、handler から呼ばれる側
    （:meth:`deliver` / :meth:`request_abort` / :meth:`snapshot`）も持つ。
    """

    def __init__(self, state: _WebState | None = None) -> None:
        self.state = state or _WebState()

    # --- Prompter protocol（wizard スレッドから呼ばれる） ---

    def say(self, text: str) -> None:
        with self.state.lock:
            self.state.transcript.append({"kind": "say", "text": text})

    def ask(self, prompt: str, *, default: str = "", multiline: bool = False) -> str:
        return self._await_answer(
            {"ptype": "ask", "text": prompt, "default": default, "multiline": multiline})

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        return self._await_answer({"ptype": "confirm", "text": prompt, "default": default})

    def choose(self, prompt: str, options, *, default: int = 0) -> int:
        return self._await_answer(
            {"ptype": "choose", "text": prompt, "options": list(options), "default": default})

    def _await_answer(self, desc: dict):
        st = self.state
        with st.lock:
            if st.abort_requested:
                # claude 実行中などに届いた中断は、次の prompt 発行のここで発火する
                st.abort_requested = False
                raise KeyboardInterrupt
            desc = {"kind": "prompt", "id": st.next_id, **desc}
            st.next_id += 1
            st.transcript.append(desc)
            st.pending = desc
        value = st.answers.get()  # lock を持たずにブロック
        if value is _ABORT:
            raise KeyboardInterrupt
        return value

    # --- HTTP handler から呼ばれる側 ---

    def deliver(self, prompt_id, value) -> str:
        """回答を検証して wizard に渡す。返り値 "ok" | "stale" | "invalid"。

        exactly-once の要: 「id 照合 → 型検証 → pending クリア → echo 追記 → put」を
        ひとつの臨界区域で行う。重複 POST・2 タブの負け側は "stale"、
        型不正・範囲外は "invalid"（pending は維持、wizard は起こさない）。
        """
        st = self.state
        with st.lock:
            p = st.pending
            if p is None or not isinstance(prompt_id, int) or p["id"] != prompt_id:
                return "stale"
            ptype = p["ptype"]
            if ptype == "ask":
                if not isinstance(value, str):
                    return "invalid"
                typed = value.strip() or p["default"]  # StdioPrompter と同じ正規化
                display = typed if typed else "（スキップ）"
            elif ptype == "confirm":
                if not isinstance(value, bool):  # bool は int の subclass — 先に判定
                    return "invalid"
                typed = value
                display = "はい" if value else "いいえ"
            else:  # choose
                if isinstance(value, bool) or not isinstance(value, int):
                    return "invalid"
                if not 0 <= value < len(p["options"]):
                    # Web の choose はボタン入力なので範囲外 = 不正クライアント。
                    # 再質問はせず reject（pending 維持で正規 UI は回答可能なまま）
                    return "invalid"
                typed = value
                display = p["options"][value]
            st.pending = None
            st.transcript.append({"kind": "answer", "id": p["id"], "display": display})
            st.answers.put(typed)
            return "ok"

    def request_abort(self) -> None:
        """ブラウザの「中断」。pending 中なら即時、なければ次の prompt 発行時に発火。

        claude -p の実行中（最長 600s）は割り込めない — hard stop はターミナル Ctrl-C。
        """
        st = self.state
        with st.lock:
            if st.pending is not None:
                st.pending = None
                st.transcript.append({"kind": "say", "text": "（中断リクエストを受け付けました）"})
                st.answers.put(_ABORT)
            else:
                st.abort_requested = True

    def snapshot(self, since: int) -> dict:
        st = self.state
        with st.lock:
            return {
                "entries": list(st.transcript[since:]),
                "next": len(st.transcript),
                "pending": st.pending,
                "done": st.done,
                "rc": st.rc,
            }
