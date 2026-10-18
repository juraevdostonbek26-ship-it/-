"""Telegram бот: кўп фойдаланувчили эслатма котиби (UZ/RU). Фақат стандарт кутубхона."""
import calendar, html, json, os, re, sys, time, traceback, urllib.error, urllib.request
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
MENU = {tr(lg, k): c for lg in TXT for k, c in (("m_add", "add"), ("m_list", "list"), ("m_soon", "soon"), ("m_set", "set"), ("m_fb", "feedback"))}
WIZ_KEYS = {"fr", "dy", "wd", "cal", "cd", "tm", "tmd", "tmc", "ld", "am", "cx", "bk"}
TEXT_STEPS = {"title", "amount", "time_custom", "snooze_custom", "day", "date", "time", "lead", "feedback"}


def kb(rows):
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}


def main_kb(lg):
    r = lambda *k: [{"text": tr(lg, x)} for x in k]
    return {"keyboard": [r("m_add", "m_list"), r("m_soon", "m_set"), r("m_fb")], "resize_keyboard": True, "is_persistent": True}


class Tg:
    def __init__(self, token, base=None):
        self.url = f"{base or os.environ.get('TELEGRAM_API') or 'https://api.telegram.org'}/bot{token}/"

    def call(self, method, **p):
        req = urllib.request.Request(self.url + method, json.dumps(p).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=70) as r:
            return json.load(r)

    def send_media(self, method, chat, field, url, caption=""):
        """Овоз/расмни ҳавола орқали юборади (Telegram ўзи юклаб олади)."""
        try:
            return self.call(method, chat_id=chat, **{field: url}, caption=caption)
        except Exception:
            return None

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

    def answer(self, cid, text=""):
        try:
            self.call("answerCallbackQuery", callback_query_id=cid, **({"text": text[:190]} if text else {}))
        except Exception:
            pass

    def delete(self, chat, mid):
        try:
            self.call("deleteMessage", chat_id=chat, message_id=mid)
        except Exception:
            pass


# ---------- матн ва тугмалар ----------
def fmt_date(iso):
    return f"{iso[8:]}.{iso[5:7]}.{iso[:4]}"


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
    h = lambda v, lab: (lab, f"sz:{oid}:{v}")
    m = lambda mm: h(str(mm / 60), tr(lg, "mins", m=mm))
    hr = lambda n: h(str(n), tr(lg, "hours", h=n))
    return kb([[m(15), m(30), hr(1)], [hr(2), hr(3), hr(6)], [(tr(lg, "tomorrow"), f"sz:{oid}:t"), (tr(lg, "custom"), f"sz:{oid}:c")]])


def cancel_row(lg):
    return [(tr(lg, "back_step"), "bk"), (tr(lg, "cancel"), "cx")]


def home_row(lg):
    return [(tr(lg, "btn_home"), "home")]


def kb_home(lg):
    return kb([home_row(lg)])


ASSET_BASE = ""  # сервер ишга тушганда https://… қўйилади: овоз ва фон файллари шу манзилдан юборилади
BG_LINK = os.environ.get("BG_LINK", "")  # Telegram фон ҳаволаси (t.me/bg/…): бир босишда DOJU фонини қўллайди
VIDEO_URL = {"uz": "", "ru": ""}  # YouTube видео қўлланма ҳаволалари (сервер муҳитидан); бўш бўлса тугма чиқмайди
WEBAPP_URL = ""  # сервер ишга тушганда https://…/app/ қўйилади; бўш бўлса веб тугмаси чиқмайди


def home_markup(lg):
    m = kb([[(tr(lg, "m_add"), "go:add"), (tr(lg, "m_list"), "go:list")], [(tr(lg, "m_soon"), "go:soon"), (tr(lg, "m_set"), "go:set")], [(tr(lg, "bg_btn"), "bg"), (tr(lg, "sound_btn"), "snd")], [(tr(lg, "m_fb"), "go:fb")]])
    if WEBAPP_URL:
        m["inline_keyboard"].append([{"text": tr(lg, "m_web"), "web_app": {"url": WEBAPP_URL}}])
    if VIDEO_URL.get(lg):
        m["inline_keyboard"].append([{"text": tr(lg, "m_video"), "url": VIDEO_URL[lg]}])
    return m


ORDER = ("amount", "lead", "times", "day", "date", "freq", "title")


def go_back(d):
    """Охирги жавобни олиб ташлайди (бир қадам орқага)."""
    for k in ORDER:
        if k in d:
            del d[k]
            if k == "freq":
                for x in ("day", "date", "times", "lead", "amount"):
                    d.pop(x, None)
            return k
    return None


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
        return (tr(lg, "q_title_edit", title=E(d.get("old_title", ""))) if d.get("edit") else tr(lg, "q_title")), kb([cancel_row(lg)])
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
        self.toast = ""
        self.errors = []
        self.verbose = False
        self.admin_chat = int(os.environ.get("ADMIN_ID", "0") or 0)  # асосчининг Telegram ID'си (махфий эмас, лекин env'да)

    def limited(self, uid):
        q, t = self.hits[uid], self.now()
        while q and t - q[0] > 10:
            q.popleft()
        q.append(t)
        return len(q) > 40

    def set_conv(self, uid, step, d):
        L.set_conv(self.db, uid, step, d, self.now())

    def get_conv(self, uid):
        return L.get_conv(self.db, uid, self.now())

    def today(self, u):
        return L.local_dt(u, self.now()).date()

    def fmt_ts(self, u, ts):
        return L.local_dt(u, ts).strftime("%d.%m %H:%M")

    # --- чат тоза қолиши: ягона «панел» хабари алмашиб туради ---
    def new_panel(self, uid, chat, text, markup):
        prev = L.get_user(self.db, uid)["panel_mid"]
        r = self.tg.send(chat, text, markup)
        mid = ((r or {}).get("result") or {}).get("message_id")
        L.set_user(self.db, uid, panel_mid=mid)
        if prev and prev != mid:
            self.tg.delete(chat, prev)
        return mid

    def panel(self, uid, chat, mid, text, markup):
        """mid берилса — шу хабарни жойида алмаштиради, бўлмаса янги панел (эскиси ўчади)."""
        if mid and self.tg.edit(chat, mid, text, markup):
            L.set_user(self.db, uid, panel_mid=mid)
            return mid
        return self.new_panel(uid, chat, text, markup)

    def put(self, uid, chat, d, text, markup):
        d["mid"] = self.panel(uid, chat, d.get("mid"), text, markup)

    def wiz(self, uid, chat, d, step=None, warn=""):
        u = L.get_user(self.db, uid)
        lg = u["lang"] or "uz"
        step = step or next_step(d)
        if step is None:
            return self.finish(uid, chat, d, u, lg)
        text, markup = render(step, d, lg, self.today(u), warn)
        self.put(uid, chat, d, text, markup)
        self.set_conv(uid, step, d)

    def finish(self, uid, chat, d, u, lg):
        L.clear_conv(self.db, uid)
        if d.get("edit"):
            if L.update_reminder(self.db, uid, d["edit"], d, self.now()):
                L.sync(self.db, self.now())
                return self.show_item(uid, chat, d.get("mid"), d["edit"], lg, header=tr(lg, "updated"))
            return self.show_home(uid, chat, lg, d.get("mid"))
        rid = L.add_reminder(self.db, uid, d, self.now())
        if rid is None:
            return self.put(uid, chat, d, tr(lg, "limit", n=L.MAX_REMINDERS), None)
        L.sync(self.db, self.now())
        r = L.own_reminder(self.db, uid, rid)
        nf = L.next_fire(self.db, uid, r, self.now())
        text = tr(lg, "saved", title=E(r["title"]), when=when_of(r, lg) + lead_of(r["lead_days"], lg), times=", ".join(L.times_of(r)),
                  extra=(f"\n💰 {E(r['amount'])}" if r["amount"] else ""), next=self.fmt_ts(u, nf) if nf else tr(lg, "none"))
        self.put(uid, chat, d, text, kb([[(tr(lg, "add_more"), "addnew"), (tr(lg, "to_list"), "lst")], home_row(lg)]))

    def ensure_anchor(self, uid, chat, lg, force=False):
        """Пастки меню (reply keyboard) ЎЧИРИЛМАЙДИГАН алоҳида хабарга боғланган: Telegram уни ўчирилса, менюни ҳам олиб ташлайди."""
        u = L.get_user(self.db, uid)
        if not force and u["anchor_mid"] and u["anchor_lang"] == lg:
            return
        r = self.tg.send(chat, tr(lg, "anchor"), main_kb(lg))
        mid = ((r or {}).get("result") or {}).get("message_id")
        L.set_user(self.db, uid, anchor_mid=mid, anchor_lang=lg)
        if u["anchor_mid"] and u["anchor_mid"] != mid:
            self.tg.delete(chat, u["anchor_mid"])

    def show_home(self, uid, chat, lg, mid=None):
        self.panel(uid, chat, mid, tr(lg, "home"), home_markup(lg))

    def ask_lang(self, uid, chat):
        self.new_panel(uid, chat, TXT["uz"]["lang_pick"], kb([[("🇺🇿 UZB", "lg:uz"), ("🇷🇺 РУС", "lg:ru")]]))

    def on_message(self, m):
        if m["chat"]["type"] != "private" or "from" not in m:
            return
        uid, chat, text = m["from"]["id"], m["chat"]["id"], (m.get("text") or "").strip()
        if self.limited(uid):
            return
        u = L.ensure_user(self.db, uid, chat)
        mine = lambda: m.get("message_id") and self.tg.delete(chat, m["message_id"])  # ёзганимиз чатда қолмасин
        if u["lang"] is None:
            mine()
            return self.ask_lang(uid, chat)
        lg = u["lang"]
        cmd = text.split("@")[0].split()[0].lower().lstrip("/") if text.startswith("/") else MENU.get(text, "")
        self.ensure_anchor(uid, chat, lg, force=(cmd == "start"))
        if cmd in ("start", "add", "list", "soon", "set", "cancel", "privacy", "help", "deleteme", "feedback", "id"):
            mine()
            L.clear_conv(self.db, uid)  # меню босилса, ярим қолган оқим тўхтайди
        if cmd == "start":
            return self.new_panel(uid, chat, tr(lg, "welcome"), home_markup(lg))
        if cmd == "add":
            d = {}
            return self.wiz(uid, chat, d, "title")
        if cmd == "list":
            return self.show_list(uid, chat, lg)
        if cmd == "soon":
            return self.show_soon(uid, chat, u, lg)
        if cmd == "set":
            return self.show_settings(uid, chat, u)
        if cmd == "cancel":
            return self.show_home(uid, chat, lg)
        if cmd == "id":
            return self.new_panel(uid, chat, tr(lg, "id_is", id=uid), kb_home(lg))
        if cmd == "feedback":
            return self.ask_feedback(uid, chat, lg, None)
        if cmd in ("privacy", "help"):
            return self.new_panel(uid, chat, tr(lg, "privacy"), kb_home(lg))
        if cmd == "deleteme":
            return self.new_panel(uid, chat, tr(lg, "del_all_q"), kb([[(tr(lg, "del_all_yes"), "del:yes"), (tr(lg, "no"), "del:no")]]))
        step, d = self.get_conv(uid)
        mine()
        if step in TEXT_STEPS:
            self.on_text(uid, chat, step, d, text, lg)
        elif step is None:
            title = L.clean(text, 80) if text and not text.startswith("/") else ""
            if title:  # ҳар қандай ёзилган матн — янги эслатма номи (тугма босмасдан тез қўшиш)
                self.wiz(uid, chat, {"title": title})
            else:
                self.new_panel(uid, chat, tr(lg, "pick_menu"), home_markup(lg))

    def ask_feedback(self, uid, chat, lg, mid):
        self.set_conv(uid, "feedback", {})
        self.panel(uid, chat, mid, tr(lg, "fb_q"), kb_home(lg))

    def on_text(self, uid, chat, step, d, text, lg):
        if step == "feedback":
            L.clear_conv(self.db, uid)
            fid = L.add_feedback(self.db, uid, text, self.now())
            if fid:
                self.deliver_feedback()
            return self.new_panel(uid, chat, tr(lg, "fb_ok" if fid else "fb_limit"), kb_home(lg))
        if step == "title":
            v = L.clean(text, 80)
            if v:
                d["title"] = v
                self.wiz(uid, chat, d)
        elif step == "amount":
            d["amount"] = L.clean(text, 40)
            self.wiz(uid, chat, d)
        elif step == "day":  # тугма ўрнига рақам ёзса ҳам бўлади
            v = L.parse_int(text, 1, 31)
            if v:
                d["day"] = v
                self.wiz(uid, chat, d)
        elif step == "date":
            v = parse_date(text, self.today(L.get_user(self.db, uid)))
            if v:
                d["date"] = v.isoformat()
                self.wiz(uid, chat, d)
        elif step == "lead":
            v = L.parse_int(text, 0, 7)
            if v is not None:
                d["lead"] = v
                self.wiz(uid, chat, d)
        elif step in ("time", "time_custom"):
            v = L.parse_time(text)
            if v is None:
                return self.wiz(uid, chat, d, step, "\n⚠️ " + tr(lg, "bad_time"))
            sel = set(d.get("sel", []))
            if len(sel) < 12:
                sel.add(v)
            d["sel"] = sorted(sel)
            self.wiz(uid, chat, d, "time")
        elif step == "snooze_custom":
            h = L.parse_hours(text)
            if h is None:
                return self.panel(uid, chat, d.get("mid"), tr(lg, "later_custom_q") + "\n⚠️ " + tr(lg, "bad_hours"), None)
            L.clear_conv(self.db, uid)
            ok = L.snooze(self.db, uid, d["oid"], self.now(), hours=h)
            L.set_card(self.db, d["oid"], None)
            self.tg.delete(chat, d.get("mid"))
            self.new_panel(uid, chat, tr(lg, "later_ok", h=f"{h:g}") if ok else tr(lg, "closed"), kb_home(lg))

    def on_callback(self, c):
        self.toast = ""
        try:
            self._on_callback(c)
        finally:
            self.tg.answer(c["id"], self.toast)

    def _on_callback(self, c):
        uid, msg = c["from"]["id"], c.get("message")
        if not msg or msg["chat"]["type"] != "private" or self.limited(uid):
            return
        chat, mid, data = msg["chat"]["id"], msg["message_id"], c.get("data", "")
        u = L.ensure_user(self.db, uid, chat)
        key, _, arg = data.partition(":")
        if key == "x" or u["anchor_mid"] == mid:  # доимий меню хабарига тегилмайди
            return
        if key == "lg" and arg in LANG_NAME:
            first = u["lang"] is None
            L.set_user(self.db, uid, lang=arg)
            u = L.get_user(self.db, uid)
            self.ensure_anchor(uid, chat, arg)  # пастки меню янги тилда
            if first:
                return self.new_panel(uid, chat, tr(arg, "welcome"), home_markup(arg))
            return self.show_settings(uid, chat, u, mid)
        if u["lang"] is None:
            return self.ask_lang(uid, chat)
        lg = u["lang"]
        self.ensure_anchor(uid, chat, lg)
        if key == "home":
            L.clear_conv(self.db, uid)
            return self.show_home(uid, chat, lg, mid)
        if key == "go" and arg in ("add", "list", "soon", "set", "fb"):
            L.clear_conv(self.db, uid)
            if arg == "add":
                return self.wiz(uid, chat, {"mid": mid}, "title")
            if arg == "fb":
                return self.ask_feedback(uid, chat, lg, mid)
            return {"list": lambda: self.show_list(uid, chat, lg, mid), "soon": lambda: self.show_soon(uid, chat, u, lg, mid),
                    "set": lambda: self.show_settings(uid, chat, u, mid)}[arg]()
        step, d = self.get_conv(uid)
        if key in WIZ_KEYS:
            if step is None:
                return self.show_home(uid, chat, lg, mid)  # оқим эскирган/тугаган: ўлик тугмалар қолмасин
            if d.get("mid") != mid:
                return  # бошқа (эски) оқимнинг тугмаси
            return self.wizard_cb(uid, chat, mid, key, arg, step, d, u, lg)
        if key in ("dn", "sn", "sz") and arg.split(":")[0].isdigit():
            return self.occ_cb(uid, chat, mid, key, arg, lg)
        if key == "addnew":
            d = {"mid": mid}
            self.set_conv(uid, "title", d)
            return self.wiz(uid, chat, d, "title")
        if key == "lst":
            return self.show_list(uid, chat, lg, mid)
        if key == "set":
            return self.show_settings(uid, chat, u, mid)
        if key == "ls" and arg.isdigit():
            return self.show_item(uid, chat, mid, int(arg), lg)
        if key in ("pz", "rm", "rmy", "em", "sk") and arg.isdigit():
            return self.item_action(uid, chat, mid, key, int(arg), lg)
        if key == "ed":
            return self.start_edit(uid, chat, mid, arg, lg)
        if key == "tz" and arg in ("5", "3"):
            L.set_user(self.db, uid, tz=float(arg))
        elif key == "rp" and arg in ("0", "m", "1", "3", "6"):
            L.set_user(self.db, uid, repeat_h=0.016667 if arg == "m" else float(arg))
        elif key == "dg" and arg in ("off", "7", "8", "9"):
            L.set_user(self.db, uid, digest_hour=None if arg == "off" else int(arg), digest_date=None)
        elif key == "qh" and arg in ("off", "21", "22", "23"):
            qs, qe = (0, 0) if arg == "off" else (int(arg), {"21": 6, "22": 7, "23": 8}[arg])
            L.set_user(self.db, uid, quiet_start=qs, quiet_end=qe)
        elif key == "snd":
            if ASSET_BASE:  # файл ОЛДИН юборилади, меню (панель) ҳар доим ЭНГ ПАСТДА қолади
                self.tg.send_media("sendAudio", chat, "audio", ASSET_BASE + "/assets/doju_ovoz.mp3", tr(lg, "snd_caption"))
                self.new_panel(uid, chat, tr(lg, "sound_help"), kb([[(tr(lg, "back_set"), "set")], home_row(lg)]))
            else:
                self.panel(uid, chat, mid, tr(lg, "sound_help"), kb([[(tr(lg, "back_set"), "set")], home_row(lg)]))
            return
        elif key == "bg":
            if BG_LINK:
                return self.panel(uid, chat, mid, tr(lg, "bg_help", how=tr(lg, "bg_how_link")), {"inline_keyboard": [[{"text": tr(lg, "bg_btn"), "url": BG_LINK}], [{"text": tr(lg, "back_set"), "callback_data": "set"}], [{"text": tr(lg, "btn_home"), "callback_data": "home"}]]})
            markup = kb([[(tr(lg, "back_set"), "set")], home_row(lg)])
            if ASSET_BASE:  # расм ОЛДИН, меню энг пастда
                self.tg.send_media("sendPhoto", chat, "photo", ASSET_BASE + "/assets/doju_fon.png")
                self.new_panel(uid, chat, tr(lg, "bg_help", how=tr(lg, "bg_how_photo")), markup)
            else:
                self.panel(uid, chat, mid, tr(lg, "bg_help", how=tr(lg, "bg_how_photo")), markup)
            return
        elif key == "del":
            if arg == "yes":
                L.delete_user_data(self.db, uid)
                return self.tg.edit(chat, mid, tr(lg, "all_deleted"))
            return self.tg.edit(chat, mid, tr(lg, "cancelled"), kb_home(lg))
        else:
            return
        self.show_settings(uid, chat, L.get_user(self.db, uid), mid)

    def wizard_cb(self, uid, chat, mid, key, arg, step, d, u, lg):
        if key == "cx":
            L.clear_conv(self.db, uid)
            if d.get("edit"):
                return self.show_item(uid, chat, mid, d["edit"], lg)
            return self.show_home(uid, chat, lg, mid)
        if key == "bk" and d.get("edit") and step != "time_custom":
            L.clear_conv(self.db, uid)
            return self.show_edit_menu(uid, chat, mid, d["edit"], lg)
        if key == "bk":
            if step == "time_custom":
                return self.wiz(uid, chat, d, "time")
            if go_back(d) is None:
                L.clear_conv(self.db, uid)
                return self.show_home(uid, chat, lg, mid)
            return self.wiz(uid, chat, d)
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
            L.set_card(self.db, oid, None)
            self.toast = tr(lg, "b_done")
            return self.tg.delete(chat, mid)  # бажарилган карточка чатда қолмайди
        if o["status"] != "pending":
            self.toast = tr(lg, "closed")
            L.set_card(self.db, oid, None)
            return self.tg.delete(chat, mid)
        if key == "sn":
            return self.tg.edit(chat, mid, tr(lg, "later_q"), snooze_kb(oid, lg))
        val = arg.split(":")[1] if ":" in arg else ""
        if val == "c":
            self.set_conv(uid, "snooze_custom", {"oid": oid, "mid": mid})
            return self.tg.edit(chat, mid, tr(lg, "later_custom_q"))
        if val == "t":
            L.snooze(self.db, uid, oid, self.now(), tomorrow=True)
            L.set_card(self.db, oid, None)
            self.toast = tr(lg, "toast_tom")
            return self.tg.delete(chat, mid)
        h = L.parse_hours(val)
        if h is not None:
            L.snooze(self.db, uid, oid, self.now(), hours=h)
            L.set_card(self.db, oid, None)
            self.toast = tr(lg, "toast_later_m", m=round(h * 60)) if h < 1 else tr(lg, "toast_later", h=f"{h:g}")
            self.tg.delete(chat, mid)

    # ---------- рўйхатлар ----------
    def show_list(self, uid, chat, lg, mid=None):
        rows = self.db.execute("SELECT * FROM reminders WHERE user_id=? ORDER BY id", (uid,)).fetchall()
        text = tr(lg, "list_title") if rows else tr(lg, "list_empty")
        markup = kb([[(("⏸ " if not r["active"] else "🔔 ") + r["title"], f"ls:{r['id']}")] for r in rows] + [home_row(lg)])
        self.panel(uid, chat, mid, text, markup)

    def show_item(self, uid, chat, mid, rid, lg, header=""):
        r = L.own_reminder(self.db, uid, rid)
        if not r:
            return
        rows = [[(tr(lg, "b_edit"), f"em:{rid}"), (tr(lg, "resume" if not r["active"] else "pause"), f"pz:{rid}")]]
        rows.append(([(tr(lg, "b_skip"), f"sk:{rid}")] if r["freq"] != "once" else []) + [(tr(lg, "del"), f"rm:{rid}")])
        rows.append([(tr(lg, "back"), "lst"), (tr(lg, "btn_home"), "home")])
        self.panel(uid, chat, mid, (header + "\n\n" if header else "") + describe(r, lg), kb(rows))

    def show_edit_menu(self, uid, chat, mid, rid, lg):
        r = L.own_reminder(self.db, uid, rid)
        if not r:
            return
        e = lambda k: (tr(lg, f"e_{k}"), f"ed:{rid}:{k}")
        rows = [[e("title"), e("when")], [e("times")] + ([e("lead")] if r["freq"] in ("monthly", "once") else []), [e("amount")], [(tr(lg, "back"), f"ls:{rid}"), (tr(lg, "btn_home"), "home")]]
        self.panel(uid, chat, mid, tr(lg, "edit_menu", desc=describe(r, lg)), kb(rows))

    def start_edit(self, uid, chat, mid, arg, lg):
        """arg = «<id>:<майдон>». Мавжуд қийматлар тўлдирилади, таҳрирланаётгани ўчирилиб қайта сўралади."""
        rid_s, _, field = arg.partition(":")
        r = L.own_reminder(self.db, uid, int(rid_s)) if rid_s.isdigit() else None  # ЭГАЛИК текшируви
        if not r or field not in ("title", "when", "times", "lead", "amount"):
            return
        times = L.times_of(r)
        d = {"edit": r["id"], "mid": mid, "old_title": r["title"], "title": r["title"], "freq": r["freq"], "times": times, "sel": times, "lead": r["lead_days"], "amount": r["amount"]}
        if r["day"] is not None:
            d["day"] = r["day"]
        if r["date"]:
            d["date"] = r["date"]
        if field == "when":
            for k in ("freq", "day", "date"):
                d.pop(k, None)
        elif field == "lead" and r["freq"] in ("monthly", "once"):
            d.pop("lead")
        else:
            d.pop({"title": "title", "times": "times", "amount": "amount"}.get(field, "x"), None)
        self.wiz(uid, chat, d)

    def item_action(self, uid, chat, mid, key, rid, lg):
        r = L.own_reminder(self.db, uid, rid)
        if not r:
            return
        if key == "em":
            return self.show_edit_menu(uid, chat, mid, rid, lg)
        if key == "sk":
            due = L.skip_next(self.db, uid, rid, self.now())
            self.toast = tr(lg, "toast_skipped", d=f"{due:%d.%m}") if due else tr(lg, "skip_none")
            return self.show_item(uid, chat, mid, rid, lg)
        if key == "pz":
            self.db.execute("UPDATE reminders SET active=? WHERE id=? AND user_id=?", (0 if r["active"] else 1, rid, uid))
            self.db.commit()
            return self.show_item(uid, chat, mid, rid, lg)
        if key == "rm":
            return self.tg.edit(chat, mid, tr(lg, "del_q", title=E(r["title"])), kb([[(tr(lg, "yes_del"), f"rmy:{rid}"), (tr(lg, "no"), f"ls:{rid}")], home_row(lg)]))
        self.db.execute("DELETE FROM occ WHERE reminder_id=? AND user_id=?", (rid, uid))
        self.db.execute("DELETE FROM reminders WHERE id=? AND user_id=?", (rid, uid))
        self.db.commit()
        self.tg.edit(chat, mid, tr(lg, "deleted"), kb([[(tr(lg, "back"), "lst"), (tr(lg, "btn_home"), "home")]]))

    def show_soon(self, uid, chat, u, lg, mid=None):
        now = self.now()
        items = []
        for r in self.db.execute("SELECT * FROM reminders WHERE user_id=? AND active=1", (uid,)).fetchall():
            ts = L.next_fire(self.db, uid, r, now)
            if ts and ts - now <= 30 * 86400:
                items.append((ts, r))
        over = L.overdue_items(self.db, uid, now)
        if not items and not over:
            return self.panel(uid, chat, mid, tr(lg, "soon_empty"), kb_home(lg))
        head = ([tr(lg, "dg_over")] + [f"🔴 <b>{o['due'][8:]}.{o['due'][5:7]}</b> · {E(o['title'])}" for o in over] + [""]) if over else []
        lines = [f"🔔 <b>{self.fmt_ts(u, ts)}</b> · {E(r['title'])}" + (f" · {E(r['amount'])}" if r["amount"] else "") for ts, r in sorted(items, key=lambda x: x[0])]
        self.panel(uid, chat, mid, tr(lg, "soon_title") + "\n\n" + "\n".join(head + lines), kb_home(lg))

    def show_settings(self, uid, chat, u, mid=None):
        lg = u["lang"] or "uz"
        rep = tr(lg, "rep_off") if not u["repeat_h"] else tr(lg, "rep_m") if u["repeat_h"] < 0.1 else tr(lg, "rep_val", h=f"{u['repeat_h']:g}")
        dg = tr(lg, "dg_off") if u["digest_hour"] is None else f"{u['digest_hour']:02d}:00"
        q = tr(lg, "q_off") if u["quiet_start"] == u["quiet_end"] else tr(lg, "q_range", a=f"{u['quiet_start']:02d}", b=f"{u['quiet_end']:02d}")
        text = tr(lg, "settings", lang=LANG_NAME[lg], tz=f"{u['tz']:g}", rep=rep, q=q, dg=dg)
        markup = kb([[("🇺🇿 UZB", "lg:uz"), ("🇷🇺 РУС", "lg:ru")], [(tr(lg, "tz5"), "tz:5"), (tr(lg, "tz3"), "tz:3")],
                     [(tr(lg, "rep_btn_off"), "rp:0"), (tr(lg, "rep_btn_m"), "rp:m")] + [(tr(lg, "rep_btn", h=h), f"rp:{h}") for h in (1, 3, 6)], [(tr(lg, "dg_btn_off"), "dg:off")] + [(tr(lg, "dg_btn", h=f"{h:02d}"), f"dg:{h}") for h in (7, 8, 9)], [(tr(lg, "q_btn_off"), "qh:off")] + [(f"🌙 {a}–{e:02d}", f"qh:{a}") for a, e in ((21, 6), (22, 7), (23, 8))], [(tr(lg, "sound_btn"), "snd"), (tr(lg, "bg_btn"), "bg")], home_row(lg)])
        self.panel(uid, chat, mid, text, markup)

    # ---------- цикл ----------
    def send_digests(self, now):
        for u in self.db.execute("SELECT * FROM users WHERE digest_hour IS NOT NULL AND lang IS NOT NULL").fetchall():
            loc = L.local_dt(u, now)
            if loc.hour < u["digest_hour"] or u["digest_date"] == loc.date().isoformat():
                continue
            lg, uid = u["lang"], u["user_id"]
            items = L.digest_items(self.db, uid, now)
            L.set_user(self.db, uid, digest_date=loc.date().isoformat())  # кунига 1 марта
            if u["digest_mid"]:
                self.tg.delete(u["chat_id"], u["digest_mid"])
            mid = None
            if items:
                lines = [tr(lg, "dg_title")]
                for head, kind in (("dg_over", "over"), ("dg_today", "today"), ("dg_soon", "soon")):
                    part = [f"{d:%d.%m} · {E(t)}" + (f" · {E(a)}" if a else "") for d, t, a, k in items if k == kind][:15]
                    if part:
                        lines += ["", tr(lg, head)] + part
                r = self.tg.send(u["chat_id"], "\n".join(lines), kb_home(lg))
                mid = ((r or {}).get("result") or {}).get("message_id")
            L.set_user(self.db, uid, digest_mid=mid)

    def deliver_feedback(self):
        """Хатларни асосчига юборади (юборилмаганини кейинроқ қайта уринади). Юборувчи кимлиги КЎРСАТИЛМАЙДИ."""
        if not self.admin_chat:
            return
        for f in L.unsent_feedback(self.db):
            try:
                self.tg.send(self.admin_chat, f"📩 <b>Fikr #{f['id']}</b>\n\n{E(f['text'])}")
                L.mark_feedback_sent(self.db, f["id"])
            except Exception as e:
                print("хат юборилмади:", type(e).__name__, flush=True)
                return

    def tick(self):
        now = self.now()
        self.deliver_feedback()
        L.sync(self.db, now)
        try:
            self.send_digests(now)
        except Exception as e:
            print("хулоса хатоси:", type(e).__name__, flush=True)
        for x in L.pop_due(self.db, now):
            try:
                r = self.tg.send(x["chat_id"], card(x), action_kb(x["oid"], x.get("lang") or "uz"))
                if x.get("card_mid"):  # жавобсиз такрорий эслатмалар чатда тўпланмасин: эскиси ўчади
                    self.tg.delete(x["chat_id"], x["card_mid"])
                L.set_card(self.db, x["oid"], ((r or {}).get("result") or {}).get("message_id"))
            except Exception as e:
                print("юбориб бўлмади:", type(e).__name__, flush=True)


def poll(app, conn, offset, timeout=25):
    """Telegram'дан янгиликларни олиб ишлайди; янги offset қайтаради."""
    for up in app.tg.call("getUpdates", offset=offset, timeout=timeout, allowed_updates=["message", "callback_query"]).get("result", []):
        offset = up["update_id"] + 1
        if app.verbose:
            print(time.strftime("%H:%M:%S"), "хабар келди:", "тугма" if "callback_query" in up else "матн", flush=True)
        try:
            if "message" in up:
                app.on_message(up["message"])
            elif "callback_query" in up:
                app.on_callback(up["callback_query"])
        except Exception as e:  # битта хато ботни тўхтатмайди
            fr = traceback.extract_tb(e.__traceback__)[-1]
            app.errors.append(f"{type(e).__name__}: {e} ({fr.name}:{fr.lineno})")
            print("ИШЛОВ ХАТОСИ:", type(e).__name__, e, "— қатор", fr.lineno, fr.name, flush=True)
    conn.execute("INSERT INTO meta(k,v) VALUES('offset',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (str(offset),))
    conn.commit()
    app.tick()
    return offset


def run():
    conn = L.connect(DB_PATH)
    app = App(conn, Tg(os.environ["TELEGRAM_BOT_TOKEN"]))
    app.verbose = True
    try:
        print("Бот ишга тушди: @" + app.tg.call("getMe")["result"]["username"], flush=True)
    except Exception as e:
        raise SystemExit(f"Токен нотўғри ёки интернет йўқ ({type(e).__name__}). Токенни текширинг.")
    row = conn.execute("SELECT v FROM meta WHERE k='offset'").fetchone()
    offset = int(row["v"]) if row else 0
    while True:
        try:
            offset = poll(app, conn, offset)
        except Exception as e:
            print("тармоқ хатоси:", type(e).__name__, flush=True)
            time.sleep(5)


if __name__ == "__main__":
    run()
