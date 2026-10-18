"""Mini App мантиғи: имзо, хавфсизлик (бошқа одам маълумоти), текширув, бот билан бир база."""
import json, os, tempfile, time
from datetime import datetime, timezone
import logic as L, webapi as W

TOKEN = "123456:TEST-TOKEN"


def ts(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() - 5 * 3600


NOW = ts(2026, 11, 2, 10)


def fresh():
    db = L.connect(os.path.join(tempfile.mkdtemp(), "w.db"))
    for uid in (1, 2):
        L.ensure_user(db, uid, uid); L.set_user(db, uid, lang="uz")
    return db


def init_data(uid, auth_date=None, token=TOKEN, extra=None):
    f = {"auth_date": str(int(auth_date or time.time())), "query_id": "AAH", "user": json.dumps({"id": uid, "first_name": "X"})}
    f.update(extra or {})
    return W.sign_init_data(f, token)


def raises(code, fn, *a, **k):
    try:
        fn(*a, **k)
    except W.ApiError as e:
        assert e.code == code, (e.code, code)
        return
    raise AssertionError(f"ApiError({code}) чиқмади")


def test_init_data_signature_checks():
    now = time.time()
    assert W.verify_init_data(init_data(7), TOKEN, now) == 7
    raises("auth", W.verify_init_data, init_data(7, token="999:OTHER"), TOKEN, now)  # бошқа токен билан имзоланган
    forged = init_data(7).replace("%22id%22%3A+7", "%22id%22%3A+8")  # ID алмаштирилди
    assert forged != init_data(7)
    raises("auth", W.verify_init_data, forged, TOKEN, now)
    raises("auth", W.verify_init_data, "", TOKEN, now)
    raises("auth", W.verify_init_data, "hash=abc&user=%7B%7D", TOKEN, now)
    raises("auth", W.verify_init_data, init_data(7).replace("hash=", "hash=0"), TOKEN, now)
    raises("expired", W.verify_init_data, init_data(7, auth_date=now - 2 * 86400), TOKEN, now)
    raises("expired", W.verify_init_data, init_data(7, auth_date=now + 3600), TOKEN, now)
    raises("auth", W.verify_init_data, init_data(7, extra={"user": "not json"}), TOKEN, now)
    raises("auth", W.verify_init_data, "x" * 5000, TOKEN, now)


def test_unregistered_user_must_start_bot_first():
    db = fresh()
    raises("start_bot", W.handle, db, 99, "state", {}, NOW)
    raises("start_bot", W.handle, db, 99, "reminder", {"title": "x"}, NOW)
    L.ensure_user(db, 98, 98)  # /start босган, лекин тил танламаган
    raises("start_bot", W.handle, db, 98, "state", {}, NOW)


def test_create_edit_delete_pause_skip_and_bot_sees_same_data():
    db = fresh()
    st = W.handle(db, 1, "reminder", {"title": "  Ijara   to'lovi ", "freq": "monthly", "day": 31, "times": ["9:00", "18:00", "09:00"], "lead": 1, "amount": "5000000"}, NOW)
    r = st["reminders"][0]
    assert r["title"] == "Ijara to'lovi" and r["day"] == 31 and r["times"] == ["09:00", "18:00"] and r["lead"] == 1 and r["amount"] == "5000000"
    # бот шу эслатмани ўзининг функциялари билан кўради
    br = L.own_reminder(db, 1, r["id"])
    assert br["title"] == "Ijara to'lovi" and L.times_of(br) == ["09:00", "18:00"]
    # ботда қўшилган эслатма веб'да кўринади
    L.add_reminder(db, 1, {"title": "Botdan", "freq": "daily", "times": ["08:00"]}, NOW)
    assert {x["title"] for x in W.handle(db, 1, "state", {}, NOW)["reminders"]} == {"Ijara to'lovi", "Botdan"}
    # таҳрирлаш
    st = W.handle(db, 1, "reminder", {"id": r["id"], "title": "Yangi nom", "freq": "weekly", "day": 2, "times": ["12:00"], "lead": 0}, NOW)
    r2 = [x for x in st["reminders"] if x["id"] == r["id"]][0]
    assert (r2["title"], r2["freq"], r2["day"], r2["times"]) == ("Yangi nom", "weekly", 2, ["12:00"])
    # пауза
    assert [x for x in W.handle(db, 1, "pause", {"id": r["id"]}, NOW)["reminders"] if x["id"] == r["id"]][0]["active"] is False
    assert [x for x in W.handle(db, 1, "pause", {"id": r["id"]}, NOW)["reminders"] if x["id"] == r["id"]][0]["active"] is True
    # ўтказиб юбориш
    W.handle(db, 1, "skip", {"id": r["id"]}, NOW)
    # ўчириш
    st = W.handle(db, 1, "delete", {"id": r["id"]}, NOW)
    assert all(x["id"] != r["id"] for x in st["reminders"])
    assert db.execute("select count(*) from occ where reminder_id=?", (r["id"],)).fetchone()[0] == 0


def test_validation_rejects_bad_input():
    db = fresh()
    good = {"title": "A", "freq": "daily", "times": ["09:00"]}
    for bad, code in (({**good, "title": "   "}, "title"), ({**good, "freq": "yearly"}, "freq"), ({**good, "times": []}, "times"), ({**good, "times": ["25:00"]}, "times"),
                      ({**good, "times": "09:00"}, "times"), ({**good, "times": ["09:00"] * 13}, "times"),
                      ({**good, "freq": "monthly", "day": 0}, "day"), ({**good, "freq": "monthly", "day": 32}, "day"), ({**good, "freq": "monthly"}, "bad_value"),
                      ({**good, "freq": "weekly", "day": 7}, "weekday"), ({**good, "freq": "once", "date": "2020-01-01"}, "date_past"),
                      ({**good, "freq": "once", "date": "not-a-date"}, "date"), ({**good, "lead": 2}, "lead"), ({**good, "lead": "x"}, "bad_value")):
        raises(code, W.handle, db, 1, "reminder", bad, NOW)
    assert db.execute("select count(*) from reminders").fetchone()[0] == 0
    long = W.handle(db, 1, "reminder", {**good, "title": "x" * 500, "amount": "9" * 500}, NOW)["reminders"][0]
    assert len(long["title"]) == 80 and len(long["amount"]) == 40
    raises("unknown", W.handle, db, 1, "drop_tables", {}, NOW)
    raises("bad_value", W.handle, db, 1, "reminder", ["x"], NOW)
    # лимит
    for i in range(L.MAX_REMINDERS - 1):
        L.add_reminder(db, 1, good, NOW)
    raises("limit", W.handle, db, 1, "reminder", good, NOW)


def test_users_cannot_touch_each_others_data():
    db = fresh()
    W.handle(db, 1, "reminder", {"title": "Maxfiy", "freq": "daily", "times": ["11:00"]}, NOW)
    rid = db.execute("select id from reminders").fetchone()[0]
    L.sync(db, ts(2026, 11, 2, 10, 30))
    oid = db.execute("select id from occ").fetchone()[0]
    assert W.handle(db, 2, "state", {}, NOW)["reminders"] == []
    for action, p in (("delete", {"id": rid}), ("pause", {"id": rid}), ("skip", {"id": rid}), ("reminder", {"id": rid, "title": "Hack", "freq": "daily", "times": ["09:00"]}),
                      ("done", {"oid": oid}), ("snooze", {"oid": oid, "minutes": 15})):
        raises("not_found", W.handle, db, 2, action, p, NOW)
    assert db.execute("select title, active from reminders where id=?", (rid,)).fetchone()[:] == ("Maxfiy", 1)
    assert db.execute("select status from occ where id=?", (oid,)).fetchone()[0] == "pending"


def test_done_snooze_and_state_buckets():
    db = fresh()
    W.handle(db, 1, "reminder", {"title": "Bugun", "freq": "monthly", "day": 2, "times": ["09:00"]}, ts(2026, 11, 1, 10))  # шу ойнинг 2-куни
    W.handle(db, 1, "reminder", {"title": "Yaqin", "freq": "monthly", "day": 10, "times": ["09:00"]}, NOW)
    L.sync(db, ts(2026, 11, 2, 9, 30))
    st = W.handle(db, 1, "state", {}, ts(2026, 11, 2, 9, 30))
    assert [p["title"] for p in st["pending"]] == ["Bugun"] and st["pending"][0]["days"] == 0
    assert [s["title"] for s in st["soon"]] == ["Yaqin"] and st["soon"][0]["days"] == 8
    oid = st["pending"][0]["oid"]
    raises("bad_value", W.handle, db, 1, "snooze", {"oid": oid, "minutes": 7}, NOW)
    st = W.handle(db, 1, "snooze", {"oid": oid, "minutes": 60}, ts(2026, 11, 2, 9, 30))
    assert st["pending"][0]["snoozed"] is True and abs(st["pending"][0]["fire_ts"] - (ts(2026, 11, 2, 9, 30) + 3600)) < 1
    st = W.handle(db, 1, "snooze", {"oid": oid, "tomorrow": True}, ts(2026, 11, 2, 9, 30))
    assert st["pending"][0]["fire_ts"] > ts(2026, 11, 3, 0)
    st = W.handle(db, 1, "done", {"oid": oid}, ts(2026, 11, 2, 9, 40))
    assert st["pending"] == [] and all(s["title"] != "Bugun" or s["days"] > 0 for s in st["soon"])
    raises("not_found", W.handle, db, 1, "done", {"oid": oid + 999}, NOW)


def test_web_created_reminder_fires_in_bot_loop():
    db = fresh()
    W.handle(db, 1, "reminder", {"title": "Vebdan", "freq": "once", "date": "2026-11-02", "times": ["10:30"]}, NOW)
    L.sync(db, ts(2026, 11, 2, 10, 31))
    due = L.pop_due(db, ts(2026, 11, 2, 10, 31))
    assert [x["title"] for x in due] == ["Vebdan"]


def test_settings_and_feedback():
    db = fresh()
    st = W.handle(db, 1, "settings", {"lang": "ru", "tz": 3, "repeat_h": 3, "digest_hour": 8}, NOW)
    assert st["user"]["lang"] == "ru" and st["user"]["tz"] == 3 and st["user"]["repeat_h"] == 3 and st["user"]["digest_hour"] == 8
    assert st["user"]["quiet_start"] == 22  # тинч соатлар ўзгармайди
    for bad in ({"lang": "en"}, {"tz": 9}, {"tz": "x"}, {"repeat_h": 2}, {"digest_hour": 12}, {"tz": None}):
        raises("bad_value", W.handle, db, 1, "settings", bad, NOW)
    assert L.get_user(db, 2)["lang"] == "uz"  # бошқа фойдаланувчига тегмайди
    st = W.handle(db, 1, "settings", {"digest_hour": None}, NOW)
    assert st["user"]["digest_hour"] is None
    W.handle(db, 1, "feedback", {"text": "Salom"}, NOW)
    assert len(L.unsent_feedback(db)) == 1
    raises("feedback_limit", W.handle, db, 1, "feedback", {"text": "   "}, NOW)
    for i in range(L.FEEDBACK_PER_DAY):
        try:
            W.handle(db, 1, "feedback", {"text": f"x{i}"}, NOW)
        except W.ApiError:
            pass
    raises("feedback_limit", W.handle, db, 1, "feedback", {"text": "ortiqcha"}, NOW)
