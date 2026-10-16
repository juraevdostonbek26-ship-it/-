import os, tempfile
from datetime import datetime, timezone
import bot, logic as L


class FakeTg:
    def __init__(self):
        self.out = []
    def send(self, chat, text, markup=None):
        self.out.append(("send", chat, text, markup))
    def edit(self, chat, mid, text, markup=None):
        self.out.append(("edit", chat, text, markup))
    def call(self, m, **p):
        self.out.append((m, p))


def ts(y, mo, d, h=0, mi=0, tz=5):  # маҳаллий вақт -> UTC ts
    return datetime(y, mo, d, h - tz, mi, tzinfo=timezone.utc).timestamp() if h >= tz else datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() - tz * 3600


class Clock:
    t = ts(2026, 11, 2, 10)
    def __call__(self):
        return self.t


def make():
    db = L.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    clk, tg = Clock(), FakeTg()
    return bot.App(db, tg, clk), db, tg, clk


def msg(uid, text):
    return {"chat": {"id": uid, "type": "private"}, "from": {"id": uid}, "text": text}


def cb(uid, data):
    return {"id": "x", "from": {"id": uid}, "data": data, "message": {"chat": {"id": uid, "type": "private"}, "message_id": 7}}


def add(app, uid, title="Аренда", day="5", lead="ld:1"):
    app.on_message(msg(uid, "/add"))
    app.on_message(msg(uid, title))
    app.on_callback(cb(uid, "fr:monthly"))
    app.on_message(msg(uid, day))
    app.on_callback(cb(uid, "tm:09:00"))
    app.on_callback(cb(uid, lead))
    app.on_message(msg(uid, "5 000 000"))


def test_full_flow_and_reminder_cycle():
    app, db, tg, clk = make()
    add(app, 1)
    r = db.execute("select * from reminders").fetchone()
    assert (r["title"], r["day"], r["lead_days"], r["amount"]) == ("Аренда", 5, 1, "5 000 000")
    # 2-ноябр: муддат 5-ноябр, 1 кун олдин = 4-ноябр -> ҳали вазифа йўқ
    app.tick(); assert db.execute("select count(*) from occ").fetchone()[0] == 0
    clk.t = ts(2026, 11, 4, 9, 1)
    tg.out.clear(); app.tick()
    sent = [o for o in tg.out if o[0] == "send"]
    assert len(sent) == 1 and "1 кун" in sent[0][2] and "Кейинрок" in str(sent[0][3])
    # жавоб йўқ: 3 соатдан кейин такрор
    clk.t += 2 * 3600; tg.out.clear(); app.tick(); assert not tg.out
    clk.t += 1.1 * 3600; app.tick(); assert any("такрорий" in o[2] for o in tg.out if o[0] == "send")


def test_snooze_custom_and_done():
    app, db, tg, clk = make()
    add(app, 1, lead="ld:0"); clk.t = ts(2026, 11, 5, 9, 1); app.tick()
    oid = db.execute("select id from occ").fetchone()[0]
    app.on_callback(cb(1, f"sn:{oid}")); assert "Қачон" in tg.out[-1][2]
    app.on_callback(cb(1, f"sz:{oid}:c")); app.on_message(msg(1, "0,5"))
    assert abs(db.execute("select next_ts from occ").fetchone()[0] - (clk.t + 1800)) < 1
    tg.out.clear(); clk.t += 1700; app.tick(); assert not [o for o in tg.out if o[0] == "send"]
    clk.t += 200; app.tick(); assert [o for o in tg.out if o[0] == "send"]
    app.on_callback(cb(1, f"dn:{oid}"))
    assert db.execute("select status from occ").fetchone()[0] == "done"
    tg.out.clear(); clk.t += 10 * 3600; app.tick(); assert not [o for o in tg.out if o[0] == "send"]


def test_users_isolated():
    app, db, tg, clk = make()
    add(app, 1); add(app, 2, title="Менинг махфий")
    clk.t = ts(2026, 11, 4, 9, 1); app.tick()
    o1 = db.execute("select id from occ where user_id=1").fetchone()[0]
    r1 = db.execute("select id from reminders where user_id=1").fetchone()[0]
    tg.out.clear()
    # 2-фойдаланувчи 1-никининг вазифа/эслатмасига тегишга ҳаракат қилади
    for data in (f"dn:{o1}", f"sz:{o1}:1", f"ls:{r1}", f"rmy:{r1}", f"pz:{r1}"):
        app.on_callback(cb(2, data))
    assert db.execute("select status from occ where id=?", (o1,)).fetchone()[0] == "pending"
    assert db.execute("select count(*) from reminders where user_id=1").fetchone()[0] == 1
    assert db.execute("select active from reminders where id=?", (r1,)).fetchone()[0] == 1
    assert not [o for o in tg.out if o[0] in ("send", "edit")]
    # рўйхатда фақат ўзиникини кўради
    app.on_message(msg(2, "📋 Эслатмаларим")); assert "Аренда" not in str(tg.out[-1][3]) and "Менинг" in str(tg.out[-1][3])
    app.on_message(msg(1, "📋 Эслатмаларим")); assert "Аренда" in str(tg.out[-1][3]) and "Менинг" not in str(tg.out[-1][3])
    # ўчириш фақат ўзиникини
    app.on_callback(cb(2, "del:yes"))
    assert db.execute("select count(*) from reminders where user_id=1").fetchone()[0] == 1
    assert db.execute("select count(*) from reminders where user_id=2").fetchone()[0] == 0


def test_quiet_hours_and_group_ignored_and_html_escape():
    app, db, tg, clk = make()
    add(app, 1, title="<b>x</b>", lead="ld:0")
    clk.t = ts(2026, 11, 5, 23, 0); app.tick()
    assert not [o for o in tg.out if o[0] == "send" and "Сақланди" not in o[2] and "Нимани" not in o[2] and "Кейинрок" in str(o[3])]
    assert db.execute("select next_ts from occ").fetchone()[0] > clk.t
    clk.t = ts(2026, 11, 6, 7, 1); tg.out.clear(); app.tick()
    s = [o for o in tg.out if o[0] == "send"]
    assert s and "&lt;b&gt;x" in s[0][2]
    n = len(tg.out); app.on_message({"chat": {"id": -5, "type": "group"}, "from": {"id": 1}, "text": "/list"}); assert len(tg.out) == n


def test_parsers_and_limits():
    t = datetime(2026, 11, 2).date()
    assert L.parse_date("05.11.2026", t).isoformat() == "2026-11-05" and L.parse_date("01.11.2026", t) is None
    assert L.parse_time("8:30") == "08:30" and L.parse_time("25:00") is None
    assert L.parse_hours("0,5") == 0.5 and L.parse_hours("999") is None and L.parse_hours("abc") is None
    app, db, tg, clk = make()
    for i in range(L.MAX_REMINDERS + 1):
        L.add_reminder(db, 1, {"title": "t", "freq": "monthly", "day": 1})
    assert db.execute("select count(*) from reminders").fetchone()[0] == L.MAX_REMINDERS


def test_delete_all_and_rate_limit():
    app, db, tg, clk = make()
    add(app, 1); L.delete_user_data(db, 1)
    for t in ("users", "reminders", "occ", "conv"):
        assert db.execute(f"select count(*) from {t}").fetchone()[0] == 0
    n = len(tg.out)
    for _ in range(40):
        app.on_message(msg(9, "hi"))
    assert len(tg.out) - n <= 21
