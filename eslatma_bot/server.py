"""DOJU Эслатма Котиби — сервер (Render). Telegram хабарларини вебхук орқали қабул қилади.
/healthz — уйғотувчи (cron-job.org) учун; /webhook/<махфий> — Telegram учун. Эслатма таймери фонда ишлайди.
Муҳит ўзгарувчилари: TELEGRAM_BOT_TOKEN, DATABASE_URL (Neon), ADMIN_ID; ихтиёрий: WEBHOOK_SECRET, BASE_URL (Render RENDER_EXTERNAL_URL ни ўзи беради)."""
import hmac, json, os, re, sys, threading, time, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import bot
import logic as L
import webapi

LOCK = threading.RLock()  # битта уланиш: хабар ва таймер навбат билан ишлайди
TICK_SECONDS = 15
MAX_BODY = 1_000_000
MAX_API_BODY = 100_000
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp")
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
ASSETS = {"doju_ovoz.mp3": "audio/mpeg", "doju_fon.png": "image/png"}  # фақат шу файллар (йўл ўзгартириб бошқа файл олиб бўлмайди)
CSP = ("default-src 'none'; script-src 'unsafe-inline' https://telegram.org; style-src 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src data:; connect-src 'self'; base-uri 'none'; form-action 'none'")
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


def make_handler(app, secret, bot_token=None):
    class H(BaseHTTPRequestHandler):
        server_version = "DOJU"

        def log_message(self, fmt, *args):  # йўл (ичида махфий) логга ёзилмайди
            pass

        def _send(self, code, body=b"", ctype="application/json", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            for k, v in (extra or {}).items():
                self.send_header(k, v)
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
            path = self.path.split("?")[0]
            if path in ("/app", "/app/"):
                try:
                    with open(os.path.join(WEB_DIR, "index.html"), "rb") as f:
                        return self._send(200, f.read(), "text/html; charset=utf-8", {"Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})
                except OSError:
                    return self._send(404)
            if path.startswith("/assets/") and path[len("/assets/"):] in ASSETS:
                name = path[len("/assets/"):]
                with open(os.path.join(ASSET_DIR, name), "rb") as f:
                    return self._send(200, f.read(), ASSETS[name], {"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"})
            if path == "/app/api/state":
                return self._api("state", None)
            self._send(404)

        def _api(self, action, payload):
            """Mini App: имзо текширилади, ҳар қандай амал фақат шу фойдаланувчи маълумотига тегади."""
            hdr = {"Cache-Control": "no-store"}
            try:
                if not bot_token:
                    raise webapi.ApiError("off", 404)
                uid = webapi.verify_init_data(self.headers.get("X-Telegram-Init-Data", ""), bot_token)
                with LOCK:
                    if app.limited(uid):
                        raise webapi.ApiError("slow_down", 429)
                    out = webapi.handle(app.db, uid, action, payload if payload is not None else {}, time.time(), app.admin_chat)
                self._send(200, json.dumps(out, ensure_ascii=False).encode(), extra=hdr)
            except webapi.ApiError as e:
                self._send(e.status, json.dumps({"error": e.code}).encode(), extra=hdr)
            except Exception as e:
                log("API хатоси:", type(e).__name__)
                self._send(500, b'{"error": "server"}', extra=hdr)

        def do_POST(self):
            if self.path.startswith("/app/api/"):
                try:
                    n = int(self.headers.get("Content-Length", "0"))
                    body = json.loads(self.rfile.read(n)) if 0 < n <= MAX_API_BODY else None
                except ValueError:
                    body = None
                if body is None:
                    return self._send(400, b'{"error": "bad_request"}')
                return self._api(self.path[len("/app/api/"):].split("?")[0], body)
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


DEFAULT_VIDEO = {"uz": "https://t.me/doju_eslatma/3", "ru": "https://t.me/doju_eslatma/4"}  # канал постлари (оммавий ҳавола, махфий эмас)


def video_links(env):
    """Видео қўлланма ҳаволалари: env (VIDEO_URL_UZ/RU ёки умумий VIDEO_URL) устун, бўлмаса канал постлари; фақат https."""
    one = env.get("VIDEO_URL", "")
    out = {}
    for lg in ("uz", "ru"):
        u = env.get(f"VIDEO_URL_{lg.upper()}") or one or DEFAULT_VIDEO[lg]
        out[lg] = u if u.startswith("https://") else ""
    return out


def set_menu_button(app, url):
    """Чатдаги пастки «Открыть» тугмаси веб ойнани очади. Хато бўлса бот ишлашда давом этади."""
    try:
        r = app.tg.call("setChatMenuButton", menu_button={"type": "web_app", "text": "DOJU", "web_app": {"url": url}})
        log("меню тугмаси ўрнатилди" if r.get("ok") else "меню тугмаси ўрнатилмади")
    except Exception as e:
        log("меню тугмаси ўрнатилмади:", type(e).__name__)


def build(env=os.environ):
    secret = env.get("WEBHOOK_SECRET") or derive_secret(env["TELEGRAM_BOT_TOKEN"])
    if not SECRET_RE.match(secret):
        raise SystemExit("WEBHOOK_SECRET нотўғри: 16–200 та ҳарф/рақам/_/- бўлиши керак (ёки бутунлай бўш қолдиринг).")
    conn = L.connect(env.get("DATABASE_URL") or env.get("DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db"))
    app = bot.App(conn, bot.Tg(env["TELEGRAM_BOT_TOKEN"]))
    app.token = env["TELEGRAM_BOT_TOKEN"]
    return app, secret


def main():
    app, secret = build()
    bot.VIDEO_URL.update(video_links(os.environ))
    webapi.VIDEO.update(bot.VIDEO_URL)
    base = os.environ.get("BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL")
    try:
        me = app.tg.call("getMe").get("result", {})
        log("бот танилди: @" + str(me.get("username")))
    except Exception as e:
        log("ТОКЕН ЎТМАДИ (getMe хатоси):", type(e).__name__, "— токенни текширинг")
    if base:
        bot.WEBAPP_URL = base.rstrip("/") + "/app/"
        bot.ASSET_BASE = base.rstrip("/")
        set_webhook(app, base, secret)
        set_menu_button(app, bot.WEBAPP_URL)
    else:
        log("ОГОҲЛАНТИРИШ: BASE_URL йўқ, вебхук ўрнатилмади")
    stop = threading.Event()
    threading.Thread(target=tick_loop, args=(app, stop), daemon=True).start()
    port = int(os.environ.get("PORT", "10000"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), make_handler(app, secret, app.token))
    log(f"сервер ишга тушди, порт {port}")
    try:
        srv.serve_forever()
    finally:
        stop.set()


if __name__ == "__main__":
    main()
