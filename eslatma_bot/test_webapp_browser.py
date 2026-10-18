"""Mini App саҳифасини ҲАҚИҚИЙ браузерда босиб текширади (Telegram имзоси билан, сервер ва база ҳақиқий).
Ҳар босилган нарса базада текширилади. Ишга тушириш: python3 test_webapp_browser.py"""
import glob, json, os, sys, tempfile, threading, time
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
import bot, logic as L, server, webapi
from fake_telegram import FakeTelegram

TOKEN = "888:BROWSER-TEST"
SECRET = "browser_secret_0123456789_abcd"
res = []


def check(name, cond):
    res.append((name, bool(cond)))
    print(("OK   " if cond else "FAIL ") + name)


def main():
    from playwright.sync_api import sync_playwright
    fake = FakeTelegram()
    db = L.connect(os.path.join(tempfile.mkdtemp(), "b.db"))
    app = bot.App(db, bot.Tg("T", fake.url))
    for uid in (1, 2):
        L.ensure_user(db, uid, uid); L.set_user(db, uid, lang="uz")
    L.add_reminder(db, 2, {"title": "BOSHQANING", "freq": "daily", "times": ["09:00"]})
    srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(app, SECRET, TOKEN))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    init = webapi.sign_init_data({"auth_date": str(int(time.time())), "user": json.dumps({"id": 1})}, TOKEN)
    ch = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")[0]
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=ch, args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": 400, "height": 850})
        errs, bad_req = [], []
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "telegram" not in m.text.lower() and "Failed to load resource" not in m.text else None)
        pg.on("response", lambda r: bad_req.append((r.url, r.status)) if r.status >= 400 and "telegram.org" not in r.url else None)
        pg.route("https://telegram.org/**", lambda r: r.fulfill(status=200, content_type="application/javascript", body=""))
        pg.add_init_script("window.Telegram={WebApp:{initData:%s,ready(){},expand(){},setHeaderColor(){},setBackgroundColor(){}}}" % json.dumps(init))
        pg.goto(base + "/app/")
        pg.wait_for_selector(".stat")
        view = lambda: pg.inner_text("#view")
        tab = lambda n: pg.click(f'#tabs button[data-tab="{n}"]')
        rems = lambda: db.execute("select * from reminders where user_id=1 order by id").fetchall()

        check("Саҳифа очилди, бошқанинг эслатмаси кўринмайди", "BOSHQANING" not in pg.content() and pg.locator(".stat").count() == 3)
        # ---- Янги эслатма: ҳар тур
        tab("new")
        pg.click('[data-act="save"]'); check("Бўш номда хато", pg.inner_text("#err") != "")
        pg.fill("#f-title", "Ijara"); pg.click('[data-act="save"]'); check("Кун танланмаса хато", pg.inner_text("#err") != "")
        pg.locator('.day[data-v="31"]').click(); pg.fill("#f-amt", "5000000"); pg.click('[data-act="lead"][data-v="3"]')
        pg.fill("#f-time", "15:30"); pg.click('[data-act="addtime"]')
        pg.click('[data-act="time"][data-v="12:00"]')
        pg.click('[data-act="save"]'); pg.wait_for_selector("#toast:not([hidden])")
        r = rems()[0]
        check("Ой охири+сумма+3 кун олдин+соатлар базага ёзилди", (r["title"], r["freq"], r["day"], r["amount"], r["lead_days"], L.times_of(r)) == ("Ijara", "monthly", 31, "5000000", 3, ["09:00", "12:00", "15:30"]))
        tab("new"); pg.fill("#f-title", "Haftalik"); pg.click('[data-act="freq"][data-v="weekly"]'); pg.click('[data-act="save"]')
        check("Ҳафта куни танланмаса хато", pg.inner_text("#err") != "")
        pg.click('[data-act="wd"][data-v="4"]'); pg.click('[data-act="save"]'); pg.wait_for_selector("#toast:not([hidden])")
        check("Ҳафталик (жума) базада", rems()[1]["freq"] == "weekly" and rems()[1]["day"] == 4)
        tab("new"); pg.fill("#f-title", "Bir marta"); pg.click('[data-act="freq"][data-v="once"]'); pg.click('[data-act="save"]')
        check("Санасиз хато", pg.inner_text("#err") != "")
        from datetime import date, timedelta
        pg.fill("#f-date", (date.today() + timedelta(days=5)).isoformat()); pg.click('[data-act="save"]'); pg.wait_for_selector("#toast:not([hidden])")
        check("Бир марталик базада", rems()[2]["freq"] == "once")
        tab("new"); pg.fill("#f-title", "Kunlik"); pg.click('[data-act="freq"][data-v="daily"]'); pg.click('[data-act="save"]'); pg.wait_for_selector("#toast:not([hidden])")
        check("Ҳар кунги базада", rems()[3]["freq"] == "daily")
        # ---- Ҳаммаси ва таҳрир
        tab("list"); check("Рўйхатда 4 та", pg.locator(".card").count() == 4)
        pg.locator('.card [data-act="open"]').first.click()
        check("Эслатма очилди, ном ва кун тўлдирилган", pg.input_value("#f-title") == "Ijara" and pg.locator('.day.on[data-v="31"]').count() == 1)
        pg.fill("#f-title", "Ijara YANGI"); pg.locator('.day[data-v="5"]').click(); pg.click('[data-act="lead"][data-v="0"]'); pg.fill("#f-amt", "7000000")
        pg.click('[data-act="save"]'); pg.wait_for_selector("#toast:not([hidden])")
        r = rems()[0]
        check("Таҳрир: ном, кун, олдиндан, сумма базада ўзгарди", (r["title"], r["day"], r["lead_days"], r["amount"]) == ("Ijara YANGI", 5, 0, "7000000"))
        pg.wait_for_selector(".card")
        tab("list"); pg.locator('.card [data-act="open"]').first.click(); pg.click('[data-act="pause"]'); pg.wait_for_timeout(300)
        check("Пауза базада", rems()[0]["active"] == 0)
        pg.click('[data-act="pause"]'); pg.wait_for_timeout(300); check("Давом эттириш базада", rems()[0]["active"] == 1)
        pg.click('[data-act="skip"]'); pg.wait_for_timeout(300)
        check("Кейингисини ўтказиш базада", db.execute("select count(*) from occ where reminder_id=? and status='skipped'", (rems()[0]["id"],)).fetchone()[0] == 1)
        pg.click('[data-act="cancelEdit"]'); check("Бекор қилиш рўйхатга қайтаради", "hammasi" in view().lower())
        # ---- Бугун: бажарилди / кейинроқ
        t0 = time.time(); u = L.get_user(db, 1)
        dl = L.add_reminder(db, 1, {"title": "Hozir", "freq": "daily", "times": ["00:00"]}, t0 - 86400 * 2)
        L.sync(db, t0)
        tab("home"); pg.reload(); pg.wait_for_selector(".stat")
        check("Бугунги эслатма кўринди (база→веб)", "Hozir" in view())
        pg.locator('[data-act="later"]').first.click(); check("Кейинроқ вариантлари", pg.locator('[data-act="snz"]').count() == 4)
        pg.locator('[data-act="snz"][data-v="60"]').first.click(); pg.wait_for_timeout(300)
        o = db.execute("select next_ts, status from occ where reminder_id=?", (dl,)).fetchall()
        check("Кейинроқ: бир соатдан кейинга қўйилди", any(x["status"] == "pending" and 3500 < x["next_ts"] - t0 < 3700 for x in o))
        pg.locator('[data-act="done"]').first.click(); pg.wait_for_timeout(300)
        check("Бажарилди базада", db.execute("select count(*) from occ where reminder_id=? and status='done'", (dl,)).fetchone()[0] >= 1)
        # ---- Ўчириш
        tab("list"); n = pg.locator(".card").count(); pg.locator('.card [data-act="open"]').last.click()
        pg.click('[data-act="del"]'); check("Ўчиришда тасдиқ сўралди", pg.locator('[data-act="delyes"]').count() == 1)
        pg.click('[data-act="delno"]'); pg.click('[data-act="del"]'); pg.click('[data-act="delyes"]'); pg.wait_for_timeout(300)
        check("Ўчирилди", len(rems()) == n - 1)
        # ---- Созламалар
        tab("set")
        pg.click('[data-act="lang"][data-v="ru"]'); pg.wait_for_timeout(300)
        check("Тил РУС: базада ва матнда", L.get_user(db, 1)["lang"] == "ru" and "Настройки" in pg.inner_text("#tabs") and "Язык" in view())
        tab("home"); check("РУС: бугун экрани", any(w in view() for w in ("Просрочено", "Сегодня", "Скоро")))
        tab("set"); pg.click('[data-act="lang"][data-v="uz"]'); pg.wait_for_timeout(300); check("Тил UZB қайтди", L.get_user(db, 1)["lang"] == "uz")
        pg.click('[data-act="tz"][data-v="3"]'); pg.wait_for_timeout(300); check("Вақт зонаси +3 базада", L.get_user(db, 1)["tz"] == 3)
        pg.click('[data-act="tz"][data-v="5"]'); pg.wait_for_timeout(300); check("Вақт зонаси +5 қайтди", L.get_user(db, 1)["tz"] == 5)
        for v, want in (("0", 0), ("1", 1), ("3", 3), ("6", 6), ("0.016667", 0.016667)):
            pg.click(f'[data-act="rep"][data-v="{v}"]'); pg.wait_for_timeout(250)
            check(f"Такрор {v} базада", abs(L.get_user(db, 1)["repeat_h"] - want) < 1e-9)
        pg.click('[data-act="dg"][data-v="8"]'); pg.wait_for_timeout(250); check("Хулоса 08:00", L.get_user(db, 1)["digest_hour"] == 8)
        pg.click('[data-act="dg"][data-v="off"]'); pg.wait_for_timeout(250); check("Хулоса ўчиқ", L.get_user(db, 1)["digest_hour"] is None)
        check("Тинч соатлар фақат кўрсатилади (22–07)", "22:00–07:00" in view())
        pg.click('[data-act="fbtoggle"]'); pg.click('[data-act="fbsend"]'); check("Бўш хатга огоҳлантириш", pg.inner_text("#fberr") != "")
        pg.fill("#f-fb", "Veb oynadan salom"); pg.click('[data-act="fbsend"]'); pg.wait_for_timeout(300)
        check("Асосчига хат базага тушди", [x["text"] for x in L.unsent_feedback(db)] == ["Veb oynadan salom"])
        pg.click('[data-act="privtoggle"]'); check("Махфийлик очилади", "faqat siz" in view())
        # ---- асосчи ойнаси (фақат админга)
        check("Оддий фойдаланувчида «Xabarlar» табини йўқ", pg.locator("#tab-inbox").is_hidden() and "Rang yoqmadi" not in pg.content())
        app.admin_chat = 3
        L.ensure_user(db, 3, 3); L.set_user(db, 3, lang="uz")
        L.add_feedback(db, 2, "Tugma kichik", time.time()); L.add_feedback(db, 2, "Rang yoqmadi", time.time())
        init3 = webapi.sign_init_data({"auth_date": str(int(time.time())), "user": json.dumps({"id": 3})}, TOKEN)
        ctx3 = b.new_context(viewport={"width": 400, "height": 850}); pa = ctx3.new_page()
        pa.route("https://telegram.org/**", lambda r: r.fulfill(status=200, content_type="application/javascript", body=""))
        pa.add_init_script("window.Telegram={WebApp:{initData:%s,ready(){},expand(){}}}" % json.dumps(init3))
        pa.goto(base + "/app/"); pa.wait_for_selector(".stat")
        check("Асосчида «Xabarlar» табини кўринади (3 та янги: 2 + аввалги 1)", pa.locator("#tab-inbox").is_visible() and pa.inner_text("#inbox-n").strip() == "3")
        pa.click('#tabs button[data-tab="inbox"]')
        check("Хатлар кўринади, юборувчи номисиз", "Rang yoqmadi" in pa.inner_text("#view") and "Tugma kichik" in pa.inner_text("#view") and "user" not in pa.inner_text("#view").lower())
        pa.locator('[data-act="fbdone"]').first.click(); pa.wait_for_timeout(300)
        check("«Hal qilindi» базада", db.execute("select count(*) from feedback where done=1").fetchone()[0] == 1 and "Rang yoqmadi" not in pa.inner_text("#view"))
        pa.click('[data-act="fbfilter"][data-v="done"]'); check("Ҳал қилинганлар рўйхати", "Rang yoqmadi" in pa.inner_text("#view"))
        pa.click('[data-act="fbfilter"][data-v="all"]'); check("Ҳаммаси: 3 та", pa.locator(".fbtext").count() == 3)
        pa.locator('[data-act="fbdone"]').first.click(); pa.wait_for_timeout(300)
        check("Қайтариш базада", db.execute("select count(*) from feedback where done=1").fetchone()[0] == 0)
        # оддий фойдаланувчи API орқали ҳам админ амалини бажара олмайди
        code = pg.evaluate("fetch('/app/api/fb_done',{method:'POST',headers:{'X-Telegram-Init-Data':%s,'Content-Type':'application/json'},body:JSON.stringify({id:1,done:true})}).then(r=>r.status)" % json.dumps(init))
        check("Оддий фойдаланувчига админ амали рад этилди (403)", code == 403 and db.execute("select count(*) from feedback where done=1").fetchone()[0] == 0)
        bad_req.clear()
        # ---- имзосиз очилса
        pg2 = ctx.new_page(); pg2.route("https://telegram.org/**", lambda r: r.fulfill(status=200, content_type="application/javascript", body=""))
        pg2.goto(base + "/app/"); pg2.wait_for_timeout(500)
        check("Telegram'сиз очилса тушунарли хабар, маълумот йўқ", "Telegram" in pg2.inner_text("#view") and "YANGI" not in pg2.content() and "Haftalik" not in pg2.content())
        check("Кутилмаган HTTP хато (401/403 дан бошқа) йўқ", all(s in (401, 403) for u_, s in bad_req) or not bad_req)
        check("JS/CSP хатолари йўқ", not errs)
        if errs: print(errs)
        b.close()
    srv.shutdown(); fake.close()


if __name__ == "__main__":
    main()
    bad = [n for n, ok in res if not ok]
    print(f"\nЖами: {len(res)}, муваффақиятсиз: {len(bad)}")
    sys.exit(1 if bad else 0)
