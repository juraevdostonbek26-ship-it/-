"""Сервер (вебхук) синови: ҳақиқий HTTP орқали. Хавфсизлик: нотўғри махфий/бош сўров ўтмаслиги."""
import json, os, tempfile, threading, urllib.error, urllib.request
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
import bot, logic as L, server
from fake_telegram import FakeTelegram

SECRET = "test_secret_0123456789_abcdef"


def start():
    fake = FakeTelegram()
    db = L.connect(os.path.join(tempfile.mkdtemp(), "s.db"))
    app = bot.App(db, bot.Tg("TOKEN", fake.url))
    srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(app, SECRET))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return fake, db, app, srv, f"http://127.0.0.1:{srv.server_address[1]}"


def bot_msgs(fake, uid):
    return [x for x in fake.visible(uid) if x[1] == "bot"]


def req(url, data=None, headers=None, method=None):
    r = urllib.request.Request(url, data, headers or {}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as x:
            return x.status, x.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def post_update(base, up, path=None, headers=None):
    return req(base + (path or f"/webhook/{SECRET}"), json.dumps(up).encode(), {"Content-Type": "application/json", **(headers or {})})


def test_healthz_and_unknown_paths():
    fake, db, app, srv, base = start()
    try:
        assert req(base + "/healthz")[0] == 200 and json.loads(req(base + "/healthz")[1]) == {"ok": True}
        assert req(base + "/healthz", method="HEAD")[0] == 200
        assert req(base + "/nope")[0] == 404 and req(base + "/webhook/x", method="GET")[0] == 404
    finally:
        srv.shutdown(); fake.close()


def test_webhook_start_reaches_bot_and_wrong_secret_is_rejected():
    fake, db, app, srv, base = start()
    try:
        fake.say(7, "/start"); up = fake.updates[-1]
        code, _ = post_update(base, up, path="/webhook/wrong_secret_value_0123456789")
        assert code == 404 and not bot_msgs(fake, 7), "нотўғри махфий билан хабар ўтди"
        code, _ = post_update(base, up, headers={"X-Telegram-Bot-Api-Secret-Token": "bad"})
        assert code == 403 and not bot_msgs(fake, 7)
        code, _ = post_update(base, up, headers={"X-Telegram-Bot-Api-Secret-Token": SECRET})
        assert code == 200
        texts = [x[2] for x in bot_msgs(fake, 7)]
        assert any("Tilni tanlang" in t for t in texts), texts  # биринчи марта: тил сўралади
        assert not app.errors, app.errors
    finally:
        srv.shutdown(); fake.close()


def test_garbage_and_oversize_do_not_break_server():
    fake, db, app, srv, base = start()
    try:
        assert req(base + f"/webhook/{SECRET}", b"not json", {"Content-Length": "8"})[0] == 400
        assert req(base + f"/webhook/{SECRET}", b"", {})[0] == 400
        assert req(base + f"/webhook/{SECRET}", b"[1,2]", {})[0] == 200  # JSON, лекин update эмас — эътибор берилмайди
        try:
            assert req(base + f"/webhook/{SECRET}", b"x" * 1_200_000, {})[0] == 400
        except urllib.error.URLError:
            pass  # сервер катта танани ўқимасдан узиб қўйди — ҳам тўғри
        assert post_update(base, {"update_id": 1, "message": {"chat": {"id": 9, "type": "group"}, "from": {"id": 9}, "text": "/start"}})[0] == 200
        assert req(base + "/healthz")[0] == 200
        assert not app.errors, app.errors
    finally:
        srv.shutdown(); fake.close()


def test_set_webhook_sends_secret_and_url():
    fake, db, app, srv, base = start()
    try:
        server.set_webhook(app, "https://doju.example.com/", SECRET)
        w = fake.webhook
        assert w["url"] == f"https://doju.example.com/webhook/{SECRET}" and w["secret_token"] == SECRET
        assert set(w["allowed_updates"]) == {"message", "callback_query"}
    finally:
        srv.shutdown(); fake.close()


def test_weak_secret_is_refused():
    for bad in ("short", "has space in it 0123456789", "x" * 300):
        try:
            server.build({"WEBHOOK_SECRET": bad, "TELEGRAM_BOT_TOKEN": "t"})
            assert False, f"заиф махфий қабул қилинди: {bad[:10]!r}"
        except SystemExit:
            pass


def test_tick_loop_runs_repeatedly_and_survives_errors():
    class Stub:
        n = 0
        errors = []
        def tick(self):
            Stub.n += 1
            if Stub.n == 2:
                raise RuntimeError("тасодифий хато")
    old = server.TICK_SECONDS
    server.TICK_SECONDS = 0.05
    stop = threading.Event()
    t = threading.Thread(target=server.tick_loop, args=(Stub(), stop), daemon=True)
    t.start()
    import time; time.sleep(0.5); stop.set(); t.join(2)
    server.TICK_SECONDS = old
    assert Stub.n >= 4, Stub.n  # хатодан кейин ҳам давом этди


def test_secret_is_derived_from_token_when_not_given():
    a = server.derive_secret("111:AAA"); b = server.derive_secret("222:BBB")
    assert a != b and a == server.derive_secret("111:AAA") and server.SECRET_RE.match(a) and "111" not in a
    app, secret = server.build({"TELEGRAM_BOT_TOKEN": "111:AAA", "DB_PATH": os.path.join(tempfile.mkdtemp(), "d.db")})
    assert secret == a


# ---------- Mini App йўллари ----------
import time as _time
import webapi
API_TOKEN = "777:API-TEST-TOKEN"


def start_api():
    fake = FakeTelegram()
    db = L.connect(os.path.join(tempfile.mkdtemp(), "a.db"))
    app = bot.App(db, bot.Tg("TOKEN", fake.url))
    srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(app, SECRET, API_TOKEN))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    for uid in (1, 2):
        L.ensure_user(db, uid, uid); L.set_user(db, uid, lang="uz")
    return fake, db, app, srv, f"http://127.0.0.1:{srv.server_address[1]}"


def init_for(uid, token=API_TOKEN, age=0):
    return webapi.sign_init_data({"auth_date": str(int(_time.time()) - age), "user": json.dumps({"id": uid})}, token)


def api(base, action, uid=None, payload=None, init=None):
    h = {"X-Telegram-Init-Data": init if init is not None else (init_for(uid) if uid else "")}
    if payload is not None:
        h["Content-Type"] = "application/json"
    code, body = req(base + "/app/api/" + action, None if payload is None else json.dumps(payload).encode(), h)
    return code, json.loads(body or b"{}")


def test_api_requires_valid_signature_and_isolates_users():
    fake, db, app, srv, base = start_api()
    try:
        assert api(base, "state")[0] == 401  # имзосиз
        assert api(base, "state", init=init_for(1, token="1:OTHER"))[0] == 401  # бошқа токен
        assert api(base, "state", init=init_for(1, age=2 * 86400))[0] == 401  # эскирган
        code, st = api(base, "state", 1); assert code == 200 and st["reminders"] == []
        good = {"title": "Maxfiy", "freq": "daily", "times": ["09:00"]}
        code, st = api(base, "reminder", 1, good); assert code == 200 and st["reminders"][0]["title"] == "Maxfiy"
        rid = st["reminders"][0]["id"]
        assert api(base, "state", 2)[1]["reminders"] == []  # иккинчи одам кўрмайди
        for action, p in (("delete", {"id": rid}), ("pause", {"id": rid}), ("reminder", {**good, "id": rid})):
            assert api(base, action, 2, p)[0] == 404, action
        assert api(base, "state", 1)[1]["reminders"][0]["title"] == "Maxfiy"
        # ID имзода алмаштирилса (2 номидан 1 нинг маълумотини сўраш) ўтмайди
        forged = init_for(2).replace("%22id%22%3A+2", "%22id%22%3A+1")
        assert api(base, "state", init=forged)[0] == 401
        assert api(base, "nope", 1, {})[0] == 404
        assert api(base, "reminder", 1, {"title": ""})[0] == 400
        assert req(base + "/app/api/reminder", b"not json", {"X-Telegram-Init-Data": init_for(1)})[0] == 400
        assert not app.errors
    finally:
        srv.shutdown(); fake.close()


def test_api_user_without_start_gets_clear_error_and_page_served_with_csp():
    fake, db, app, srv, base = start_api()
    try:
        code, body = api(base, "state", 555)
        assert code == 403 and body["error"] == "start_bot"
        r = urllib.request.urlopen(base + "/app/")
        html = r.read().decode()
        assert r.status == 200 and "DOJU" in html and "telegram-web-app.js" in html
        assert "default-src 'none'" in r.headers["Content-Security-Policy"] and r.headers["X-Content-Type-Options"] == "nosniff"
        # токенсиз сервер (ёки хато созлама) API'ни бермайди
        srv2 = server.ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(app, SECRET, None))
        threading.Thread(target=srv2.serve_forever, daemon=True).start()
        base2 = f"http://127.0.0.1:{srv2.server_address[1]}"
        assert api(base2, "state", 1)[0] == 404
        srv2.shutdown()
    finally:
        srv.shutdown(); fake.close()


def test_web_button_in_home_menu_and_menu_button_set():
    fake, db, app, srv, base = start()
    old = bot.WEBAPP_URL
    try:
        assert not any("web_app" in b for row in bot.home_markup("uz")["inline_keyboard"] for b in row)  # URL йўқ — тугма йўқ
        bot.WEBAPP_URL = "https://doju.example.com/app/"
        btns = [b for row in bot.home_markup("ru")["inline_keyboard"] for b in row if "web_app" in b]
        assert btns and btns[0]["web_app"]["url"] == "https://doju.example.com/app/" and "Веб" in btns[0]["text"]
        server.set_menu_button(app, "https://doju.example.com/app/")
        assert fake.menu_button["menu_button"]["web_app"]["url"] == "https://doju.example.com/app/"
        # меню ҳақиқатан юборилади ва сохта Telegram уни қабул қилади
        fake.say(7, "/start"); post_update(base, fake.updates[-1])
        fake.click(7, "🇺🇿 UZB"); post_update(base, fake.updates[-1])
        assert not fake.errors, fake.errors
        assert any(x[1] == "🌐 Veb oyna" for x in fake.buttons(7)), fake.buttons(7)
    finally:
        bot.WEBAPP_URL = old
        srv.shutdown(); fake.close()
