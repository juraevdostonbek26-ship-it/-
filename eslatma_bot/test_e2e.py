"""E2E: ҳақиқий HTTP орқали сохта Telegram'га уланган бот. Одамдек: тугмани матни бўйича босиб синайди."""
import os, random, tempfile
from datetime import datetime, timezone

os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
import bot, logic as L
from fake_telegram import FakeTelegram
from texts import TXT

UZ, RU = TXT["uz"], TXT["ru"]


def ts(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() - 5 * 3600


class World:
    def __init__(self, t=ts(2026, 11, 2, 10)):
        self.fake = FakeTelegram()
        self.db = L.connect(os.path.join(tempfile.mkdtemp(), "e2e.db"))
        self.t = t
        self.app = bot.App(self.db, bot.Tg("TOKEN", self.fake.url), lambda: self.t)
        self.offset = 0

    def run(self, tolerate=()):
        self.offset = bot.poll(self.app, self.db, self.offset, timeout=0)
        assert not self.app.errors, self.app.errors
        bad = [x for x in self.fake.errors if not any(t in x[1] for t in tolerate)]
        assert not bad, bad

    def say(self, uid, text):
        self.fake.say(uid, text); self.run()

    def menu(self, uid, label):
        self.fake.tap_menu(uid, label); self.run()

    def click(self, uid, label):
        self.fake.click(uid, label); self.run()

    def at(self, t):
        self.t = t; self.run()

    def bot_msgs(self, uid):
        return [x for x in self.fake.visible(uid) if x[1] == "bot" and not self.is_anchor(x)]

    @staticmethod
    def is_anchor(x):
        return x[2] in (UZ["anchor"], RU["anchor"])

    def last(self, uid):
        b = self.bot_msgs(uid)
        return b[-1][2] if b else ""

    def screen(self, uid):
        """Доимий меню хабаридан ташқари кўринадиган хабарлар."""
        return [x for x in self.fake.visible(uid) if not self.is_anchor(x)]

    def nav_ok(self, uid):
        """Охирги панелда уйга/орқага қайтиш йўли борми."""
        p = [x for x in self.bot_msgs(uid) if "🚨" not in x[2]]
        if not p:
            return True
        data = [d for mid, t, d in self.fake.buttons(uid) if mid == p[-1][0]]
        return any(d in ("home", "bk", "cx", "del:no") or d.startswith("go:") for d in data)

    def close(self):
        self.fake.close()


def onboard(w, uid=1, lang="🇺🇿 UZB"):
    w.say(uid, "/start"); w.click(uid, lang)


def test_human_journey_chat_stays_clean():
    w = World(); onboard(w)
    assert len(w.screen(1)) == 1 and "Salom" in w.last(1)  # фақат салом: меню босишлар ва тил танлаш ўчган
    w.menu(1, UZ["m_add"]); assert "Nimani eslatay" in w.last(1)
    w.say(1, "Ijara to'lovi"); w.click(1, UZ["t_month"]); w.click(1, "15")
    w.click(1, "09:00"); w.click(1, "18:00"); assert "09:00, 18:00" in w.last(1)
    w.click(1, "✅ Tayyor (2)"); w.click(1, UZ["l3"]); w.say(1, "5 000 000")
    assert "Saqlandi" in w.last(1) and "5 000 000" in w.last(1) and "12.11 09:00" in w.last(1)
    assert len(w.screen(1)) == 1, w.fake.visible(1)  # бутун ёзишма давомида чатда 1 та хабар
    w.menu(1, UZ["m_list"]); assert len(w.screen(1)) == 1 and "Ijara" in str(w.fake.buttons(1))
    w.click(1, "🔔 Ijara to'lovi"); assert "har oyning 15-kuni" in w.last(1)
    w.click(1, UZ["pause"]); assert "⏸" in w.last(1)
    w.click(1, UZ["resume"]); w.click(1, UZ["back"]); assert len(w.screen(1)) == 1
    w.menu(1, UZ["m_soon"]); assert "12.11" in w.last(1) and len(w.screen(1)) == 1
    w.menu(1, UZ["m_set"]); assert len(w.screen(1)) == 1 and "UTC+5" in w.last(1)
    assert "tz:6" not in str(w.fake.buttons(1))
    w.click(1, UZ["sound_btn"]); assert "Bildirishnomalar" in w.last(1) and len(w.screen(1)) == 1
    w.click(1, UZ["back_set"]); w.click(1, "🇷🇺 РУС")
    assert RU["m_add"] in (w.fake.chats[1]["kbd"] or []) and "Русский" in w.last(1)  # пастки меню тили ўзгарди
    assert len(w.screen(1)) == 1
    w.menu(1, RU["m_list"]); assert "Мои напоминания" in w.last(1)
    w.close()


def test_reminder_arrives_and_buttons_replace_messages():
    w = World(); onboard(w)
    w.menu(1, UZ["m_add"]); w.say(1, "Soliq"); w.click(1, UZ["t_month"]); w.click(1, "5"); w.click(1, "09:00"); w.click(1, UZ["time_done"] + " (1)")
    w.click(1, UZ["l0"]); w.click(1, UZ["skip"])
    w.at(ts(2026, 11, 5, 9, 1))
    cards = [x for x in w.bot_msgs(1) if "🚨" in x[2]]
    assert len(cards) == 1 and "Soliq" in cards[0][2] and "bugun" in cards[0][2]
    assert len(w.screen(1)) == 2  # панел + карточка
    w.click(1, UZ["b_later"]); assert "Qachon" in w.last(1)
    w.click(1, UZ["hours"].format(h=2)); assert not [x for x in w.bot_msgs(1) if "🚨" in x[2]] and "2 soatdan" in w.fake.toasts[-1]
    w.at(ts(2026, 11, 5, 10, 30)); assert not [x for x in w.bot_msgs(1) if "🚨" in x[2]]
    w.at(ts(2026, 11, 5, 11, 2)); cards = [x for x in w.bot_msgs(1) if "🚨" in x[2]]; assert len(cards) == 1 and "takroriy" in cards[0][2]
    w.click(1, UZ["b_later"]); w.click(1, UZ["custom"]); w.say(1, "0,5")
    assert not [x for x in w.bot_msgs(1) if "🚨" in x[2]] and "0.5 soatdan" in w.last(1)
    w.at(ts(2026, 11, 5, 11, 40)); assert [x for x in w.bot_msgs(1) if "🚨" in x[2]]
    w.click(1, UZ["b_done"]); assert not [x for x in w.bot_msgs(1) if "🚨" in x[2]] and "Bajarildi" in w.fake.toasts[-1]
    w.at(ts(2026, 11, 6, 9, 5)); assert not [x for x in w.bot_msgs(1) if "🚨" in x[2]]
    assert len(w.screen(1)) == 1
    w.close()


def test_once_via_calendar_and_ru_ui():
    w = World(); onboard(w, lang="🇷🇺 РУС")
    assert "Привет" in w.last(1)
    w.menu(1, RU["m_add"]); w.say(1, "Встреча"); w.click(1, RU["t_once"])
    assert "Ноябрь 2026" in str(w.fake.buttons(1)) and "·" in str(w.fake.buttons(1))
    w.click(1, "▶"); assert "Декабрь 2026" in str(w.fake.buttons(1)); w.click(1, "24")
    w.click(1, "10:00"); w.click(1, RU["time_other"]); w.say(1, "17:45"); assert "10:00, 17:45" in w.last(1)
    w.click(1, RU["time_done"] + " (2)"); w.click(1, RU["l1"]); w.click(1, RU["skip"])
    assert "Сохранено" in w.last(1) and "23.12 10:00" in w.last(1) and len(w.screen(1)) == 1
    w.at(ts(2026, 12, 23, 10, 1)); assert "Встреча" in w.bot_msgs(1)[-1][2] and "1 дн." in w.bot_msgs(1)[-1][2]
    w.close()


def test_weekly_daily_end_of_month():
    w = World(); onboard(w)
    w.menu(1, UZ["m_add"]); w.say(1, "Hisobot"); w.click(1, UZ["t_week"]); w.click(1, "Ju"); w.click(1, "15:00"); w.click(1, UZ["time_done"] + " (1)"); w.click(1, UZ["skip"])
    assert "har juma" in w.last(1)
    w.menu(1, UZ["m_add"]); w.say(1, "Dori"); w.click(1, UZ["t_day"]); w.click(1, "20:00"); w.click(1, UZ["time_done"] + " (1)"); w.click(1, UZ["skip"])
    w.menu(1, UZ["m_add"]); w.say(1, "Oylik"); w.click(1, UZ["t_month"]); w.click(1, UZ["month_end"]); w.click(1, "10:00"); w.click(1, UZ["time_done"] + " (1)"); w.click(1, UZ["l0"]); w.click(1, UZ["skip"])
    assert "oxirgi kuni" in w.last(1)
    w.at(ts(2027, 2, 28, 10, 1)); assert any("Oylik" in x[2] for x in w.bot_msgs(1))  # феврал: 28-си ой охири
    w.at(ts(2026, 11, 6, 15, 1)); assert any("Hisobot" in x[2] for x in w.bot_msgs(1))
    w.close()


def test_cancel_stale_and_garbage_input():
    w = World(); onboard(w)
    w.menu(1, UZ["m_add"]); w.say(1, "x"); w.click(1, UZ["cancel"]); assert "Asosiy menyu" in w.last(1) and "go:add" in str(w.fake.buttons(1))
    w.say(1, "ixtiyoriy matn"); assert "Qachon eslatay" in w.last(1) and len(w.screen(1)) == 1  # ёзилган матн — янги эслатма номи
    w.click(1, UZ["cancel"]); w.say(1, "/nomalum"); assert "menyudan" in w.last(1)
    w.menu(1, UZ["m_add"]); w.say(1, "<b>&\"'</b> " + "я" * 200); w.click(1, UZ["t_day"])
    old = w.fake.buttons(1)[0]
    w.menu(1, UZ["m_add"])  # янги оқим бошланади, эскиси тугмалари ўчган
    w.fake.press(1, old[0], old[2]); w.run(); assert "Nimani eslatay" in w.last(1)
    w.say(1, "A"); w.click(1, UZ["t_day"]); w.click(1, UZ["time_done"]); assert "Kamida" in w.last(1)
    w.close()


def test_two_users_never_see_each_other():
    w = World(); onboard(w, 1); onboard(w, 2)
    for uid, name in ((1, "SIR_BIR"), (2, "SIR_IKKI")):
        w.menu(uid, UZ["m_add"]); w.say(uid, name); w.click(uid, UZ["t_month"]); w.click(uid, "5"); w.click(uid, "09:00"); w.click(uid, UZ["time_done"] + " (1)"); w.click(uid, UZ["l0"]); w.click(uid, UZ["skip"])
    w.at(ts(2026, 11, 5, 9, 1))
    o1 = w.db.execute("select id from occ where user_id=1").fetchone()[0]
    r1 = w.db.execute("select id from reminders where user_id=1").fetchone()[0]
    mid2 = w.fake.buttons(2)[0][0]
    for data in (f"dn:{o1}", f"sn:{o1}", f"sz:{o1}:1", f"ls:{r1}", f"rm:{r1}", f"rmy:{r1}", f"pz:{r1}"):
        w.fake.press(2, mid2, data); w.run()
    assert w.db.execute("select status from occ where id=?", (o1,)).fetchone()[0] == "pending"
    assert w.db.execute("select count(*) from reminders where user_id=1").fetchone()[0] == 1
    for uid, other in ((1, "SIR_IKKI"), (2, "SIR_BIR")):
        assert other not in str(w.fake.visible(uid)) and other not in str(w.fake.buttons(uid))
    w.close()


def test_fuzz_no_errors_no_leaks_chat_stays_small():
    for seed in (1, 2, 3):
        rnd = random.Random(seed)
        w = World()
        users = (11, 12, 13)
        for u in users:
            onboard(w, u, rnd.choice(["🇺🇿 UZB", "🇷🇺 РУС"]))
        junk = ["", " ", "0", "31", "99", "-5", "8:30", "25:99", "<b>", "&amp;", "'; DROP TABLE users;--", "я" * 300, "💥", "05.11.2026", "0,5", "1e9", "\n\n", "/start", "/list", "/deleteme", "/cancel"]
        for step in range(900):
            u = rnd.choice(users)
            act = rnd.random()
            try:
                kbd = w.fake.chats[u]["kbd"] or []
                if act < 0.15 and kbd:
                    w.fake.tap_menu(u, rnd.choice(kbd))
                elif act < 0.55 and w.fake.buttons(u):
                    mid, text, data = rnd.choice(w.fake.buttons(u))
                    if "del:yes" == data and rnd.random() < 0.85:
                        continue
                    w.fake.press(u, mid, data)
                elif act < 0.8:
                    w.fake.say(u, rnd.choice(junk) if rnd.random() < 0.6 else f"SECRET_{u}_" + str(rnd.randint(1, 99)))
                elif act < 0.9:
                    w.t += rnd.choice([60, 900, 3600, 4 * 3600, 86400, 3 * 86400])
                elif act < 0.95 and w.fake.visible(u):
                    w.fake.press(u, rnd.choice(w.fake.visible(u))[0], rnd.choice(["em:1", "ed:1:when", "ed:2:title", "sk:1", "dg:9", "dg:x", "ed:99:amount", "ed:1:zzz", "sk:abc","dn:1", "sz:1:3", "ls:1", "rmy:2", "cd:2026-02-30", "cal:abc", "tm:99:99", "x", "", "lg:xx", "tz:99", "fr:zzz", "dy:99", "wd:-1"]))
                w.run()
            except AssertionError as e:
                raise AssertionError(f"seed={seed} step={step}: {e}")
            if step % 50 == 0:
                for v in users:
                    non_cards = [x for x in w.bot_msgs(v) if "🚨" not in x[2]]
                    assert len(non_cards) <= 2, (seed, step, v, [x[2][:40] for x in non_cards])
                    assert w.fake.chats[v]["kbd"], (seed, step, v, "пастки меню йўқолди")
                    assert w.nav_ok(v) or L.get_user(w.db, v) is None or L.get_user(w.db, v)["lang"] is None, (seed, step, v, w.last(v)[:60])
                    for other in users:
                        if other != v:
                            assert f"SECRET_{other}_" not in str(w.fake.visible(v)), (seed, step, v, other)
        w.close()


def test_typed_answers_are_accepted_too():
    w = World(); onboard(w)
    w.menu(1, UZ["m_add"]); w.say(1, "Yozib"); w.click(1, UZ["t_month"])
    w.say(1, "17"); assert "17-kuni" in w.last(1)          # санани ёзди
    w.say(1, "8:45"); w.say(1, "x9"); assert "⚠️" in w.last(1)   # вақтни ёзди / нотўғри
    w.say(1, "19:30"); assert "08:45, 19:30" in w.last(1)
    w.click(1, UZ["time_done"] + " (2)"); w.say(1, "3"); w.click(1, UZ["skip"])
    assert "3 kun oldin" in w.last(1) and len(w.screen(1)) == 1
    w.menu(1, UZ["m_add"]); w.say(1, "Sana"); w.click(1, UZ["t_once"]); w.say(1, "31.02.2027"); assert "Sanani tanlang" in w.last(1)
    w.say(1, "24.12")
    assert w.db.execute("select count(*) from reminders where title='Sana'").fetchone()[0] == 0  # ҳали сақланмаган (вақт сўралмоқда)
    w.click(1, "09:00"); w.click(1, UZ["time_done"] + " (1)"); w.click(1, UZ["l0"]); w.click(1, UZ["skip"])
    assert w.db.execute("select date from reminders where title='Sana'").fetchone()[0] == "2026-12-24"
    w.close()


def test_old_wizard_buttons_cannot_drive_new_wizard():
    w = World(); onboard(w)
    w.menu(1, UZ["m_add"]); w.say(1, "A"); old = w.fake.buttons(1)       # А оқими «қачон» босқичида
    w.menu(1, UZ["m_add"]); w.say(1, "B")                                 # Б оқими ҳам худди шу босқичда
    assert L.get_conv(w.db, 1)[0] == "freq"
    w.fake.press(1, old[0][0], "fr:daily"); w.run()                       # А нинг эски тугмаси
    assert "freq" not in L.get_conv(w.db, 1)[1] and L.get_conv(w.db, 1)[1]["title"] == "B"
    w.close()


def test_bottom_menu_never_disappears():
    """Расмдаги хато: хабарлар ўчирилганда пастки меню йўқолиб қолган."""
    w = World(); onboard(w)
    has = lambda: bool(w.fake.chats[1]["kbd"]) and UZ["m_add"] in w.fake.chats[1]["kbd"] or RU["m_add"] in (w.fake.chats[1]["kbd"] or [])
    assert has()
    steps = [lambda: w.menu(1, UZ["m_add"]), lambda: w.say(1, "A"), lambda: w.click(1, UZ["t_day"]), lambda: w.click(1, "09:00"),
             lambda: w.click(1, UZ["time_done"] + " (1)"), lambda: w.click(1, UZ["skip"]), lambda: w.menu(1, UZ["m_list"]),
             lambda: w.click(1, "🔔 A"), lambda: w.click(1, UZ["del"]), lambda: w.click(1, UZ["yes_del"]), lambda: w.menu(1, UZ["m_soon"]),
             lambda: w.menu(1, UZ["m_set"]), lambda: w.click(1, UZ["sound_btn"]), lambda: w.click(1, UZ["back_set"]), lambda: w.say(1, "/privacy"),
             lambda: w.say(1, "tasodifiy matn"), lambda: w.say(1, "/deleteme"), lambda: w.click(1, UZ["no"]), lambda: w.menu(1, UZ["m_set"]),
             lambda: w.click(1, "🇷🇺 РУС"), lambda: w.click(1, "🇺🇿 UZB"), lambda: w.say(1, "/start")]
    for i, st in enumerate(steps):
        st(); assert has(), f"{i}-қадамдан кейин пастки меню йўқолди"
    # Dostonbek'нинг ҳозирги ҳолати: меню йўқолган ва база эски (anchor йўқ) — бир хабардан кейин қайтиши керак
    w.fake.chats[1]["kbd"] = None
    w.db.execute("update users set anchor_mid=NULL"); w.db.commit()
    w.say(1, "salom"); assert has()
    w.close()


def test_every_screen_has_way_home_and_back_works():
    w = World(); onboard(w); w.menu(1, UZ["m_add"]); w.say(1, "Navigatsiya")
    # бутун оқим: ҳар қадамда уйга/орқага йўл бор
    for label in (UZ["t_month"], "15", "09:00", UZ["time_done"] + " (1)", UZ["l1"]):
        assert w.nav_ok(1), w.last(1)
        w.click(1, label)
    assert w.nav_ok(1) and "Summa" in w.last(1)  # сумма босқичи
    w.click(1, UZ["back_step"]); assert "Navigatsiya" in w.last(1) and "Oldindan" in w.last(1)   # lead қайта
    w.click(1, UZ["back_step"]); assert "Qaysi soatlarda" in w.last(1) and "09:00" in w.last(1)          # тanlangan соат сақланган
    w.click(1, UZ["back_step"]); assert "nechanchi kuni" in w.last(1)
    w.click(1, UZ["back_step"]); assert "Qachon eslatay" in w.last(1)
    w.click(1, UZ["back_step"]); assert "Nimani eslatay" in w.last(1)
    w.click(1, UZ["back_step"]); assert "Asosiy menyu" in w.last(1) and "go:add" in str(w.fake.buttons(1))
    assert L.get_conv(w.db, 1)[0] is None
    # қолган ҳамма экранлар
    w.click(1, UZ["m_add"]); w.say(1, "X"); w.click(1, UZ["t_day"]); w.click(1, "09:00"); w.click(1, UZ["time_done"] + " (1)"); w.click(1, UZ["skip"])
    for opener in (lambda: w.click(1, UZ["to_list"]), lambda: w.click(1, "🔔 X"), lambda: w.click(1, UZ["del"]), lambda: w.click(1, UZ["no"]),
                   lambda: w.click(1, UZ["btn_home"]), lambda: w.click(1, UZ["m_soon"]), lambda: w.click(1, UZ["btn_home"]), lambda: w.click(1, UZ["m_set"]),
                   lambda: w.click(1, UZ["sound_btn"]), lambda: w.click(1, UZ["back_set"]), lambda: w.click(1, UZ["btn_home"]), lambda: w.say(1, "/privacy"), lambda: w.say(1, "xyz")):
        opener(); assert w.nav_ok(1), w.last(1)
    assert len(w.screen(1)) == 1
    w.close()


def test_time_custom_back_and_cancel_to_home():
    w = World(); onboard(w); w.menu(1, UZ["m_add"]); w.say(1, "T"); w.click(1, UZ["t_day"]); w.click(1, UZ["time_other"])
    assert "8:30" in w.last(1); w.click(1, UZ["back_step"]); assert "Qaysi soatlarda" in w.last(1)
    w.click(1, UZ["cancel"]); assert "Asosiy menyu" in w.last(1) and L.get_conv(w.db, 1)[0] is None
    w.close()


def make_one(w, uid=1, title="Ijara", day=5, times=("09:00",), lead="0"):
    w.menu(uid, UZ["m_add"]); w.say(uid, title); w.click(uid, UZ["t_month"]); w.click(uid, str(day))
    for t in times:
        w.click(uid, t)
    w.click(uid, UZ["time_done"] + f" ({len(times)})"); w.click(uid, {"0": UZ["l0"], "1": UZ["l1"], "3": UZ["l3"]}[lead]); w.click(uid, UZ["skip"])
    return w.db.execute("select max(id) from reminders where user_id=?", (uid,)).fetchone()[0]


def test_edit_every_field():
    w = World(); onboard(w); rid = make_one(w)
    get = lambda: dict(w.db.execute("select * from reminders where id=?", (rid,)).fetchone())
    open_edit = lambda: (w.click(1, UZ["m_list"]) if False else None)
    w.menu(1, UZ["m_list"]); w.click(1, "🔔 Ijara"); w.click(1, UZ["b_edit"]); assert "Nimani o'zgartiramiz" in w.last(1) and "Ijara" in w.last(1)
    w.click(1, UZ["e_title"]); assert "Yangi nomini" in w.last(1); w.say(1, "Ofis ijarasi")
    assert "Yangilandi" in w.last(1) and get()["title"] == "Ofis ijarasi" and len(w.screen(1)) == 1
    w.click(1, UZ["b_edit"]); w.click(1, UZ["e_times"]); assert "09:00" in w.last(1) and "✅ 09:00" in str(w.fake.buttons(1))     # эски қийматлар олдиндан белгиланган
    w.click(1, "✅ 09:00"); w.click(1, "14:00"); w.click(1, "16:00"); w.click(1, UZ["time_done"] + " (2)")
    assert get()["times"] == "14:00,16:00"
    w.click(1, UZ["b_edit"]); w.click(1, UZ["e_lead"]); w.click(1, UZ["l7"]); assert get()["lead_days"] == 7
    w.click(1, UZ["b_edit"]); w.click(1, UZ["e_amount"]); w.say(1, "3 000 000"); assert get()["amount"] == "3 000 000"
    w.click(1, UZ["b_edit"]); w.click(1, UZ["e_when"]); w.click(1, UZ["t_week"]); w.click(1, "Ju")
    r = get(); assert (r["freq"], r["day"], r["lead_days"], r["times"], r["title"]) == ("weekly", 4, 7, "14:00,16:00", "Ofis ijarasi")
    assert "har juma" in w.last(1) and len(w.screen(1)) == 1
    w.click(1, UZ["b_edit"]); w.click(1, UZ["e_when"]); w.click(1, UZ["back_step"]); assert "Nimani o'zgartiramiz" in w.last(1)   # таҳрирда «Орқага» — таҳрир менюсига
    w.click(1, UZ["e_title"]); w.click(1, UZ["cancel"]); assert "har juma" in w.last(1)                                         # «Бекор» — эслатма экрани
    w.close()


def test_edit_schedule_regenerates_but_title_edit_keeps_nagging():
    w = World(); onboard(w); rid = make_one(w, day=5, times=("09:00",))
    w.at(ts(2026, 11, 5, 9, 1)); assert len([x for x in w.bot_msgs(1) if "🚨" in x[2]]) == 1
    # ном ўзгартирилса — кутилаётган эслатма тегилмайди (бир хил ID, янги карточка юборилмайди)
    occ_before = w.db.execute("select id, sent_count from occ").fetchone()[:]
    w.menu(1, UZ["m_list"]); w.click(1, "🔔 Ijara"); w.click(1, UZ["b_edit"]); w.click(1, UZ["e_title"]); w.say(1, "Yangi nom")
    assert w.db.execute("select count(*) from occ where status='pending'").fetchone()[0] == 1
    assert w.db.execute("select id, sent_count from occ").fetchone()[:] == occ_before
    assert len([x for x in w.bot_msgs(1) if "🚨" in x[2]]) == 1
    w.at(ts(2026, 11, 5, 12, 5)); assert any("Yangi nom" in x[2] and "takroriy" in x[2] for x in w.bot_msgs(1))     # такрор давом этди ва янги ном билан
    # жадвал ўзгартирилса — қайта ҳисобланади (кутилаётган ўчади)
    w.click(1, UZ["b_edit"]) if False else None
    w.menu(1, UZ["m_list"]); w.click(1, "🔔 Yangi nom"); w.click(1, UZ["b_edit"]); w.click(1, UZ["e_times"]); w.click(1, "✅ 09:00"); w.click(1, "20:00"); w.click(1, UZ["time_done"] + " (1)")
    assert w.db.execute("select count(*) from occ where status='pending'").fetchone()[0] == 1
    assert w.db.execute("select next_ts from occ").fetchone()[0] == ts(2026, 11, 5, 20, 0)
    w.close()


def test_edit_and_skip_foreign_reminders_are_rejected():
    w = World(); onboard(w, 1); onboard(w, 2); rid = make_one(w, 1, "SIR_BIR"); make_one(w, 2, "SIR_IKKI")
    mid2 = w.fake.buttons(2)[0][0] if w.fake.buttons(2) else w.bot_msgs(2)[-1][0]
    before = dict(w.db.execute("select * from reminders where id=?", (rid,)).fetchone())
    for data in (f"em:{rid}", f"ed:{rid}:title", f"ed:{rid}:when", f"sk:{rid}", f"pz:{rid}", f"rm:{rid}"):
        w.fake.press(2, mid2, data); w.run()
    assert L.get_conv(w.db, 2)[0] is None or "SIR_BIR" not in str(L.get_conv(w.db, 2)[1])
    assert dict(w.db.execute("select * from reminders where id=?", (rid,)).fetchone()) == before
    assert w.db.execute("select count(*) from occ where reminder_id=? and status='skipped'", (rid,)).fetchone()[0] == 0
    assert "SIR_BIR" not in str(w.fake.visible(2))
    w.close()


def test_skip_next_occurrence_monthly_and_daily():
    w = World(); onboard(w); rid = make_one(w, day=5)
    w.menu(1, UZ["m_list"]); w.click(1, "🔔 Ijara"); w.click(1, UZ["b_skip"]); assert "05.11" in w.fake.toasts[-1]
    w.at(ts(2026, 11, 5, 9, 1)); assert not [x for x in w.bot_msgs(1) if "🚨" in x[2]]       # ноябрь ўтказилди
    w.at(ts(2026, 12, 5, 9, 1)); assert len([x for x in w.bot_msgs(1) if "🚨" in x[2]]) == 1  # декабрь ишлайди
    w.click(1, UZ["b_done"])
    w.menu(1, UZ["m_list"]); w.click(1, "🔔 Ijara"); w.click(1, UZ["b_skip"]); assert "05.01" in w.fake.toasts[-1]   # ёки кейинги
    w.close()


def test_daily_digest_once_a_day_replaced_and_empty_skipped():
    w = World(); onboard(w); make_one(w, day=2, times=("12:00",)); make_one(w, title="Soliq", day=4, times=("09:00",))
    w.at(ts(2026, 11, 2, 12, 5))
    dg = lambda: [x for x in w.bot_msgs(1) if "Bugungi xulosa" in x[2]]
    w.menu(1, UZ["m_set"]); w.click(1, "🗞 08:00"); assert "08:00" in w.last(1) or dg()
    assert len(dg()) == 1 and "Bugun" in dg()[0][2] and "Ijara" in dg()[0][2] and "Yaqin 3 kun" in dg()[0][2] and "Soliq" in dg()[0][2]   # yoqilganda namuna darrov
    d0 = dg()[0][0]
    w.at(ts(2026, 11, 2, 15, 0)); assert len(dg()) == 1 and dg()[0][0] == d0                  # кунига 1 марта
    w.at(ts(2026, 11, 3, 7, 0)); assert dg()[0][0] == d0
    w.at(ts(2026, 11, 3, 8, 5)); assert len(dg()) == 1 and dg()[0][0] != d0 and "Muddati o'tgan" in dg()[0][2]   # эскиси ўрнига янгиси
    w.menu(1, UZ["m_set"]); w.click(1, "🗞 O'chiq"); assert "o'chiq" in w.last(1)
    w.close()


def test_unanswered_repeats_keep_exactly_one_card():
    w = World(); onboard(w); make_one(w, day=5, times=("09:00",))
    cards = lambda: [x for x in w.bot_msgs(1) if "🚨" in x[2]]
    for h, mi in ((9, 1), (12, 5), (15, 10), (18, 20), (21, 30)):
        w.at(ts(2026, 11, 5, h, mi)); assert len(cards()) == 1, (h, len(cards()))
    assert "takroriy" in cards()[0][2]
    w.at(ts(2026, 11, 6, 9, 5)); assert len(cards()) == 1 and "1 kun" in cards()[0][2]       # эртасига ҳам битта
    w.close()


def test_draft_expires_after_30_minutes_and_dead_buttons_go_home():
    w = World(); onboard(w); w.menu(1, UZ["m_add"]); w.say(1, "Eskiradi")
    w.at(w.t + 31 * 60)
    w.click(1, UZ["t_month"])                                   # эскирган қоралама тугмаси
    assert "Asosiy menyu" in w.last(1) and L.get_conv(w.db, 1)[0] is None
    w.say(1, "15"); assert "Qachon eslatay" in w.last(1)           # «15» янги эслатма номи бўлиб қолади, эски қоралама эмас
    w.close()


def test_snooze_presets_15_and_30_minutes():
    w = World(); onboard(w); make_one(w, day=5)
    w.at(ts(2026, 11, 5, 9, 1)); w.click(1, UZ["b_later"])
    assert [b[1] for b in w.fake.buttons(1) if b[2].startswith("sz:")][:3] == ["15 daq", "30 daq", "1 soat"]
    w.click(1, "15 daq"); assert "15 daqiqadan" in w.fake.toasts[-1]
    oid = w.db.execute("select id from occ").fetchone()[0]
    assert abs(w.db.execute("select next_ts from occ").fetchone()[0] - (ts(2026, 11, 5, 9, 1) + 900)) < 1
    w.at(ts(2026, 11, 5, 9, 17)); assert [x for x in w.bot_msgs(1) if "🚨" in x[2]]
    w.close()


def test_user_deletes_wizard_message_manually_wizard_recovers():
    w = World(); onboard(w); w.menu(1, UZ["m_add"]); mid = L.get_conv(w.db, 1)[1]["mid"]
    w.fake.chats[1]["msgs"][mid]["deleted"] = True                # одам хабарни ўзи ўчирди
    w.fake.say(1, "Tiklanadi"); w.run(tolerate=("not found",)); assert "Qachon eslatay" in w.last(1)
    w.close()


def test_feedback_reaches_admin_anonymously_with_daily_limit():
    w = World()
    w.app.admin_chat = 999
    w.say(7, "/start"); w.click(7, "🇺🇿 UZB")
    w.menu(7, UZ["m_fb"])
    assert "Asoschiga" in w.last(7)
    w.say(7, "Menyu juda kichik <b>xato</b>")
    assert w.last(7) == UZ["fb_ok"]
    got = [x for x in w.fake.visible(999) if x[1] == "bot"]
    assert got and "Menyu juda kichik" in got[-1][2] and "7" not in got[-1][2].replace("#1", "")
    for i in range(6):
        w.menu(7, UZ["m_fb"]); w.say(7, f"yana {i}")
    assert w.last(7) == UZ["fb_limit"]
    assert len(L.unsent_feedback(w.db)) == 0
    assert w.db.execute("select count(*) from feedback").fetchone()[0] == L.FEEDBACK_PER_DAY


def test_feedback_without_admin_is_kept_and_sent_later():
    w = World()
    w.say(7, "/start"); w.click(7, "🇺🇿 UZB")
    w.menu(7, UZ["m_fb"]); w.say(7, "salom")
    assert len(L.unsent_feedback(w.db)) == 1
    w.app.admin_chat = 999
    w.at(w.t + 60)
    assert len(L.unsent_feedback(w.db)) == 0


def test_quiet_hours_presets_and_off_from_bot_settings():
    w = World()
    w.say(7, "/start"); w.click(7, "🇺🇿 UZB")
    w.menu(7, UZ["m_set"])
    assert "22:00–07:00" in w.last(7)
    for label, want in (("🌙 23–08", (23, 8)), ("🌙 21–06", (21, 6)), ("🌙 22–07", (22, 7))):
        w.click(7, label)
        u = L.get_user(w.db, 7)
        assert (u["quiet_start"], u["quiet_end"]) == want, (label, dict(u))
    w.click(7, UZ["q_btn_off"])
    u = L.get_user(w.db, 7)
    assert u["quiet_start"] == u["quiet_end"] and "o'chiq" in w.last(7)
    assert not L.in_quiet(3, u["quiet_start"], u["quiet_end"])
    assert (L.get_user(w.db, 7)["quiet_start"], L.ensure_user(w.db, 8, 8)["quiet_start"]) == (0, 22)  # бошқа фойдаланувчига тегмайди


def test_sound_and_background_buttons_send_files_and_instructions():
    w = World()
    old = (bot.ASSET_BASE, bot.BG_LINK)
    try:
        bot.ASSET_BASE, bot.BG_LINK = "https://doju.example.com", ""
        w.say(7, "/start"); w.click(7, "🇺🇿 UZB")
        w.click(7, UZ["sound_btn"])
        assert ("sendAudio", "https://doju.example.com/assets/doju_ovoz.mp3", UZ["snd_caption"]) in w.fake.media
        assert "Bildirishnomalar uchun saqlash" in "".join(x[2] for x in w.fake.visible(7))
        n = len(w.fake.media)
        w.click(7, UZ["back_set"])
        w.click(7, UZ["bg_btn"])
        assert ("sendPhoto", "https://doju.example.com/assets/doju_fon.png", "") in w.fake.media[n:]
        assert "galereya" in "".join(x[2] for x in w.fake.visible(7))
        # ҳавола берилса — битта босишда қўлланадиган тугма
        bot.BG_LINK = "https://t.me/bg/ABCDEF"
        w.click(7, UZ["back_set"])
        w.click(7, UZ["bg_btn"])
        mk = [m for m in w.fake.chats[7]["msgs"].values() if m["markup"] and any("url" in b for r in m["markup"]["inline_keyboard"] for b in r)]
        assert mk and mk[-1]["markup"]["inline_keyboard"][0][0]["url"] == "https://t.me/bg/ABCDEF"
        # асос URL йўқ (маҳаллий) — хатосиз, фақат матн
        bot.ASSET_BASE = ""
        w.click(7, UZ["back_set"])
        w.click(7, UZ["sound_btn"]); assert not w.app.errors
    finally:
        bot.ASSET_BASE, bot.BG_LINK = old
