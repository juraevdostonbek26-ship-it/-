"""Мантиқ: база (SQLite), эслатма жадвали, қайта эслатиш алгоритми. Telegram'га боғлиқ эмас."""
import calendar, json, os, re, sqlite3, time
from datetime import date, datetime, timedelta, timezone

MAX_REMINDERS = 100
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL,
  tz REAL NOT NULL DEFAULT 5, repeat_h REAL NOT NULL DEFAULT 3, quiet_start INTEGER NOT NULL DEFAULT 22,
  quiet_end INTEGER NOT NULL DEFAULT 7, lang TEXT, panel_mid INTEGER);
CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
  title TEXT NOT NULL, freq TEXT NOT NULL, day INTEGER, date TEXT, hhmm TEXT NOT NULL DEFAULT '09:00',
  lead_days INTEGER NOT NULL DEFAULT 0, amount TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1,
  times TEXT, created_ts REAL NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_rem_user ON reminders(user_id);
CREATE TABLE IF NOT EXISTS occ(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
  reminder_id INTEGER NOT NULL, due TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
  next_ts REAL NOT NULL, sent_count INTEGER NOT NULL DEFAULT 0, UNIQUE(reminder_id, due));
CREATE TABLE IF NOT EXISTS conv(user_id INTEGER PRIMARY KEY, step TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
"""
USER_TABLES = ("occ", "reminders", "conv", "users")


def connect(path):
    new = not os.path.exists(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    cols = lambda t: {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
    for t, c, ddl in (("users", "lang", "TEXT"), ("users", "panel_mid", "INTEGER"), ("reminders", "times", "TEXT"), ("reminders", "created_ts", "REAL NOT NULL DEFAULT 0")):
        if c not in cols(t):  # эски базани йўқотмасдан янгилаш
            conn.execute(f"ALTER TABLE {t} ADD COLUMN {c} {ddl}")
    conn.commit()
    if new:
        os.chmod(path, 0o600)  # базани фақат эгаси ўқийди
    return conn


# ---------- вақт ----------
def local_dt(u, now):
    return datetime.fromtimestamp(now, timezone.utc).replace(tzinfo=None) + timedelta(hours=u["tz"])


def to_ts(u, naive_local):
    return (naive_local - timedelta(hours=u["tz"])).replace(tzinfo=timezone.utc).timestamp()


def at(u, d, hhmm):
    h, m = map(int, hhmm.split(":"))
    return to_ts(u, datetime(d.year, d.month, d.day, h, m))


def in_quiet(hour, qs, qe):
    return (hour >= qs or hour < qe) if qs > qe else (qs <= hour < qe)


# ---------- фойдаланувчи ----------
def ensure_user(conn, uid, chat_id):
    conn.execute("INSERT INTO users(user_id, chat_id) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET chat_id=excluded.chat_id", (uid, chat_id))
    conn.commit()
    return get_user(conn, uid)


def get_user(conn, uid):
    return conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()


def set_user(conn, uid, **kw):
    for k in kw:
        assert k in ("lang", "tz", "repeat_h", "panel_mid")
    conn.execute("UPDATE users SET " + ",".join(f"{k}=?" for k in kw) + " WHERE user_id=?", (*kw.values(), uid))
    conn.commit()


def delete_user_data(conn, uid):
    for t in USER_TABLES:
        conn.execute(f"DELETE FROM {t} WHERE user_id=?", (uid,))
    conn.commit()


# ---------- суҳбат ҳолати ----------
def get_conv(conn, uid):
    r = conn.execute("SELECT step, data FROM conv WHERE user_id=?", (uid,)).fetchone()
    return (r["step"], json.loads(r["data"])) if r else (None, {})


def set_conv(conn, uid, step, data):
    conn.execute("INSERT OR REPLACE INTO conv(user_id, step, data) VALUES(?,?,?)", (uid, step, json.dumps(data, ensure_ascii=False)))
    conn.commit()


def clear_conv(conn, uid):
    conn.execute("DELETE FROM conv WHERE user_id=?", (uid,))
    conn.commit()


# ---------- парсерлар ----------
def clean(s, n):
    return re.sub(r"\s+", " ", (s or "").replace("\x00", "")).strip()[:n]


def parse_int(s, lo, hi):
    s = (s or "").strip()
    return int(s) if s.isdigit() and lo <= int(s) <= hi else None


def parse_hours(s):
    try:
        h = float((s or "").strip().replace(",", "."))
    except ValueError:
        return None
    return h if 0.1 <= h <= 72 else None


def parse_time(s):
    m = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?", (s or "").strip())
    if not m:
        return None
    h, mi = int(m[1]), int(m[2] or 0)
    return f"{h:02d}:{mi:02d}" if h < 24 and mi < 60 else None


# ---------- эслатмалар ----------
def times_of(r):
    return sorted({t for t in (r["times"] or r["hhmm"] or "09:00").split(",") if t})


def add_reminder(conn, uid, d, now=None):
    if conn.execute("SELECT COUNT(*) FROM reminders WHERE user_id=?", (uid,)).fetchone()[0] >= MAX_REMINDERS:
        return None
    times = sorted(set(d.get("times") or ["09:00"]))
    cur = conn.execute(
        "INSERT INTO reminders(user_id,title,freq,day,date,hhmm,lead_days,amount,times,created_ts) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (uid, clean(d["title"], 80), d["freq"], d.get("day"), d.get("date"), times[0], d.get("lead", 0), clean(d.get("amount", ""), 40), ",".join(times), now or time.time()))
    conn.commit()
    return cur.lastrowid


def own_reminder(conn, uid, rid):
    return conn.execute("SELECT * FROM reminders WHERE id=? AND user_id=?", (rid, uid)).fetchone()


def own_occ(conn, uid, oid):
    return conn.execute("SELECT * FROM occ WHERE id=? AND user_id=?", (oid, uid)).fetchone()


def dues_near(r, today):
    f = r["freq"]
    if f == "once":
        return [date.fromisoformat(r["date"])]
    if f == "daily":
        return [today, today + timedelta(days=1)]
    if f == "weekly":
        return [today + timedelta(d) for d in range(8) if (today + timedelta(d)).weekday() == r["day"]]
    out, y, m = [], today.year, today.month
    for _ in range(2):
        out.append(date(y, m, min(r["day"], calendar.monthrange(y, m)[1])))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def next_due(r, today):
    c = [d for d in dues_near(r, today) if d >= today]
    return min(c) if c else None


def first_fire(u, r, due, now, created):
    """Муддат (due) учун биринчи эслатма вақти (ts). Яратилгандан олдинги вақтлар ўтказиб юборилади."""
    times = times_of(r)
    today = local_dt(u, now).date()
    cdate = local_dt(u, created).date() if created > 0 else date.min
    d = max(due - timedelta(days=r["lead_days"]), cdate)
    while d <= due:
        for t in times:
            ts = at(u, d, t)
            if ts >= created:
                return ts
        d += timedelta(days=1)
    return None


def next_fire(conn, uid, r, now):
    """Шу эслатманинг энг яқин келажакдаги вақти (кўрсатиш учун)."""
    u = get_user(conn, uid)
    best = None
    for due in dues_near(r, local_dt(u, now).date()):
        ts = first_fire(u, r, due, now, now)
        if ts is not None and (best is None or ts < best):
            best = ts
    return best


def sync(conn, now):
    """Муддати яқинлашган эслатмалар учун вазифа (occ) яратади."""
    for u in conn.execute("SELECT * FROM users").fetchall():
        today = local_dt(u, now).date()
        for r in conn.execute("SELECT * FROM reminders WHERE user_id=? AND active=1", (u["user_id"],)).fetchall():
            if r["freq"] == "daily":
                conn.execute("UPDATE occ SET status='missed' WHERE reminder_id=? AND due<? AND status='pending'", (r["id"], today.isoformat()))
            for due in dues_near(r, today):
                if not (due - timedelta(days=r["lead_days"]) <= today <= due):
                    continue
                if conn.execute("SELECT 1 FROM occ WHERE reminder_id=? AND due=?", (r["id"], due.isoformat())).fetchone():
                    continue
                ts = first_fire(u, r, due, now, r["created_ts"])
                conn.execute("INSERT OR IGNORE INTO occ(user_id,reminder_id,due,status,next_ts) VALUES(?,?,?,?,?)",
                             (u["user_id"], r["id"], due.isoformat(), "pending" if ts is not None else "missed", ts if ts is not None else now))
    cutoff = (datetime.fromtimestamp(now, timezone.utc).date() - timedelta(days=8)).isoformat()
    conn.execute("UPDATE occ SET status='missed' WHERE status='pending' AND due < ?", (cutoff,))
    conn.commit()


def next_after_send(x, times, now):
    """Юборгандан кейин навбатдаги эслатма: бугунги қолган вақтлар, сўнг такрор, сўнг эртанги биринчи вақт."""
    loc = local_dt(x, now)
    later = [ts for ts in (at(x, loc.date(), t) for t in times) if ts > now + 60]
    if later:
        return min(later)
    if x["repeat_h"] > 0:
        nag = now + x["repeat_h"] * 3600
        nl = local_dt(x, nag)
        if nl.date() == loc.date() and not in_quiet(nl.hour, x["quiet_start"], x["quiet_end"]):
            return nag
    return at(x, loc.date() + timedelta(days=1), times[0])


def pop_due(conn, now):
    """Ҳозир юбориладиган хабарлар. Навбатдаги вақтни ЮБОРИШДАН ОЛДИН ёзади (иккилаб кетмасин)."""
    rows = conn.execute(
        "SELECT o.id oid, o.user_id, o.due, o.sent_count, r.title, r.amount, r.hhmm, r.times, r.freq, u.chat_id, u.tz, u.repeat_h, u.quiet_start, u.quiet_end, u.lang "
        "FROM occ o JOIN reminders r ON r.id=o.reminder_id JOIN users u ON u.user_id=o.user_id "
        "WHERE o.status='pending' AND o.next_ts<=? AND r.active=1", (now,)).fetchall()
    out = []
    for x in rows:
        conn.execute("UPDATE occ SET next_ts=?, sent_count=sent_count+1 WHERE id=?", (next_after_send(x, times_of(x), now), x["oid"]))
        out.append({**dict(x), "days_left": (date.fromisoformat(x["due"]) - local_dt(x, now).date()).days})
    conn.commit()
    return out


def mark_done(conn, uid, oid):
    cur = conn.execute("UPDATE occ SET status='done' WHERE id=? AND user_id=?", (oid, uid))
    conn.commit()
    return cur.rowcount == 1


def snooze(conn, uid, oid, now, hours=None, tomorrow=False):
    o = own_occ(conn, uid, oid)
    if not o or o["status"] != "pending":
        return None
    u = get_user(conn, uid)
    if tomorrow:
        r = conn.execute("SELECT * FROM reminders WHERE id=?", (o["reminder_id"],)).fetchone()
        ts = at(u, local_dt(u, now).date() + timedelta(days=1), times_of(r)[0])
    else:
        ts = now + hours * 3600
    conn.execute("UPDATE occ SET next_ts=? WHERE id=?", (ts, oid))
    conn.commit()
    return ts
