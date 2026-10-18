"""Mini App (веб ойна) мантиғи: Telegram имзосини текшириш ва эслатмалар билан ишлаш.
Ботнинг ўзи ишлатадиган logic.py функциялари ишлатилади, шунинг учун бот ва веб ойна БИР БАЗАДАН ишлайди.
Ҳар амал фақат имзодан олинган фойдаланувчи (uid) маълумотига тегади."""
import hashlib, hmac, json, time
from datetime import date, timedelta
from urllib.parse import parse_qsl

import logic as L

MAX_AGE = 86400  # Telegram имзосининг умри (сония)
FREQS = ("once", "monthly", "weekly", "daily")
LEADS = (0, 1, 3, 7)
SNOOZE_MINUTES = (15, 30, 60, 180)
DIGEST_HOURS = (None, 7, 8, 9)
TZ_CHOICES = (3.0, 5.0)
REPEAT_CHOICES = (0.0, 0.016667, 1.0, 3.0, 6.0)
SOON_DAYS = 14


class ApiError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status


# ---------- Telegram имзоси ----------
def verify_init_data(init_data, bot_token, now=None, max_age=MAX_AGE):
    """Telegram Mini App initData имзосини текширади (hash). Фойдаланувчи ID'сини қайтаради ёки ApiError."""
    now = now or time.time()
    if not init_data or len(init_data) > 4096:
        raise ApiError("auth", 401)
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    got = pairs.pop("hash", "")
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    want = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not got or not hmac.compare_digest(got, want):
        raise ApiError("auth", 401)
    try:
        auth_date = int(pairs["auth_date"])
        uid = int(json.loads(pairs["user"])["id"])
    except (KeyError, ValueError, TypeError):
        raise ApiError("auth", 401)
    if auth_date > now + 60 or now - auth_date > max_age:
        raise ApiError("expired", 401)
    return uid


def sign_init_data(fields, bot_token):
    """Тест учун: Telegram каби имзоланган initData ясайди."""
    from urllib.parse import urlencode
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return urlencode({**fields, "hash": hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()})


# ---------- ҳолат ----------
def _rem(r):
    return {"id": r["id"], "title": r["title"], "amount": r["amount"] or "", "freq": r["freq"], "day": r["day"], "date": r["date"],
            "times": L.times_of(r), "lead": r["lead_days"], "active": bool(r["active"])}


def get_state(conn, uid, now):
    u = L.get_user(conn, uid)
    if not u or u["lang"] is None:
        raise ApiError("start_bot", 403)  # аввал ботда /start босиб, тил танлаш керак
    today = L.local_dt(u, now).date()
    rows = conn.execute("SELECT * FROM reminders WHERE user_id=? ORDER BY id", (uid,)).fetchall()
    rems = {r["id"]: r for r in rows}
    pending, taken = [], set()
    for o in conn.execute("SELECT o.id oid, o.reminder_id rid, o.due, o.next_ts, o.sent_count FROM occ o JOIN reminders r ON r.id=o.reminder_id "
                          "WHERE o.user_id=? AND o.status='pending' AND r.active=1 ORDER BY o.due, o.id", (uid,)).fetchall():
        r = rems[o["rid"]]
        due = date.fromisoformat(o["due"])
        taken.add((o["rid"], o["due"]))
        pending.append({"oid": o["oid"], "rid": o["rid"], "title": r["title"], "amount": r["amount"] or "", "due": o["due"],
                        "days": (due - today).days, "times": L.times_of(r), "fire_ts": o["next_ts"], "snoozed": o["next_ts"] > now and due <= today})
    soon = []
    for r in rows:
        if not r["active"]:
            continue
        for d in L.dues_near(r, today):
            if d < today or (d - today).days > SOON_DAYS or (r["id"], d.isoformat()) in taken:
                continue
            st = conn.execute("SELECT status FROM occ WHERE reminder_id=? AND due=?", (r["id"], d.isoformat())).fetchone()
            if st and st["status"] in ("done", "skipped"):
                continue
            soon.append({"rid": r["id"], "title": r["title"], "amount": r["amount"] or "", "due": d.isoformat(), "days": (d - today).days, "times": L.times_of(r)})
            break  # эслатма учун битта (энг яқин) муддат
    soon.sort(key=lambda x: (x["due"], x["title"]))
    return {"now": now, "today": today.isoformat(), "user": {"lang": u["lang"], "tz": u["tz"], "repeat_h": u["repeat_h"], "digest_hour": u["digest_hour"],
                                                              "quiet_start": u["quiet_start"], "quiet_end": u["quiet_end"]},
            "pending": pending, "soon": soon, "reminders": [_rem(r) for r in rows], "max": L.MAX_REMINDERS}


# ---------- амаллар ----------
def done(conn, uid, p):
    oid = _int(p.get("oid"))
    if not L.mark_done(conn, uid, oid):
        raise ApiError("not_found", 404)


def snooze(conn, uid, p, now):
    oid = _int(p.get("oid"))
    if p.get("tomorrow"):
        ts = L.snooze(conn, uid, oid, now, tomorrow=True)
    else:
        m = _int(p.get("minutes"))
        if m not in SNOOZE_MINUTES:
            raise ApiError("bad_value")
        ts = L.snooze(conn, uid, oid, now, hours=m / 60)
    if ts is None:
        raise ApiError("not_found", 404)


def parse_reminder(p, today):
    """Кирувчи маълумотни текширади ва logic.add_reminder учун lug'ат қайтаради."""
    title = L.clean(str(p.get("title") or ""), 80)
    if not title:
        raise ApiError("title")
    freq = p.get("freq")
    if freq not in FREQS:
        raise ApiError("freq")
    d = {"title": title, "freq": freq, "amount": L.clean(str(p.get("amount") or ""), 40), "day": None, "date": None}
    if freq == "monthly":
        d["day"] = _int(p.get("day"))
        if not 1 <= d["day"] <= 31:
            raise ApiError("day")
    elif freq == "weekly":
        d["day"] = _int(p.get("day"))
        if not 0 <= d["day"] <= 6:
            raise ApiError("weekday")
    elif freq == "once":
        try:
            dt = date.fromisoformat(str(p.get("date")))
        except ValueError:
            raise ApiError("date")
        if dt < today:
            raise ApiError("date_past")
        d["date"] = dt.isoformat()
    times = p.get("times")
    if not isinstance(times, list) or not 1 <= len(times) <= 12:
        raise ApiError("times")
    parsed = set()
    for t in times:
        v = L.parse_time(str(t))
        if v is None:
            raise ApiError("times")
        parsed.add(v)
    d["times"] = sorted(parsed)
    d["lead"] = _int(p.get("lead", 0))
    if d["lead"] not in LEADS:
        raise ApiError("lead")
    return d


def save_reminder(conn, uid, p, now):
    u = L.get_user(conn, uid)
    d = parse_reminder(p, L.local_dt(u, now).date())
    if p.get("id") is not None:
        rid = _int(p["id"])
        if not L.update_reminder(conn, uid, rid, d, now):
            raise ApiError("not_found", 404)
    else:
        if L.add_reminder(conn, uid, d, now) is None:
            raise ApiError("limit")
    L.sync(conn, now)


def delete_reminder(conn, uid, p):
    rid = _int(p.get("id"))
    if not L.own_reminder(conn, uid, rid):
        raise ApiError("not_found", 404)
    conn.execute("DELETE FROM occ WHERE reminder_id=? AND user_id=?", (rid, uid))
    conn.execute("DELETE FROM reminders WHERE id=? AND user_id=?", (rid, uid))
    conn.commit()


def toggle_pause(conn, uid, p):
    rid = _int(p.get("id"))
    r = L.own_reminder(conn, uid, rid)
    if not r:
        raise ApiError("not_found", 404)
    conn.execute("UPDATE reminders SET active=? WHERE id=? AND user_id=?", (0 if r["active"] else 1, rid, uid))
    conn.commit()


def skip(conn, uid, p, now):
    rid = _int(p.get("id"))
    if not L.own_reminder(conn, uid, rid):
        raise ApiError("not_found", 404)
    if L.skip_next(conn, uid, rid, now) is None:
        raise ApiError("nothing_to_skip")


def set_settings(conn, uid, p):
    try:
        return _set_settings(conn, uid, p)
    except (ValueError, TypeError):
        raise ApiError("bad_value")


def _set_settings(conn, uid, p):
    kw = {}
    if "lang" in p:
        if p["lang"] not in ("uz", "ru"):
            raise ApiError("bad_value")
        kw["lang"] = p["lang"]
    if "tz" in p:
        if float(p["tz"]) not in TZ_CHOICES:
            raise ApiError("bad_value")
        kw["tz"] = float(p["tz"])
    if "repeat_h" in p:
        if float(p["repeat_h"]) not in REPEAT_CHOICES:
            raise ApiError("bad_value")
        kw["repeat_h"] = float(p["repeat_h"])
    if "digest_hour" in p:
        h = p["digest_hour"]
        if h not in DIGEST_HOURS:
            raise ApiError("bad_value")
        kw.update(digest_hour=h, digest_date=None)
    if kw:
        L.set_user(conn, uid, **kw)


def send_feedback(conn, uid, p, now):
    if L.add_feedback(conn, uid, str(p.get("text") or ""), now) is None:
        raise ApiError("feedback_limit")


def _int(v):
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise ApiError("bad_value")
    try:
        f = float(v)
    except ValueError:
        raise ApiError("bad_value")
    if f != int(f):
        raise ApiError("bad_value")
    return int(f)


ACTIONS = {
    "done": lambda c, u, p, n: done(c, u, p),
    "snooze": snooze,
    "reminder": save_reminder,
    "delete": lambda c, u, p, n: delete_reminder(c, u, p),
    "pause": lambda c, u, p, n: toggle_pause(c, u, p),
    "skip": skip,
    "settings": lambda c, u, p, n: set_settings(c, u, p),
    "feedback": send_feedback,
}


def handle(conn, uid, action, payload, now):
    """Амални бажаради ва янги ҳолатни қайтаради. Хато бўлса ApiError."""
    if action != "state":
        if action not in ACTIONS:
            raise ApiError("unknown", 404)
        if not isinstance(payload, dict):
            raise ApiError("bad_value")
        get_state(conn, uid, now)  # фойдаланувчи ботда рўйхатдан ўтганини текшириш
        ACTIONS[action](conn, uid, payload, now)
    return get_state(conn, uid, now)
