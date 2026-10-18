"""DOJU Эслатма Котиби — сервер (Render). Telegram хабарларини вебхук орқали қабул қилади.
/healthz — уйғотувчи (cron-job.org) учун; /webhook/<махфий> — Telegram учун. Эслатма таймери фонда ишлайди.
Муҳит ўзгарувчилари: TELEGRAM_BOT_TOKEN, DATABASE_URL (Neon), ADMIN_ID; ихтиёрий: WEBHOOK_SECRET, BASE_URL (Render RENDER_EXTERNAL_URL ни ўзи беради)."""
import hmac, json, os, re, sys, threading, time, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import bot
import logic as L

LOCK = threading.RLock()  # битта уланиш: хабар ва таймер навбат билан ишлайди
TICK_SECONDS = 15
MAX_BODY = 1_000_000
SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{16,200}$")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def process_update(app, up):
    """Битта янгиликни ишлайди; хато бўлса сервер тўхтамайди (худди poll() каби)."""
    with LOCK:
        try:
            if "message" in up:
                app.on_message(up["message"])
            elif "callback_query" in up:
                app.on_callback(up["callback_query"])
        except Exception as e:
            fr = traceback.extract_tb(e.__traceback__)[-1]
            app.errors.append(f"{type(e).__name__}: {e} ({fr.name}:{fr.lineno})")
            log("ИШЛОВ ХАТОСИ:", type(e).__name__, "— қатор", fr.lineno, fr.name)


def tick_loop(app, stop):
    while not stop.is_set():
        with LOCK:
            try:
                app.tick()
            except Exception as e:
                log("таймер хатоси:", type(e).__name__)
        stop.wait(TICK_SECONDS)


def make_handler(app, secret):
    class H(BaseHTTPRequestHandler):
        server_version = "DOJU"

        def log_message(self, fmt, *args):  # йўл (ичида махфий) логга ёзилмайди
            pass

        def _send(self, code, body=b"", ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if self.path.split("?")[0] == "/healthz":
                return self._send(200, b'{"ok": true}')
            if self.path == "/":
                return self._send(200, "DOJU Eslatma Kotibi".encode(), "text/plain; charset=utf-8")
            self._send(404)

        def do_POST(self):
            prefix = "/webhook/"
            if not self.path.startswith(prefix) or not hmac.compare_digest(self.path[len(prefix):], secret):
                log("вебхук: нотўғри йўл (рад этилди)")
                return self._send(404)
            hdr = self.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if hdr is not None and not hmac.compare_digest(hdr, secret):
                return self._send(403)
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self._send(400)
            if n <= 0 or n > MAX_BODY:
                return self._send(400)
            try:
                up = json.loads(self.rfile.read(n))
            except ValueError:
                return self._send(400)
            if isinstance(up, dict):
                log("вебхук: янгилик келди —", "тугма" if "callback_query" in up else "хабар")
                process_update(app, up)
            self._send(200, b'{"ok": true}')  # Telegram'га ҳар доим 200 (хато бўлса ҳам қайта-қайта юбормасин)

    return H


def set_webhook(app, base_url, secret):
    try:
        r = app.tg.call("setWebhook", url=f"{base_url.rstrip('/')}/webhook/{secret}", secret_token=secret,
                        allowed_updates=["message", "callback_query"], drop_pending_updates=False)
        log("вебхук ўрнатилди" if r.get("ok") else "вебхук ўрнатилмади: " + str(r.get("description")))
    except Exception as e:  # Telegram жавоби (масалан 401 — токен нотўғри) сабабини логга чиқарамиз, токенсиз
        body = getattr(e, "read", lambda: b"")()
        log("вебхук ўрнатилмади:", type(e).__name__, body[:200].decode("utf-8", "replace") if body else "")


def derive_secret(token):
    """WEBHOOK_SECRET берилмаса, токендан ҳосил қилинади (токенсиз тахмин қилиб бўлмайди)."""
    return hmac.new(token.encode(), b"doju-webhook", "sha256").hexdigest()[:48]


def build(env=os.environ):
    secret = env.get("WEBHOOK_SECRET") or derive_secret(env["TELEGRAM_BOT_TOKEN"])
    if not SECRET_RE.match(secret):
        raise SystemExit("WEBHOOK_SECRET нотўғри: 16–200 та ҳарф/рақам/_/- бўлиши керак (ёки бутунлай бўш қолдиринг).")
    conn = L.connect(env.get("DATABASE_URL") or env.get("DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db"))
    app = bot.App(conn, bot.Tg(env["TELEGRAM_BOT_TOKEN"]))
    return app, secret


def main():
    app, secret = build()
    base = os.environ.get("BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL")
    try:
        me = app.tg.call("getMe").get("result", {})
        log("бот танилди: @" + str(me.get("username")))
    except Exception as e:
        log("ТОКЕН ЎТМАДИ (getMe хатоси):", type(e).__name__, "— токенни текширинг")
    if base:
        set_webhook(app, base, secret)
    else:
        log("ОГОҲЛАНТИРИШ: BASE_URL йўқ, вебхук ўрнатилмади")
    stop = threading.Event()
    threading.Thread(target=tick_loop, args=(app, stop), daemon=True).start()
    port = int(os.environ.get("PORT", "10000"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), make_handler(app, secret))
    log(f"сервер ишга тушди, порт {port}")
    try:
        srv.serve_forever()
    finally:
        stop.set()


if __name__ == "__main__":
    main()
