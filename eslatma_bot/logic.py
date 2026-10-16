"""Мантиқ: база (SQLite), эслатма жадвали, қайта эслатиш алгоритми. Telegram'га боғлиқ эмас."""
import calendar, json, os, re, sqlite3
from datetime import date, datetime, timedelta, timezone

MAX_REMINDERS = 100
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL,
  tz REAL NOT NULL DEFAULT 5, repeat_h REAL NOT NULL DEFAULT 3, quiet_start INTEGER NOT NULL DEFAULT 22,
  quiet_end INTEGER NOT NULL DEFAULT 7);
CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
  title TEXT NOT NULL, freq TEXT NOT NULL, day INTEGER, date TEXT, hhmm TEXT NOT NULL DEFAULT '09:00',
  lead_days INTEGER NOT NULL DEFAULT 0, amount TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1);
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
    if new:
        os.chmod(path, 0o600)  # базани фақат эгаси ўқийди
    return conn


# ---------- вақт ----------

def local_dt(u, now):
    return datetime.fromtimestamp(now, timezone.utc).replace(tzinfo=None) + timedelta(hours=u["tz"])


def to_ts(u, naive_local):
    return (naive_local - timedelta(hours=u["tz"])).replace(tzinfo=timezone.utc).timestamp()


def in_quiet(hour, qs, qe):
    return (hour >= qs or hour < qe) if qs > qe else (qs <= hour < qe)


# ---------- фойдаланувчи ----------
def ensure_user(conn, uid, chat_id):
    conn.execute("INSERT INTO users(user_id, chat_id) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET chat_id=excluded.chat_id", (uid, chat_id))
    conn.commit()
    return get_user(conn, uid)


def get_user(conn, uid):
    return conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()


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


def parse_date(s, today):
    m = re.fullmatch(r"(\d{1,2})[./](\d{1,2})(?:[./](\d{4}))?", (s or "").strip())
    if not m:
        return None
    try:
        d = date(int(m[3]) if m[3] else today.year, int(m[2]), int(m[1]))
        if not m[3] and d < today:
            d = d.replace(year=d.year + 1)
    except ValueError:
        return None
    return d if d >= today else None


# ---------- эслатмалар ----------
def add_reminder(conn, uid, d):
    if conn.execute("SELECT COUNT(*) FROM reminders WHERE user_id=?", (uid,)).fetchone()[0] >= MAX_REMINDERS:
        return None
    cur = conn.execute(
        "INSERT INTO reminders(user_id,title,freq,day,date,hhmm,lead_days,amount) VALUES(?,?,?,?,?,?,?,?)",
        (uid, clean(d["title"], 80), d["freq"], d.get("day"), d.get("date"), d.get("hhmm", "09:00"), d.get("lead", 0), clean(d.get("amount", ""), 40)))
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


def sync(conn, now):
    """Муддати яқинлашган эслатмалар учун вазифа (occ) яратади."""
    for u in conn.execute("SELECT * FROM users"):
        today = local_dt(u, now).date()
        for r in conn.execute("SELECT * FROM reminders WHERE user_id=? AND active=1", (u["user_id"],)):
            for due in dues_near(r, today):
                start = due - timedelta(days=r["lead_days"])
                if not (start <= today <= due):
                    continue
                h, mi = map(int, r["hhmm"].split(":"))
                first = max(to_ts(u, datetime(start.year, start.month, start.day, h, mi)), now)
                conn.execute("INSERT OR IGNORE INTO occ(user_id,reminder_id,due,next_ts) VALUES(?,?,?,?)", (u["user_id"], r["id"], due.isoformat(), first))
    conn.execute("UPDATE occ SET status='missed' WHERE status='pending' AND due < ?", ((date.fromtimestamp(now) - timedelta(days=8)).isoformat(),))
    conn.commit()


def pop_due(conn, now):
    """Ҳозир юбориладиган хабарлар. Қайта эслатиш вақтини ЮБОРИШДАН ОЛДИН ёзади (иккилаб кетмасин)."""
    rows = conn.execute(
        "SELECT o.id oid, o.user_id, o.due, o.sent_count, r.title, r.amount, r.hhmm, u.chat_id, u.tz, u.repeat_h, u.quiet_start, u.quiet_end "
        "FROM occ o JOIN reminders r ON r.id=o.reminder_id JOIN users u ON u.user_id=o.user_id "
        "WHERE o.status='pending' AND o.next_ts<=? AND r.active=1", (now,)).fetchall()
    out = []
    for x in rows:
        loc = local_dt(x, now)
        if in_quiet(loc.hour, x["quiet_start"], x["quiet_end"]):
            wake = loc.replace(hour=x["quiet_end"], minute=0, second=0, microsecond=0)
            if wake <= loc:
                wake += timedelta(days=1)
            conn.execute("UPDATE occ SET next_ts=? WHERE id=?", (to_ts(x, wake), x["oid"]))
            continue
        conn.execute("UPDATE occ SET next_ts=?, sent_count=sent_count+1 WHERE id=?", (now + x["repeat_h"] * 3600, x["oid"]))
        out.append({**dict(x), "days_left": (date.fromisoformat(x["due"]) - loc.date()).days})
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
        r = conn.execute("SELECT hhmm FROM reminders WHERE id=?", (o["reminder_id"],)).fetchone()
        h, mi = map(int, r["hhmm"].split(":"))
        t = local_dt(u, now).replace(hour=h, minute=mi, second=0, microsecond=0) + timedelta(days=1)
        ts = to_ts(u, t)
    else:
        ts = now + hours * 3600
    conn.execute("UPDATE occ SET next_ts=? WHERE id=?", (ts, oid))
    conn.commit()
    return ts
