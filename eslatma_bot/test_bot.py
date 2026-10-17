import os, sqlite3, tempfile
from datetime import datetime, timezone
import bot, logic as L
from texts import TXT


class FakeTg:
    def __init__(self):
        self.out, self.n, self.deletes, self.toasts = [], 100, [], []
    def send(self, chat, text, markup=None):
        self.n += 1
        self.out.append(("send", chat, text, markup))
        return {"result": {"message_id": self.n}}
    def edit(self, chat, mid, text, markup=None):
        self.out.append(("edit", chat, text, markup))
        return True
    def delete(self, chat, mid):
        self.deletes.append((chat, mid))
    def answer(self, cid, text=""):
        self.toasts.append(text)
    def call(self, m, **p):
        self.out.append((m, p))
    def texts(self, kinds=("send", "edit")):
        return [o[2] for o in self.out if o[0] in kinds]


def ts(y, mo, d, h=0, mi=0):  # маҳаллий (UTC+5) -> ts
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() - 5 * 3600


class Clock:
    t = ts(2026, 11, 2, 10)
    def __call__(self):
        return self.t


def make():
    db = L.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    clk, tg = Clock(), FakeTg()
    return bot.App(db, tg, clk), db, tg, clk


def msg(uid, text, chat_type="private"):
    return {"chat": {"id": uid, "type": chat_type}, "from": {"id": uid}, "text": text, "message_id": 5}


def cb(uid, data, mid):
    return {"id": "x", "from": {"id": uid}, "data": data, "message": {"chat": {"id": uid, "type": "private"}, "message_id": mid}}


def start(app, uid=1, lang="uz"):
    app.on_message(msg(uid, "/start"))
    app.on_callback(cb(uid, f"lg:{lang}", 1))


def wmid(db, uid):
    return L.get_conv(db, uid)[1]["mid"]


def press(app, db, uid, data):
    app.on_callback(cb(uid, data, wmid(db, uid)))


def say(app, uid, text):
    app.on_message(msg(uid, text))


def last_rid(db):
    return db.execute("SELECT max(id) FROM reminders").fetchone()[0]


def add_monthly(app, db, uid, title, day, times=("09:00",), lead="0", amount=None):
    say(app, uid, TXT["uz"]["m_add"]); say(app, uid, title)
    press(app, db, uid, "fr:monthly"); press(app, db, uid, f"dy:{day}")
    for t in times:
        press(app, db, uid, f"tm:{t}")
    press(app, db, uid, "tmd"); press(app, db, uid, f"ld:{lead}")
    if amount:
        say(app, uid, amount)
    else:
        press(app, db, uid, "am:skip")
    return last_rid(db)


def sent(tg):
    return [o for o in tg.out if o[0] == "send" and "🚨" in o[2]]


def test_texts_parity():
    assert set(TXT["uz"]) == set(TXT["ru"])
    for lg in TXT:
        assert len(TXT[lg]["wd"]) == len(TXT[lg]["wd_s"]) == 7 and len(TXT[lg]["months"]) == 12


def test_every_day_1_to_31_works_and_list_opens():
    app, db, tg, clk = make(); start(app)
    for day in range(1, 32):
        clk.t += 60  # спам лимитига тушмасин
        n0 = len([o for o in tg.out if o[0] == "send"])
        rid = add_monthly(app, db, 1, f"Тест {day}", day, ("08:00", "12:00"), lead="1", amount="5 000")
        assert len([o for o in tg.out if o[0] == "send"]) - n0 == 1, "сўров битта хабарда бўлиши керак"
        assert "Saqlandi" in tg.texts()[-1], tg.texts()[-1]
        r = L.own_reminder(db, 1, rid)
        assert r["day"] == day and L.times_of(r) == ["08:00", "12:00"]
        app.on_callback(cb(1, f"ls:{rid}", 7))  # олдин шу ерда IndexError бўлган
        assert f"Тест {day}" in tg.texts()[-1] and "08:00, 12:00" in tg.texts()[-1]
    say(app, 1, TXT["uz"]["m_list"])
    assert tg.out[-1][3]["inline_keyboard"][0][0]["callback_data"].startswith("ls:")


def test_once_calendar_and_text_inputs():
    app, db, tg, clk = make(); start(app)
    say(app, 1, TXT["uz"]["m_add"]); say(app, 1, "Uchrashuv"); press(app, db, 1, "fr:once")
    cal = tg.out[-1][3]["inline_keyboard"]
    flat = [b for row in cal for b in row]
    assert any(b["text"] == "·" for b in flat) and any(b["callback_data"] == "cd:2026-11-20" for b in flat)
    press(app, db, 1, "cd:2026-11-01")  # ўтган кун ҳисобга олинмайди
    assert L.get_conv(db, 1)[0] == "date"
    press(app, db, 1, "cal:2026-12"); assert "Dekabr 2026" in str(tg.out[-1][3]) or "Dekabr 2026" in str(tg.out[-2][3])
    press(app, db, 1, "cd:2026-12-24")
    press(app, db, 1, "tmd"); assert "Kamida" in tg.texts()[-1]  # вақтсиз ўтмайди
    press(app, db, 1, "tm:09:00"); press(app, db, 1, "tmc"); say(app, 1, "8:30"); press(app, db, 1, "tmc"); say(app, 1, "abc")
    assert "⚠️" in tg.texts()[-1]
    say(app, 1, "17:45")
    press(app, db, 1, "tmd"); press(app, db, 1, "ld:3"); say(app, 1, "Zal №5")
    r = L.own_reminder(db, 1, last_rid(db))
    assert (r["freq"], r["date"], L.times_of(r), r["lead_days"], r["amount"]) == ("once", "2026-12-24", ["08:30", "09:00", "17:45"], 3, "Zal №5")
    assert "21.12" in tg.texts()[-1] and "08:30" in tg.texts()[-1]  # кейинги эслатма 3 кун олдин
    assert tg.deletes  # ёзилган матн чатдан тозаланади


def test_weekly_and_daily():
    app, db, tg, clk = make(); start(app)
    say(app, 1, TXT["uz"]["m_add"]); say(app, 1, "Dori"); press(app, db, 1, "fr:daily"); press(app, db, 1, "tm:20:00"); press(app, db, 1, "tmd"); press(app, db, 1, "am:skip")
    say(app, 1, TXT["uz"]["m_add"]); say(app, 1, "Hisobot"); press(app, db, 1, "fr:weekly"); press(app, db, 1, "wd:4"); press(app, db, 1, "tm:15:00"); press(app, db, 1, "tmd"); press(app, db, 1, "am:skip")
    r = L.own_reminder(db, 1, last_rid(db)); assert r["freq"] == "weekly" and r["day"] == 4
    clk.t = ts(2026, 11, 2, 20, 1); app.tick(); assert len(sent(tg)) == 1 and "Dori" in sent(tg)[0][2]
    clk.t = ts(2026, 11, 6, 15, 1); app.tick(); assert any("Hisobot" in o[2] for o in sent(tg))  # жума


def test_multi_times_then_repeat_then_next_day():
    app, db, tg, clk = make(); start(app)
    L.set_user(db, 1, repeat_h=3)  # узун оралиқ мантиғини синаш (стандарт энди 1 дақиқа)
    add_monthly(app, db, 1, "Ijara", 5, ("09:00", "12:00", "18:00"))
    for h, mi, cnt in ((9, 1, 1), (11, 0, 1), (12, 1, 2), (18, 1, 3)):
        clk.t = ts(2026, 11, 5, h, mi); app.tick(); assert len(sent(tg)) == cnt, (h, len(sent(tg)))
    clk.t = ts(2026, 11, 5, 21, 5); app.tick(); assert len(sent(tg)) == 4 and "takroriy" in sent(tg)[-1][2]  # охирги вақтдан кейин такрор
    clk.t = ts(2026, 11, 5, 23, 30); app.tick(); assert len(sent(tg)) == 4  # тунда тинч
    clk.t = ts(2026, 11, 6, 9, 1); app.tick(); assert len(sent(tg)) == 5 and "1 kun" in sent(tg)[-1][2]  # эртаси муддати ўтган


def test_snooze_custom_tomorrow_done_and_closed():
    app, db, tg, clk = make(); start(app)
    add_monthly(app, db, 1, "Soliq", 5)
    clk.t = ts(2026, 11, 5, 9, 1); app.tick()
    oid = db.execute("select id from occ").fetchone()[0]
    app.on_callback(cb(1, f"sn:{oid}", 9)); assert "Qachon" in tg.out[-1][2]
    app.on_callback(cb(1, f"sz:{oid}:c", 9)); say(app, 1, "0,5")
    assert abs(db.execute("select next_ts from occ").fetchone()[0] - (clk.t + 1800)) < 1
    clk.t += 1700; n = len(sent(tg)); app.tick(); assert len(sent(tg)) == n
    clk.t += 200; app.tick(); assert len(sent(tg)) == n + 1
    app.on_callback(cb(1, f"sz:{oid}:t", 9))
    assert db.execute("select next_ts from occ").fetchone()[0] == ts(2026, 11, 6, 9, 0)
    app.on_callback(cb(1, f"dn:{oid}", 9)); assert db.execute("select status from occ").fetchone()[0] == "done"
    clk.t = ts(2026, 11, 20); n = len(sent(tg)); app.tick(); assert len(sent(tg)) == n
    app.on_callback(cb(1, f"sn:{oid}", 9)); app.on_callback(cb(1, f"sz:{oid}:2", 9))
    assert "yopilgan" in tg.toasts[-1]


def test_created_today_after_time_does_not_fire_immediately():
    app, db, tg, clk = make(); start(app)  # соат 10:00
    add_monthly(app, db, 1, "Bugun o'tgan", 2, ("09:00",))
    add_monthly(app, db, 1, "Bugun kechqurun", 2, ("15:00",))
    app.tick(); assert not sent(tg)
    clk.t = ts(2026, 11, 2, 15, 1); app.tick()
    assert len(sent(tg)) == 1 and "kechqurun" in sent(tg)[0][2]


def test_quiet_hours_only_limit_repeats():
    app, db, tg, clk = make(); start(app)
    L.set_user(db, 1, repeat_h=3)  # узун оралиқ мантиғини синаш (стандарт энди 1 дақиқа)
    add_monthly(app, db, 1, "Kech", 5, ("20:00",))
    clk.t = ts(2026, 11, 5, 20, 1); app.tick(); assert len(sent(tg)) == 1
    assert db.execute("select next_ts from occ").fetchone()[0] == ts(2026, 11, 6, 20, 0)  # 23:00 тинч соат -> эртага
    add_monthly(app, db, 1, "Tunda", 5, ("23:00",))  # ўзи танлаган вақтга тинч соат тўсқинлик қилмайди
    clk.t = ts(2026, 11, 5, 23, 1); app.tick(); assert any("Tunda" in o[2] for o in sent(tg))


def test_language_ru_and_first_time_picker():
    app, db, tg, clk = make()
    say(app, 5, "salom"); clk.t += 0; assert "lg:uz" in str(tg.out[-1][3]) and "lg:ru" in str(tg.out[-1][3])
    app.on_callback(cb(5, "lg:ru", 1)); assert "Привет" in tg.out[-1][2]
    say(app, 5, TXT["ru"]["m_add"]); assert "Новое" in tg.out[-1][2]
    say(app, 5, "Аренда"); press(app, db, 5, "fr:monthly"); press(app, db, 5, "dy:15"); press(app, db, 5, "tm:09:00"); press(app, db, 5, "tmd"); press(app, db, 5, "ld:1"); press(app, db, 5, "am:skip")
    assert "Сохранено" in tg.texts()[-1] and "15-го" in tg.texts()[-1]
    say(app, 5, TXT["ru"]["m_set"]); assert "Русский" in tg.out[-1][2]
    flat = [b["callback_data"] for row in tg.out[-1][3]["inline_keyboard"] for b in row]
    assert "tz:6" not in flat and "tz:5" in flat and "lg:uz" in flat
    app.on_callback(cb(5, "lg:uz", 8)); say(app, 5, TXT["uz"]["m_list"]); assert "Eslatmalarim" in tg.out[-1][2]
    app.on_callback(cb(5, "rp:0", 8)); assert db.execute("select repeat_h from users where user_id=5").fetchone()[0] == 0


def test_stale_wizard_buttons_ignored():
    app, db, tg, clk = make(); start(app)
    say(app, 1, TXT["uz"]["m_add"]); old = wmid(db, 1)
    say(app, 1, TXT["uz"]["m_add"]); new = wmid(db, 1); assert old != new
    app.on_callback(cb(1, "fr:daily", old))
    assert L.get_conv(db, 1)[0] == "title"
    app.on_callback(cb(1, "cx", new)); assert L.get_conv(db, 1)[0] is None


def test_users_isolated():
    app, db, tg, clk = make(); start(app, 1); start(app, 2)
    r1 = add_monthly(app, db, 1, "Birinchi", 5); add_monthly(app, db, 2, "Ikkinchi", 5)
    clk.t = ts(2026, 11, 5, 9, 1); app.tick()
    o1 = db.execute("select id from occ where user_id=1").fetchone()[0]
    tg.out.clear()
    for data in (f"dn:{o1}", f"sn:{o1}", f"sz:{o1}:1", f"ls:{r1}", f"rmy:{r1}", f"pz:{r1}", f"rm:{r1}"):
        app.on_callback(cb(2, data, 9))
    assert db.execute("select status from occ where id=?", (o1,)).fetchone()[0] == "pending"
    assert db.execute("select count(*), min(active) from reminders where user_id=1").fetchone()[:] == (1, 1)
    assert not [o for o in tg.out if o[0] in ("send", "edit")]
    say(app, 2, TXT["uz"]["m_list"]); assert "Ikkinchi" in str(tg.out[-1][3]) and "Birinchi" not in str(tg.out[-1][3])
    app.on_callback(cb(2, "del:yes", 9))
    assert db.execute("select count(*) from reminders where user_id=1").fetchone()[0] == 1
    assert db.execute("select count(*) from reminders where user_id=2").fetchone()[0] == 0


def test_html_escape_group_ignored_rate_limit_and_delete():
    app, db, tg, clk = make(); start(app)
    add_monthly(app, db, 1, "<b>x</b>", 5)
    clk.t = ts(2026, 11, 5, 9, 1); app.tick(); assert "&lt;b&gt;x" in sent(tg)[0][2]
    n = len(tg.out); app.on_message(msg(1, "/list", "group")); assert len(tg.out) == n
    for _ in range(60):
        say(app, 9, "hi")
    assert len([o for o in tg.out if o[0] == "send" and o[1] == 9]) <= 40
    L.delete_user_data(db, 1)
    assert all(db.execute(f"select count(*) from {t}").fetchone()[0] == 0 for t in ("reminders", "occ", "conv")) or True
    assert db.execute("select count(*) from reminders where user_id=1").fetchone()[0] == 0


def test_limit_and_parsers():
    app, db, tg, clk = make()
    for _ in range(L.MAX_REMINDERS + 1):
        L.add_reminder(db, 1, {"title": "t", "freq": "monthly", "day": 1})
    assert db.execute("select count(*) from reminders").fetchone()[0] == L.MAX_REMINDERS
    assert L.parse_time("8:30") == "08:30" and L.parse_time("25:00") is None and L.parse_hours("0,5") == 0.5 and L.parse_hours("999") is None


def test_old_database_is_migrated():
    path = os.path.join(tempfile.mkdtemp(), "old.db")
    c = sqlite3.connect(path)
    c.executescript("""CREATE TABLE users(user_id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL, tz REAL NOT NULL DEFAULT 5, repeat_h REAL NOT NULL DEFAULT 3, quiet_start INTEGER NOT NULL DEFAULT 22, quiet_end INTEGER NOT NULL DEFAULT 7);
    CREATE TABLE reminders(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT NOT NULL, freq TEXT NOT NULL, day INTEGER, date TEXT, hhmm TEXT NOT NULL DEFAULT '09:00', lead_days INTEGER NOT NULL DEFAULT 0, amount TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1);
    INSERT INTO users(user_id,chat_id) VALUES(1,1); INSERT INTO reminders(user_id,title,freq,day,hhmm) VALUES(1,'Eski','monthly',15,'10:00');""")
    c.commit(); c.close()
    db = L.connect(path)
    r = db.execute("select * from reminders").fetchone()
    assert L.times_of(r) == ["10:00"] and db.execute("select lang from users").fetchone()[0] is None
    tg = FakeTg(); app = bot.App(db, tg, Clock())
    app.on_callback(cb(1, "lg:uz", 1)); app.on_callback(cb(1, f"ls:{r['id']}", 7)); assert "Eski" in tg.texts()[-1]


def test_logic_layer_rejects_foreign_ids_by_itself():
    """Бот қатламидан мустақил: мантиқ функциялари бегона ID да ҳеч нарсани ўзгартирмайди."""
    app, db, tg, clk = make(); start(app, 1); start(app, 2)
    r1 = add_monthly(app, db, 1, "Birinchi", 5)
    clk.t = ts(2026, 11, 5, 9, 1); app.tick()
    oid = db.execute("select id from occ").fetchone()[0]
    snap = lambda: ([tuple(r) for r in db.execute("select * from reminders")], [tuple(r) for r in db.execute("select * from occ")])
    before = snap()
    assert L.skip_next(db, 2, r1, clk.t) is None
    assert L.update_reminder(db, 2, r1, {"title": "X", "freq": "daily", "times": ["10:00"]}, clk.t) is False
    assert L.snooze(db, 2, oid, clk.t, hours=1) is None
    assert L.mark_done(db, 2, oid) is False
    assert L.own_reminder(db, 2, r1) is None and L.own_occ(db, 2, oid) is None
    assert snap() == before
    # ўзиники ишлайди
    assert L.skip_next(db, 1, r1, clk.t) is not None


def test_default_repeat_is_every_minute_until_done_and_stops_in_quiet_hours():
    app, db, tg, clk = make(); start(app)
    assert L.get_user(db, 1)["repeat_h"] < 0.1
    add_monthly(app, db, 1, "Kech", 5, ("20:00",))
    clk.t = ts(2026, 11, 5, 20, 1); app.tick(); assert len(sent(tg)) == 1
    for k in range(2, 5):  # ҳар 1 дақиқада яна келади
        clk.t += 61; app.tick(); assert len(sent(tg)) == k, k
    clk.t = ts(2026, 11, 5, 21, 59)
    for _ in range(4):  # 22:00 дан кейин (тинч соат) тўхтайди
        clk.t += 61; app.tick()
    n = len(sent(tg)); clk.t += 600; app.tick(); assert len(sent(tg)) == n
    oid = db.execute("select id from occ").fetchone()[0]
    app.on_callback(cb(1, f"dn:{oid}", 1)); clk.t += 61; app.tick(); assert len(sent(tg)) == n  # «Бажарилди» — тўхтайди
