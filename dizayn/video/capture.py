"""Видео учун ҲАҚИҚИЙ веб ойнанинг скриншотларини олади (намуна маълумот билан, Telegram имзоси билан).
Ишга тушириш: python3 capture.py uz  |  python3 capture.py ru   → shots/<тил>_*.png ва shots/<тил>.json (босиш нуқталари)"""
import glob, json, os, sys, tempfile, threading, time
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "eslatma_bot"))
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
import bot, logic as L, server, webapi
from fake_telegram import FakeTelegram

TOKEN = "999:VIDEO-DEMO"
SECRET = "video_secret_0123456789_abcdefg"
DSF = 2.5
VW, VH = 432, 768
SHOTS = os.path.join(os.path.dirname(__file__), "shots")

TEXT = {
    "uz": {"title": "Ijara to'lovi", "t1": "Ij", "demo": ["Ofis ijarasi", "Xodimlarga oylik", "Internet (WiFi)", "Soliq hisoboti", "CRM obunasi"]},
    "ru": {"title": "Аренда офиса", "t1": "Аре", "demo": ["Аренда офиса", "Зарплата сотрудникам", "Интернет (WiFi)", "Налоговая отчётность", "Подписка CRM"]},
}


def seed(db, lang):
    from datetime import datetime, timedelta, timezone
    now = time.time(); uid = 1
    L.ensure_user(db, uid, uid); L.set_user(db, uid, lang=lang)
    local = lambda ts: L.local_dt(L.get_user(db, uid), ts).date()
    day_of = lambda k: local(now + k * 86400).day
    names = TEXT[lang]["demo"]
    created = now - 45 * 86400
    # 1) 2 кун олдин муддати ўтган ижара: ўша кунги вақтда sync, ҳозир «Муддати ўтган» бўлиб кўринади
    L.add_reminder(db, uid, {"title": names[0], "freq": "monthly", "day": day_of(-2), "times": ["09:00"], "amount": "5000000"}, created)
    L.sync(db, now - 2 * 86400 + 3600)
    # 2) бугунги: ойлик ва интернет
    L.add_reminder(db, uid, {"title": names[1], "freq": "monthly", "day": day_of(0), "times": ["18:00"], "amount": "48500000"}, created)
    L.add_reminder(db, uid, {"title": names[2], "freq": "monthly", "day": day_of(0), "times": ["20:00"], "amount": "350000"}, created)
    L.sync(db, now)
    # 3) яқин кунлар
    L.add_reminder(db, uid, {"title": names[3], "freq": "once", "date": str(local(now + 2 * 86400)), "times": ["10:00"]}, now - 3600)
    L.add_reminder(db, uid, {"title": names[4], "freq": "monthly", "day": day_of(7), "times": ["10:00"], "amount": "1200000"}, now - 3600)
    L.sync(db, now)


def main(lang):
    from playwright.sync_api import sync_playwright
    os.makedirs(SHOTS, exist_ok=True)
    fake = FakeTelegram()
    db = L.connect(os.path.join(tempfile.mkdtemp(), "v.db"))
    app = bot.App(db, bot.Tg("T", fake.url)); seed(db, lang)
    srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(app, SECRET, TOKEN))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    init = webapi.sign_init_data({"auth_date": str(int(time.time())), "user": json.dumps({"id": 1})}, TOKEN)
    ch = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")[0]
    taps, T = {}, TEXT[lang]
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=ch, args=["--no-sandbox"])
        pg = b.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=DSF).new_page()
        pg.route("https://telegram.org/**", lambda r: r.fulfill(status=200, content_type="application/javascript", body=""))
        pg.add_init_script("window.Telegram={WebApp:{initData:%s,ready(){},expand(){},setHeaderColor(){},setBackgroundColor(){}}}" % json.dumps(init))
        pg.goto(base + "/app/"); pg.wait_for_selector(".stat"); pg.wait_for_timeout(400)

        def shot(name, tap=None, toast=False):
            pg.wait_for_timeout(450)
            if not toast:
                pg.evaluate("document.getElementById('toast').hidden=true")
            pg.screenshot(path=os.path.join(SHOTS, f"{lang}_{name}.png"))
            taps[name] = tap

        def center(sel, nth=0):
            bb = pg.locator(sel).nth(nth).bounding_box()
            return [round((bb["x"] + bb["width"] / 2) * DSF), round((bb["y"] + bb["height"] / 2) * DSF)]

        def click(sel, nth=0):
            c = center(sel, nth); pg.locator(sel).nth(nth).click(); return c

        def scroll(y):
            pg.evaluate(f"window.scrollTo(0,{y})"); pg.wait_for_timeout(150)

        shot("home")
        # ---- янги эслатма
        tap = click('#tabs button[data-tab="new"]'); shot("new_empty", tap)
        pg.locator("#f-title").click(); pg.keyboard.type(T["t1"]); shot("new_t1", center("#f-title"))
        pg.fill("#f-title", T["title"]); shot("new_t2", center("#f-title"))
        scroll(260); tap = click('.day[data-v="5"]'); shot("new_day", tap)
        tap = click('[data-act="time"][data-v="12:00"]'); shot("new_time", tap)
        pg.fill("#f-amt", "5000000"); scroll(10000); shot("new_amount", center("#f-amt"))
        tap = click('[data-act="save"]'); pg.wait_for_selector("#toast:not([hidden])"); scroll(0); shot("saved", tap, toast=True)
        # ---- бажарилди / кейинроқ
        tap = click('[data-act="later"]', 1); shot("later", tap)
        tap = click('[data-act="snz"][data-v="60"]'); shot("later_ok", tap, toast=True)
        tap = click('[data-act="done"]', 0); shot("done", tap, toast=True)
        # ---- рўйхат ва таҳрир
        tap = click('#tabs button[data-tab="list"]'); shot("list", tap)
        tap = click('.card [data-act="open"]', 0); shot("edit", tap)
        scroll(10000); shot("edit_bottom")
        click('[data-act="cancelEdit"]')
        # ---- созламалар
        tap = click('#tabs button[data-tab="set"]'); shot("set_top", tap)
        tap = click('[data-act="rep"][data-v="0.016667"]'); shot("set_rep", tap)
        scroll(10000); shot("set_bottom")
        b.close()
    srv.shutdown(); fake.close()
    json.dump(taps, open(os.path.join(SHOTS, f"{lang}.json"), "w"))
    print(lang, "OK", len(taps), "shots")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "uz")
