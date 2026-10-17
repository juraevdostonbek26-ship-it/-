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

    def run(self):
        self.offset = bot.poll(self.app, self.db, self.offset, timeout=0)
        assert not self.app.errors, self.app.errors
        assert not self.fake.errors, self.fake.errors

    def say(self, uid, text):
        self.fake.say(uid, text); self.run()

    def menu(self, uid, label):
        self.fake.tap_menu(uid, label); self.run()

    def click(self, uid, label):
        self.fake.click(uid, label); self.run()

    def at(self, t):
        self.t = t; self.run()

    def bot_msgs(self, uid):
        return [x for x in self.fake.visible(uid) if x[1] == "bot"]

    def close(self):
        self.fake.close()


def onboard(w, uid=1, lang="🇺🇿 UZB"):
    w.say(uid, "/start"); w.click(uid, lang)


def test_human_journey_chat_stays_clean():
    w = World(); onboard(w)
    assert len(w.fake.visible(1)) == 1 and "Salom" in w.fake.last(1)  # фақат салом: меню босишлар ва тил танлаш ўчган
    w.menu(1, UZ["m_add"]); assert "Nimani eslatay" in w.fake.last(1)
    w.say(1, "Ijara to'lovi"); w.click(1, UZ["t_month"]); w.click(1, "15")
    w.click(1, "09:00"); w.click(1, "18:00"); assert "09:00, 18:00" in w.fake.last(1)
    w.click(1, "✅ Tayyor (2)"); w.click(1, UZ["l3"]); w.say(1, "5 000 000")
    assert "Saqlandi" in w.fake.last(1) and "5 000 000" in w.fake.last(1) and "12.11 09:00" in w.fake.last(1)
    assert len(w.fake.visible(1)) == 1, w.fake.visible(1)  # бутун ёзишма давомида чатда 1 та хабар
    w.menu(1, UZ["m_list"]); assert len(w.fake.visible(1)) == 1 and "Ijara" in str(w.fake.buttons(1))
    w.click(1, "🔔 Ijara to'lovi"); assert "har oyning 15-kuni" in w.fake.last(1)
    w.click(1, UZ["pause"]); assert "⏸" in w.fake.last(1)
    w.click(1, UZ["resume"]); w.click(1, UZ["back"]); assert len(w.fake.visible(1)) == 1
    w.menu(1, UZ["m_soon"]); assert "12.11" in w.fake.last(1) and len(w.fake.visible(1)) == 1
    w.menu(1, UZ["m_set"]); assert len(w.fake.visible(1)) == 1 and "UTC+5" in w.fake.last(1)
    assert "tz:6" not in str(w.fake.buttons(1))
    w.click(1, UZ["sound_btn"]); assert "Bildirishnomalar" in w.fake.last(1) and len(w.fake.visible(1)) == 1
    w.click(1, UZ["back_set"]); w.click(1, "🇷🇺 РУС")
    assert RU["m_add"] in (w.fake.chats[1]["kbd"] or []) and "Русский" in w.fake.last(1)  # пастки меню тили ўзгарди
    assert len(w.fake.visible(1)) == 1
    w.menu(1, RU["m_list"]); assert "Мои напоминания" in w.fake.last(1)
    w.close()


def test_reminder_arrives_and_buttons_replace_messages():
    w = World(); onboard(w)
    w.menu(1, UZ["m_add"]); w.say(1, "Soliq"); w.click(1, UZ["t_month"]); w.click(1, "5"); w.click(1, "09:00"); w.click(1, UZ["time_done"] + " (1)")
    w.click(1, UZ["l0"]); w.click(1, UZ["skip"])
    w.at(ts(2026, 11, 5, 9, 1))
    cards = [x for x in w.bot_msgs(1) if "🚨" in x[2]]
    assert len(cards) == 1 and "Soliq" in cards[0][2] and "bugun" in cards[0][2]
    assert len(w.fake.visible(1)) == 2  # панел + карточка
    w.click(1, UZ["b_later"]); assert "Qachon" in w.fake.last(1)
    w.click(1, UZ["hours"].format(h=2)); assert not [x for x in w.bot_msgs(1) if "🚨" in x[2]] and "2 soatdan" in w.fake.toasts[-1]
    w.at(ts(2026, 11, 5, 10, 30)); assert not [x for x in w.bot_msgs(1) if "🚨" in x[2]]
    w.at(ts(2026, 11, 5, 11, 2)); cards = [x for x in w.bot_msgs(1) if "🚨" in x[2]]; assert len(cards) == 1 and "takroriy" in cards[0][2]
    w.click(1, UZ["b_later"]); w.click(1, UZ["custom"]); w.say(1, "0,5")
    assert not [x for x in w.bot_msgs(1) if "🚨" in x[2]] and "0.5 soatdan" in w.fake.last(1)
    w.at(ts(2026, 11, 5, 11, 40)); assert [x for x in w.bot_msgs(1) if "🚨" in x[2]]
    w.click(1, UZ["b_done"]); assert not [x for x in w.bot_msgs(1) if "🚨" in x[2]] and "Bajarildi" in w.fake.toasts[-1]
    w.at(ts(2026, 11, 6, 9, 5)); assert not [x for x in w.bot_msgs(1) if "🚨" in x[2]]
    assert len(w.fake.visible(1)) == 1
    w.close()


def test_once_via_calendar_and_ru_ui():
    w = World(); onboard(w, lang="🇷🇺 РУС")
    assert "Привет" in w.fake.last(1)
    w.menu(1, RU["m_add"]); w.say(1, "Встреча"); w.click(1, RU["t_once"])
    assert "Ноябрь 2026" in str(w.fake.buttons(1)) and "·" in str(w.fake.buttons(1))
    w.click(1, "▶"); assert "Декабрь 2026" in str(w.fake.buttons(1)); w.click(1, "24")
    w.click(1, "10:00"); w.click(1, RU["time_other"]); w.say(1, "17:45"); assert "10:00, 17:45" in w.fake.last(1)
    w.click(1, RU["time_done"] + " (2)"); w.click(1, RU["l1"]); w.click(1, RU["skip"])
    assert "Сохранено" in w.fake.last(1) and "23.12 10:00" in w.fake.last(1) and len(w.fake.visible(1)) == 1
    w.at(ts(2026, 12, 23, 10, 1)); assert "Встреча" in w.bot_msgs(1)[-1][2] and "1 дн." in w.bot_msgs(1)[-1][2]
    w.close()


def test_weekly_daily_end_of_month():
    w = World(); onboard(w)
    w.menu(1, UZ["m_add"]); w.say(1, "Hisobot"); w.click(1, UZ["t_week"]); w.click(1, "Ju"); w.click(1, "15:00"); w.click(1, UZ["time_done"] + " (1)"); w.click(1, UZ["skip"])
    assert "har juma" in w.fake.last(1)
    w.menu(1, UZ["m_add"]); w.say(1, "Dori"); w.click(1, UZ["t_day"]); w.click(1, "20:00"); w.click(1, UZ["time_done"] + " (1)"); w.click(1, UZ["skip"])
    w.menu(1, UZ["m_add"]); w.say(1, "Oylik"); w.click(1, UZ["t_month"]); w.click(1, UZ["month_end"]); w.click(1, "10:00"); w.click(1, UZ["time_done"] + " (1)"); w.click(1, UZ["l0"]); w.click(1, UZ["skip"])
    assert "oxirgi kuni" in w.fake.last(1)
    w.at(ts(2027, 2, 28, 10, 1)); assert any("Oylik" in x[2] for x in w.bot_msgs(1))  # феврал: 28-си ой охири
    w.at(ts(2026, 11, 6, 15, 1)); assert any("Hisobot" in x[2] for x in w.bot_msgs(1))
    w.close()


def test_cancel_stale_and_garbage_input():
    w = World(); onboard(w)
    w.menu(1, UZ["m_add"]); w.say(1, "x"); w.click(1, UZ["cancel"]); assert "Bekor" in w.fake.last(1)
    w.say(1, "ixtiyoriy matn"); assert "menyudan" in w.fake.last(1) and len(w.fake.visible(1)) == 1
    w.menu(1, UZ["m_add"]); w.say(1, "<b>&\"'</b> " + "я" * 200); w.click(1, UZ["t_day"])
    old = w.fake.buttons(1)[0]
    w.menu(1, UZ["m_add"])  # янги оқим бошланади, эскиси тугмалари ўчган
    w.fake.press(1, old[0], old[2]); w.run(); assert "Nimani eslatay" in w.fake.last(1)
    w.say(1, "A"); w.click(1, UZ["t_day"]); w.click(1, UZ["time_done"]); assert "Kamida" in w.fake.last(1)
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
                elif act < 0.95 and w.fake.chats[u]["msgs"]:
                    w.fake.press(u, rnd.choice(list(w.fake.chats[u]["msgs"])), rnd.choice(["dn:1", "sz:1:3", "ls:1", "rmy:2", "cd:2026-02-30", "cal:abc", "tm:99:99", "x", "", "lg:xx", "tz:99", "fr:zzz", "dy:99", "wd:-1"]))
                w.run()
            except AssertionError as e:
                raise AssertionError(f"seed={seed} step={step}: {e}")
            if step % 50 == 0:
                for v in users:
                    non_cards = [x for x in w.bot_msgs(v) if "🚨" not in x[2]]
                    assert len(non_cards) <= 2, (seed, step, v, [x[2][:40] for x in non_cards])
                    for other in users:
                        if other != v:
                            assert f"SECRET_{other}_" not in str(w.fake.visible(v)), (seed, step, v, other)
        w.close()


def test_typed_answers_are_accepted_too():
    w = World(); onboard(w)
    w.menu(1, UZ["m_add"]); w.say(1, "Yozib"); w.click(1, UZ["t_month"])
    w.say(1, "17"); assert "17-kuni" in w.fake.last(1)          # санани ёзди
    w.say(1, "8:45"); w.say(1, "x9"); assert "⚠️" in w.fake.last(1)   # вақтни ёзди / нотўғри
    w.say(1, "19:30"); assert "08:45, 19:30" in w.fake.last(1)
    w.click(1, UZ["time_done"] + " (2)"); w.say(1, "3"); w.click(1, UZ["skip"])
    assert "3 kun oldin" in w.fake.last(1) and len(w.fake.visible(1)) == 1
    w.menu(1, UZ["m_add"]); w.say(1, "Sana"); w.click(1, UZ["t_once"]); w.say(1, "31.02.2027"); assert "Sanani tanlang" in w.fake.last(1)
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
