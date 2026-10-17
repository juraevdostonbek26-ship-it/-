"""Telegram бот: кўп фойдаланувчили эслатма котиби (UZ/RU). Фақат стандарт кутубхона."""
import calendar, html, json, os, sys, time, traceback, urllib.error, urllib.request
from collections import defaultdict, deque
from datetime import date, datetime, timedelta

import logic as L
from texts import LANG_NAME, TXT, tr

for _s in (sys.stdout, sys.stderr):  # Windows ойнаси ўзбекча ҳарфда ботни ўчирмасин
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db"))
E = lambda s: html.escape(s, quote=False)  # апостроф ўзгармасин
HOURS = [f"{h:02d}:00" for h in range(7, 23)]
MENU = {tr(lg, k): c for lg in TXT for k, c in (("m_add", "add"), ("m_list", "list"), ("m_soon", "soon"), ("m_set", "set"))}
WIZ_KEYS = {"fr", "dy", "wd", "cal", "cd", "tm", "tmd", "tmc", "ld", "am", "cx"}
TEXT_STEPS = {"title", "amount", "time_custom", "snooze_custom"}


def kb(rows):
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}


def main_kb(lg):
    r = lambda *k: [{"text": tr(lg, x)} for x in k]
    return {"keyboard": [r("m_add", "m_list"), r("m_soon", "m_set")], "resize_keyboard": True, "is_persistent": True}


class Tg:
    def __init__(self, token):
        self.url = f"https://api.telegram.org/bot{token}/"

    def call(self, method, **p):
        req = urllib.request.Request(self.url + method, json.dumps(p).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=70) as r:
            return json.load(r)

    def send(self, chat, text, markup=None):
        p = {"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        if markup:
            p["reply_markup"] = markup
        return self.call("sendMessage", **p)

    def edit(self, chat, mid, text, markup=None):
        p = {"chat_id": chat, "message_id": mid, "text": text, "parse_mode": "HTML"}
        if markup:
            p["reply_markup"] = markup
        try:
            self.call("editMessageText", **p)
            return True
        except urllib.error.HTTPError as e:
            return "not modified" in e.read().decode("utf-8", "replace")
        except Exception:
            return False

    def delete(self, chat, mid):
        try:
            self.call("deleteMessage", chat_id=chat, message_id=mid)
        except Exception:
            pass


# ---------- матн ва тугмалар ----------
def fmt_date(iso):
    return f"{iso[8:]}.{iso[5:7]}.{iso[:4]}"


def when_of(d, lg):
    f = d["freq"]
    if f == "monthly":
        return tr(lg, "w_month_end") if d["day"] == 31 else tr(lg, "w_month", d=d["day"])
    if f == "weekly":
        return tr(lg, "w_week", wd=TXT[lg]["wd"][d["day"] % 7])
    if f == "once":
        return fmt_date(d["date"])
    return tr(lg, "w_day")


def lead_of(n, lg):
    return tr(lg, "lead_x", n=n) if n else ""


def describe(r, lg):
    s = f"<b>{E(r['title'])}</b>\n🗓 {when_of(r, lg)}{lead_of(r['lead_days'], lg)}\n⏰ {', '.join(L.times_of(r))}"
    if r["amount"]:
        s += f"\n💰 {E(r['amount'])}"
    return s + ("" if r["active"] else "  ⏸")


def card(x):
    lg = x.get("lang") or "uz"
    n = x["days_left"]
    state = tr(lg, "c_over", n=-n) if n < 0 else tr(lg, "c_today") if n == 0 else tr(lg, "c_left", n=n)
    s = f"🚨 <b>{E(x['title'])}</b>\n{state}\n📅 {fmt_date(x['due'])}"
    if x["amount"]:
        s += f"\n💰 {E(x['amount'])}"
    return s + (f"\n{tr(lg, 'c_rep')}" if x["sent_count"] else "")


def action_kb(oid, lg):
    return kb([[(tr(lg, "b_later"), f"sn:{oid}"), (tr(lg, "b_done"), f"dn:{oid}")]])


def snooze_kb(oid, lg):
    h = lambda v: (tr(lg, "hours", h=v), f"sz:{oid}:{v}")
    return kb([[h("1"), h("2"), h("3")], [h("6"), h("12"), (tr(lg, "tomorrow"), f"sz:{oid}:t")], [(tr(lg, "custom"), f"sz:{oid}:c")]])


def cancel_row(lg):
    return [(tr(lg, "cancel"), "cx")]


def cal_markup(lg, ym, today):
    y, m = ym
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    py, pm = (y - 1, 12) if m == 1 else (y, m - 1)
    can_prev = (y, m) > (today.year, today.month)
    can_next = (y, m) < (today.year + 2, today.month)
    rows = [[("◀" if can_prev else " ", f"cal:{py}-{pm}" if can_prev else "x"), (f"{TXT[lg]['months'][m - 1]} {y}", "x"), ("▶" if can_next else " ", f"cal:{ny}-{nm}" if can_next else "x")],
            [(w, "x") for w in TXT[lg]["wd_s"]]]
    for week in calendar.monthcalendar(y, m):
        row = []
        for n in week:
            if n == 0:
                row.append((" ", "x"))
            elif date(y, m, n) < today:
                row.append(("·", "x"))
            else:
                row.append((("🔸" if date(y, m, n) == today else "") + str(n), f"cd:{y:04d}-{m:02d}-{n:02d}"))
        rows.append(row)
    return rows + [cancel_row(lg)]


def render(step, d, lg, today, warn=""):
    title = E(d.get("title", ""))
    if step == "title":
        return tr(lg, "q_title"), kb([cancel_row(lg)])
    if step == "freq":
        return tr(lg, "q_type", title=title), kb([[(tr(lg, k), f"fr:{v}")] for k, v in (("t_once", "once"), ("t_month", "monthly"), ("t_week", "weekly"), ("t_day", "daily"))] + [cancel_row(lg)])
    if step == "day":
        rows = [[(str(n), f"dy:{n}") for n in range(s, s + 6)] for s in range(1, 31, 6)]
        return tr(lg, "q_dom", title=title), kb(rows + [[(tr(lg, "month_end"), "dy:31")], cancel_row(lg)])
    if step == "wd":
        return tr(lg, "q_wd", title=title), kb([[(w, f"wd:{i}") for i, w in enumerate(TXT[lg]["wd_s"])], cancel_row(lg)])
    if step == "date":
        y, m = d.get("cal") or [today.year, today.month]
        return tr(lg, "q_date", title=title), kb(cal_markup(lg, (y, m), today))
    if step == "time":
        sel = d.get("sel", [])
        rows = [[((("✅ " if t in sel else "") + t), f"tm:{t}") for t in HOURS[i:i + 4]] for i in range(0, len(HOURS), 4)]
        extra = [t for t in sel if t not in HOURS]
        if extra:
            rows.append([(f"✅ {t}", f"tm:{t}") for t in extra[:4]])
        rows.append([(tr(lg, "time_other"), "tmc"), (tr(lg, "time_done") + (f" ({len(sel)})" if sel else ""), "tmd")])
        text = tr(lg, "q_time", title=title, when=when_of(d, lg), sel=", ".join(sorted(sel)) or tr(lg, "none")) + warn
        return text, kb(rows + [cancel_row(lg)])
    if step == "time_custom":
        return tr(lg, "q_time_custom") + warn, kb([cancel_row(lg)])
    if step == "lead":
        return tr(lg, "q_lead", title=title), kb([[(tr(lg, "l0"), "ld:0"), (tr(lg, "l1"), "ld:1")], [(tr(lg, "l3"), "ld:3"), (tr(lg, "l7"), "ld:7")], cancel_row(lg)])
    if step == "amount":
        return tr(lg, "q_amount"), kb([[(tr(lg, "skip"), "am:skip")], cancel_row(lg)])
    if step == "snooze_custom":
        return tr(lg, "later_custom_q") + warn, None


def next_step(d):
    if "title" not in d:
        return "title"
    if "freq" not in d:
        return "freq"
    f = d["freq"]
    if f == "monthly" and "day" not in d:
        return "day"
    if f == "weekly" and "day" not in d:
        return "wd"
    if f == "once" and "date" not in d:
        return "date"
    if "times" not in d:
        return "time"
    if f in ("monthly", "once") and "lead" not in d:
        return "lead"
    if "amount" not in d:
        return "amount"
    return None


# ---------- ишлов бериш ----------
class App:
    def __init__(self, conn, tg, now=time.time):
        self.db, self.tg, self.now = conn, tg, now
        self.hits = defaultdict(deque)

    def limited(self, uid):
        q, t = self.hits[uid], self.now()
        while q and t - q[0] > 10:
            q.popleft()
        q.append(t)
        return len(q) > 40

    def today(self, u):
        return L.local_dt(u, self.now()).date()

    def fmt_ts(self, u, ts):
        return L.local_dt(u, ts).strftime("%d.%m %H:%M")

    # --- битта хабарни таҳрирлаш (эски хабарлар қолиб кетмасин) ---
    def put(self, chat, d, text, markup):
        mid = d.get("mid")
        if mid and self.tg.edit(chat, mid, text, markup):
            return
        r = self.tg.send(chat, text, markup)
        d["mid"] = ((r or {}).get("result") or {}).get("message_id")

    def wiz(self, uid, chat, d, step=None, warn=""):
        u = L.get_user(self.db, uid)
        lg = u["lang"] or "uz"
        step = step or next_step(d)
        if step is None:
            return self.finish(uid, chat, d, u, lg)
        text, markup = render(step, d, lg, self.today(u), warn)
        self.put(chat, d, text, markup)
        L.set_conv(self.db, uid, step, d)

    def finish(self, uid, chat, d, u, lg):
        L.clear_conv(self.db, uid)
        rid = L.add_reminder(self.db, uid, d, self.now())
        if rid is None:
            return self.put(chat, d, tr(lg, "limit", n=L.MAX_REMINDERS), None)
        L.sync(self.db, self.now())
        r = L.own_reminder(self.db, uid, rid)
        nf = L.next_fire(self.db, uid, r, self.now())
        text = tr(lg, "saved", title=E(r["title"]), when=when_of(r, lg) + lead_of(r["lead_days"], lg), times=", ".join(L.times_of(r)),
                  extra=(f"\n💰 {E(r['amount'])}" if r["amount"] else ""), next=self.fmt_ts(u, nf) if nf else tr(lg, "none"))
        self.put(chat, d, text, kb([[(tr(lg, "add_more"), "addnew"), (tr(lg, "to_list"), "lst")]]))

    def ask_lang(self, chat):
        self.tg.send(chat, TXT["uz"]["lang_pick"], kb([[("🇺🇿 UZB", "lg:uz"), ("🇷🇺 РУС", "lg:ru")]]))

    def on_message(self, m):
        if m["chat"]["type"] != "private" or "from" not in m:
            return
        uid, chat, text = m["from"]["id"], m["chat"]["id"], (m.get("text") or "").strip()
        if self.limited(uid):
            return
        u = L.ensure_user(self.db, uid, chat)
        if u["lang"] is None:
            return self.ask_lang(chat)
        lg = u["lang"]
        cmd = text.split("@")[0].split()[0].lower().lstrip("/") if text.startswith("/") else MENU.get(text, "")
        if cmd == "start":
            L.clear_conv(self.db, uid)
            return self.tg.send(chat, tr(lg, "welcome"), main_kb(lg))
        if cmd == "add":
            d = {}
            L.set_conv(self.db, uid, "title", d)
            return self.wiz(uid, chat, d, "title")
        if cmd == "list":
            return self.show_list(uid, chat, lg)
        if cmd == "soon":
            return self.show_soon(uid, chat, u, lg)
        if cmd == "set":
            return self.show_settings(chat, u)
        if cmd == "cancel":
            L.clear_conv(self.db, uid)
            return self.tg.send(chat, tr(lg, "cancelled"), main_kb(lg))
        if cmd in ("privacy", "help"):
            return self.tg.send(chat, tr(lg, "privacy"))
        if cmd == "deleteme":
            return self.tg.send(chat, tr(lg, "del_all_q"), kb([[(tr(lg, "del_all_yes"), "del:yes"), (tr(lg, "no"), "del:no")]]))
        step, d = L.get_conv(self.db, uid)
        if step in TEXT_STEPS:
            self.on_text(uid, chat, step, d, text, lg)
            self.tg.delete(chat, m["message_id"]) if "message_id" in m else None
        elif step is None:
            self.tg.send(chat, tr(lg, "pick_menu"), main_kb(lg))

    def on_text(self, uid, chat, step, d, text, lg):
        if step == "title":
            v = L.clean(text, 80)
            if v:
                d["title"] = v
                self.wiz(uid, chat, d)
        elif step == "amount":
            d["amount"] = L.clean(text, 40)
            self.wiz(uid, chat, d)
        elif step == "time_custom":
            v = L.parse_time(text)
            if v is None:
                return self.wiz(uid, chat, d, "time_custom", "\n⚠️ " + tr(lg, "bad_time"))
            sel = set(d.get("sel", []))
            if len(sel) < 12:
                sel.add(v)
            d["sel"] = sorted(sel)
            self.wiz(uid, chat, d, "time")
        elif step == "snooze_custom":
            h = L.parse_hours(text)
            if h is None:
                return self.tg.send(chat, tr(lg, "bad_hours"))
            L.clear_conv(self.db, uid)
            if L.snooze(self.db, uid, d["oid"], self.now(), hours=h) is None:
                return self.tg.send(chat, tr(lg, "closed"))
            self.tg.send(chat, tr(lg, "later_ok", h=f"{h:g}"), main_kb(lg))

    def on_callback(self, c):
        uid, msg = c["from"]["id"], c.get("message")
        self.tg.call("answerCallbackQuery", callback_query_id=c["id"])
        if not msg or msg["chat"]["type"] != "private" or self.limited(uid):
            return
        chat, mid, data = msg["chat"]["id"], msg["message_id"], c.get("data", "")
        u = L.ensure_user(self.db, uid, chat)
        key, _, arg = data.partition(":")
        if key == "x":
            return
        if key == "lg" and arg in LANG_NAME:
            first = u["lang"] is None
            L.set_user(self.db, uid, lang=arg)
            u = L.get_user(self.db, uid)
            if first:
                self.tg.edit(chat, mid, tr(arg, "lang_set"))
                return self.tg.send(chat, tr(arg, "welcome"), main_kb(arg))
            self.tg.send(chat, tr(arg, "lang_set"), main_kb(arg))
            return self.show_settings(chat, u, mid)
        if u["lang"] is None:
            return self.ask_lang(chat)
        lg = u["lang"]
        step, d = L.get_conv(self.db, uid)
        if key in WIZ_KEYS:
            if step is None or d.get("mid") != mid:
                return  # эски/эскирган тугма
            return self.wizard_cb(uid, chat, mid, key, arg, step, d, u, lg)
        if key in ("dn", "sn", "sz") and arg.split(":")[0].isdigit():
            return self.occ_cb(uid, chat, mid, key, arg, lg)
        if key == "addnew":
            d = {"mid": mid}
            L.set_conv(self.db, uid, "title", d)
            return self.wiz(uid, chat, d, "title")
        if key == "lst":
            return self.show_list(uid, chat, lg, mid)
        if key == "ls" and arg.isdigit():
            return self.show_item(uid, chat, mid, int(arg), lg)
        if key in ("pz", "rm", "rmy") and arg.isdigit():
            return self.item_action(uid, chat, mid, key, int(arg), lg)
        if key == "tz" and arg in ("5", "3"):
            L.set_user(self.db, uid, tz=float(arg))
        elif key == "rp" and arg in ("0", "1", "2", "3", "6"):
            L.set_user(self.db, uid, repeat_h=float(arg))
        elif key == "snd":
            return self.tg.send(chat, tr(lg, "sound_help"))
        elif key == "del":
            if arg == "yes":
                L.delete_user_data(self.db, uid)
                return self.tg.edit(chat, mid, tr(lg, "all_deleted"))
            return self.tg.edit(chat, mid, tr(lg, "cancelled"))
        else:
            return
        self.show_settings(chat, L.get_user(self.db, uid), mid)

    def wizard_cb(self, uid, chat, mid, key, arg, step, d, u, lg):
        if key == "cx":
            L.clear_conv(self.db, uid)
            return self.tg.edit(chat, mid, tr(lg, "cancelled"))
        if key == "fr" and step == "freq" and arg in ("once", "monthly", "weekly", "daily"):
            d["freq"] = arg
        elif key in ("dy", "wd") and step in ("day", "wd") and (v := L.parse_int(arg, 0 if key == "wd" else 1, 6 if key == "wd" else 31)) is not None:
            d["day"] = v
        elif key == "cal" and step == "date":
            try:
                y, m = map(int, arg.split("-"))
                date(y, m, 1)
            except ValueError:
                return
            d["cal"] = [y, m]
            return self.wiz(uid, chat, d, "date")
        elif key == "cd" and step == "date":
            try:
                v = date.fromisoformat(arg)
            except ValueError:
                return
            if v < self.today(u):
                return
            d["date"] = v.isoformat()
        elif key == "tm" and step == "time":
            sel = set(d.get("sel", []))
            sel ^= {arg} if L.parse_time(arg) == arg else set()
            d["sel"] = sorted(sel)
            return self.wiz(uid, chat, d, "time")
        elif key == "tmc" and step == "time":
            return self.wiz(uid, chat, d, "time_custom")
        elif key == "tmd" and step == "time":
            if not d.get("sel"):
                return self.wiz(uid, chat, d, "time", tr(lg, "time_need"))
            d["times"] = sorted(d["sel"])
        elif key == "ld" and step == "lead" and arg in ("0", "1", "3", "7"):
            d["lead"] = int(arg)
        elif key == "am" and step == "amount":
            d["amount"] = ""
        else:
            return
        self.wiz(uid, chat, d)

    def occ_cb(self, uid, chat, mid, key, arg, lg):
        oid = int(arg.split(":")[0])
        o = L.own_occ(self.db, uid, oid)  # ЭГАЛИК текшируви
        if not o:
            return
        if key == "dn":
            L.mark_done(self.db, uid, oid)
            r = L.own_reminder(self.db, uid, o["reminder_id"])
            return self.tg.edit(chat, mid, tr(lg, "done_msg", title=E(r["title"])))
        if o["status"] != "pending":
            return self.tg.edit(chat, mid, tr(lg, "closed"))
        if key == "sn":
            return self.tg.edit(chat, mid, tr(lg, "later_q"), snooze_kb(oid, lg))
        val = arg.split(":")[1] if ":" in arg else ""
        if val == "c":
            d = {"oid": oid, "mid": mid}
            L.set_conv(self.db, uid, "snooze_custom", d)
            return self.tg.edit(chat, mid, tr(lg, "later_custom_q"))
        if val == "t":
            L.snooze(self.db, uid, oid, self.now(), tomorrow=True)
            return self.tg.edit(chat, mid, tr(lg, "later_tom"))
        h = L.parse_hours(val)
        if h is not None:
            L.snooze(self.db, uid, oid, self.now(), hours=h)
            self.tg.edit(chat, mid, tr(lg, "later_ok", h=val))

    # ---------- рўйхатлар ----------
    def show_list(self, uid, chat, lg, mid=None):
        rows = self.db.execute("SELECT * FROM reminders WHERE user_id=? ORDER BY id", (uid,)).fetchall()
        if not rows:
            text, markup = tr(lg, "list_empty"), None
        else:
            text = tr(lg, "list_title")
            markup = kb([[(("⏸ " if not r["active"] else "🔔 ") + r["title"], f"ls:{r['id']}")] for r in rows])
        if not (mid and self.tg.edit(chat, mid, text, markup)):
            self.tg.send(chat, text, markup)

    def show_item(self, uid, chat, mid, rid, lg):
        r = L.own_reminder(self.db, uid, rid)
        if not r:
            return
        self.tg.edit(chat, mid, describe(r, lg), kb([[(tr(lg, "resume" if not r["active"] else "pause"), f"pz:{rid}"), (tr(lg, "del"), f"rm:{rid}")], [(tr(lg, "back"), "lst")]]))

    def item_action(self, uid, chat, mid, key, rid, lg):
        r = L.own_reminder(self.db, uid, rid)
        if not r:
            return
        if key == "pz":
            self.db.execute("UPDATE reminders SET active=? WHERE id=? AND user_id=?", (0 if r["active"] else 1, rid, uid))
            self.db.commit()
            return self.show_item(uid, chat, mid, rid, lg)
        if key == "rm":
            return self.tg.edit(chat, mid, tr(lg, "del_q", title=E(r["title"])), kb([[(tr(lg, "yes_del"), f"rmy:{rid}"), (tr(lg, "no"), f"ls:{rid}")]]))
        self.db.execute("DELETE FROM occ WHERE reminder_id=? AND user_id=?", (rid, uid))
        self.db.execute("DELETE FROM reminders WHERE id=? AND user_id=?", (rid, uid))
        self.db.commit()
        self.tg.edit(chat, mid, tr(lg, "deleted"), kb([[(tr(lg, "back"), "lst")]]))

    def show_soon(self, uid, chat, u, lg):
        now = self.now()
        items = []
        for r in self.db.execute("SELECT * FROM reminders WHERE user_id=? AND active=1", (uid,)).fetchall():
            ts = L.next_fire(self.db, uid, r, now)
            if ts and ts - now <= 30 * 86400:
                items.append((ts, r))
        if not items:
            return self.tg.send(chat, tr(lg, "soon_empty"), main_kb(lg))
        lines = [f"🔔 <b>{self.fmt_ts(u, ts)}</b> · {E(r['title'])}" + (f" · {E(r['amount'])}" if r["amount"] else "") for ts, r in sorted(items, key=lambda x: x[0])]
        self.tg.send(chat, tr(lg, "soon_title") + "\n\n" + "\n".join(lines), main_kb(lg))

    def show_settings(self, chat, u, mid=None):
        lg = u["lang"] or "uz"
        rep = tr(lg, "rep_off") if not u["repeat_h"] else tr(lg, "rep_val", h=f"{u['repeat_h']:g}")
        text = tr(lg, "settings", lang=LANG_NAME[lg], tz=f"{u['tz']:g}", rep=rep, qs=u["quiet_start"], qe=u["quiet_end"])
        markup = kb([[("🇺🇿 UZB", "lg:uz"), ("🇷🇺 РУС", "lg:ru")], [(tr(lg, "tz5"), "tz:5"), (tr(lg, "tz3"), "tz:3")],
                     [(tr(lg, "rep_btn_off"), "rp:0")] + [(tr(lg, "rep_btn", h=h), f"rp:{h}") for h in (1, 2, 3, 6)], [(tr(lg, "sound_btn"), "snd")]])
        if not (mid and self.tg.edit(chat, mid, text, markup)):
            self.tg.send(chat, text, markup)

    # ---------- цикл ----------
    def tick(self):
        now = self.now()
        L.sync(self.db, now)
        for x in L.pop_due(self.db, now):
            try:
                self.tg.send(x["chat_id"], card(x), action_kb(x["oid"], x.get("lang") or "uz"))
            except Exception as e:
                print("юбориб бўлмади:", type(e).__name__, flush=True)


def run():
    conn = L.connect(DB_PATH)
    app = App(conn, Tg(os.environ["TELEGRAM_BOT_TOKEN"]))
    try:
        print("Бот ишга тушди: @" + app.tg.call("getMe")["result"]["username"], flush=True)
    except Exception as e:
        raise SystemExit(f"Токен нотўғри ёки интернет йўқ ({type(e).__name__}). Токенни текширинг.")
    row = conn.execute("SELECT v FROM meta WHERE k='offset'").fetchone()
    offset = int(row["v"]) if row else 0
    while True:
        try:
            for up in app.tg.call("getUpdates", offset=offset, timeout=25, allowed_updates=["message", "callback_query"]).get("result", []):
                offset = up["update_id"] + 1
                print(time.strftime("%H:%M:%S"), "хабар келди:", "тугма" if "callback_query" in up else "матн", flush=True)
                try:
                    if "message" in up:
                        app.on_message(up["message"])
                    elif "callback_query" in up:
                        app.on_callback(up["callback_query"])
                except Exception as e:  # битта хато ботни тўхтатмайди
                    fr = traceback.extract_tb(e.__traceback__)[-1]
                    print("ИШЛОВ ХАТОСИ:", type(e).__name__, e, "— қатор", fr.lineno, fr.name, flush=True)
            conn.execute("INSERT OR REPLACE INTO meta VALUES('offset',?)", (str(offset),))
            conn.commit()
            app.tick()
        except Exception as e:
            print("тармоқ хатоси:", type(e).__name__, flush=True)
            time.sleep(5)


if __name__ == "__main__":
    run()
