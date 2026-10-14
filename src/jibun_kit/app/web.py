"""``jibun app --web`` — ローカル Web シェル。

wizard（Act 0〜3）はそのまま、:class:`WebPrompter` が Prompter protocol を
ブラウザとの橋渡しに変える。wizard は worker スレッドで動き、ask/confirm/choose
ごとに pending 記述子を発行して Queue でブロック、HTTP handler が回答を検証して
put する。**egress はこの層では発生しない**（claude 同意フローは acts 内のまま、
サーバは 127.0.0.1 のみで待ち受け、UI は外部アセットを参照しない）。
"""

from __future__ import annotations

import json
import queue
import secrets
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, urlparse

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


# --- HTTP 層 ---

_MAX_BODY = 1 * 1024 * 1024  # POST body 上限


def _load_html() -> str:
    return resources.files("jibun_kit.app").joinpath("webui.html").read_text(encoding="utf-8")


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # タブを閉じた瞬間の切断は正常系。それ以外は通常どおり stderr へ
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        super().handle_error(request, client_address)


class _Handler(BaseHTTPRequestHandler):
    """UI 配信 + JSON API。共有状態は ``self.server.app``（AppServer）経由。"""

    server_version = "jibun-app"

    @property
    def app(self) -> "AppServer":
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, format, *args):  # noqa: A002 (基底クラスの契約)
        pass  # アクセスログは出さない（個人ローカルツール）

    # --- helpers ---

    def _host_ok(self) -> bool:
        # DNS rebinding 対策: ブラウザが付ける Host を検査
        host = self.headers.get("Host", "")
        return host in {f"127.0.0.1:{self.app.port}", f"localhost:{self.app.port}"}

    def _token_ok(self) -> bool:
        return self.headers.get("X-Jibun-Token", "") == self.app.prompter.state.token

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        """POST body を dict で返す。"too_large" / None（不正）の場合あり。"""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length < 0 or length > _MAX_BODY:
            return "too_large"
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    # --- routes ---

    def do_GET(self):
        if not self._host_ok():
            return self._send_json(403, {"error": "bad host"})
        parsed = urlparse(self.path)
        if parsed.path == "/":
            html = self.app.html.replace("{{TOKEN}}", self.app.prompter.state.token)
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")  # 前回 run の古い token を残さない
            # 他サイトの iframe に埋め込ませない（clickjacking 対策）。inline の
            # script/style を壊さないよう CSP は frame-ancestors だけにする
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/state":
            if not self._token_ok():
                return self._send_json(403, {"error": "bad token"})
            try:
                since = int(parse_qs(parsed.query).get("since", ["0"])[0])
            except ValueError:
                return self._send_json(400, {"error": "bad since"})
            if since < 0:
                return self._send_json(400, {"error": "bad since"})
            snap = self.app.prompter.snapshot(since)
            self._send_json(200, snap)
            if snap["done"]:
                # done をブラウザへ届け終えた → 自動シャットダウンの握手
                self.app.prompter.state.final_seen.set()
            return
        if parsed.path in ("/api/answer", "/api/abort"):
            return self._send_json(405, {"error": "method not allowed"})
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if not self._host_ok():
            return self._send_json(403, {"error": "bad host"})
        path = urlparse(self.path).path
        if path == "/api/state":
            return self._send_json(405, {"error": "method not allowed"})
        if path not in ("/api/answer", "/api/abort"):
            return self._send_json(404, {"error": "not found"})
        if not self._token_ok():
            return self._send_json(403, {"error": "bad token"})
        if path == "/api/abort":
            self.app.prompter.request_abort()
            return self._send_json(200, {"ok": True})
        data = self._read_json()
        if data == "too_large":
            return self._send_json(413, {"error": "body too large"})
        if data is None or "prompt_id" not in data or "value" not in data:
            return self._send_json(400, {"error": "bad request"})
        result = self.app.prompter.deliver(data["prompt_id"], data["value"])
        if result == "ok":
            return self._send_json(200, {"ok": True})
        if result == "stale":
            return self._send_json(409, {"error": "stale"})
        return self._send_json(400, {"error": "invalid value"})


class AppServer:
    """サーバ一式（bind・wizard スレッド・shutdown 握手）。

    テストは ``AppServer(args, grace=0.5)`` を port 0 で作り ``.port`` を読む。
    """

    def __init__(self, args, *, grace: float = 10.0):
        self.args = args
        self.grace = grace
        self.prompter = WebPrompter()
        self.html = _load_html()
        self.httpd = _Server(("127.0.0.1", getattr(args, "port", 8765)), _Handler)
        self.httpd.app = self  # type: ignore[attr-defined]
        self.port = self.httpd.server_address[1]  # --port 0 なら実ポートに解決済み

    def start_wizard(self) -> None:
        from jibun_kit.app import wizard

        def target():
            st = self.prompter.state
            try:
                rc = wizard.run(self.args, prompter=self.prompter)
            except BaseException as e:  # 想定外 — ブラウザを永久「考え中」にしない
                traceback.print_exc()
                with st.lock:
                    st.transcript.append(
                        {"kind": "say", "text": f"エラーが発生しました: {e}"})
                rc = 1
            with st.lock:
                st.done = True
                st.rc = rc
                if rc == 130:
                    st.transcript.append(
                        {"kind": "say",
                         "text": "進捗を保存しました。`jibun app` でいつでも続きから再開できます。"})
            # done をブラウザが受け取るまで grace 待ち、来なくても必ず止める
            st.final_seen.wait(timeout=self.grace)
            self.httpd.shutdown()  # 唯一の shutdown 呼び出し元

        threading.Thread(target=target, daemon=True).start()

    def serve(self) -> int:
        st = self.prompter.state
        try:
            self.httpd.serve_forever(poll_interval=0.1)
        except KeyboardInterrupt:
            self.httpd.server_close()
            print("\n\n進捗を保存しました。`jibun app --web` でいつでも続きから再開できます。")
            return 130
        self.httpd.server_close()
        with st.lock:
            return st.rc if st.rc is not None else 130


def run_web(args) -> int:
    """``jibun app --web`` のエントリポイント。"""
    try:
        server = AppServer(args)
    except OSError as e:
        print(f"error: ポート {getattr(args, 'port', '?')} で待ち受けできません（{e}）。"
              "--port で別の番号を指定してください。", file=sys.stderr)
        return 1
    url = f"http://127.0.0.1:{server.port}/"
    # WSL 等では webbrowser.open が無音 no-op のことがあるため URL は必ず表示する
    print(f"jibun app (web) — {url} をブラウザで開いてください（終了はターミナルで Ctrl-C）")
    server.start_wizard()
    if not getattr(args, "no_browser", False):
        try:
            webbrowser.open(url)
        except Exception:
            pass
    return server.serve()
