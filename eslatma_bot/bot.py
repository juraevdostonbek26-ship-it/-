"""Telegram бот: кўп фойдаланувчили эслатма котиби. Фақат стандарт кутубхона."""
import html, json, os, time, urllib.request
from collections import defaultdict, deque
from datetime import timedelta

import logic as L

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db"))
WD = ["Душанба", "Сешанба", "Чоршанба", "Пайшанба", "Жума", "Шанба", "Якшанба"]
FREQ = {"monthly": "🔁 Ҳар ой", "weekly": "📆 Ҳар ҳафта", "once": "1️⃣ Бир марта"}
TEMPLATES = {"ar": "🏠 Аренда", "oy": "👥 Ходимлар ойлиги", "so": "🧾 Солиқ", "wf": "📶 Интернет / WiFi", "cr": "💻 CRM", "ko": "💡 Коммунал"}
MENU = {"➕ Янги эслатма": "add", "📋 Эслатмаларим": "list", "📅 Яқин кунлар": "soon", "⚙️ Созламалар": "set"}
E = html.escape


def kb(rows):
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}


MAIN_KB = {"keyboard": [[{"text": "➕ Янги эслатма"}, {"text": "📋 Эслатмаларим"}], [{"text": "📅 Яқин кунлар"}, {"text": "⚙️ Созламалар"}]], "resize_keyboard": True, "is_persistent": True}


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
            return self.call("editMessageText", **p)
        except Exception:
            return None


# ---------- матн ва тугмалар ----------
def card(title, due, days_left, amount="", sent=0):
    if days_left < 0:
        state = f"🔴 Муддати <b>{-days_left} кун</b> ўтган"
    elif days_left == 0:
        state = "🟠 Муддат: <b>бугун</b>"
    else:
        state = f"🟡 Муддатга <b>{days_left} кун</b> қолди"
    s = f"🔔 <b>{E(title)}</b>\n{state}\n📅 {due[8:]}.{due[5:7]}.{due[:4]}"
    if amount:
        s += f"\n💰 {E(amount)}"
    return s + ("\n↻ такрорий эслатма" if sent else "")


def action_kb(oid):
    return kb([[("⏰ Кейинрок", f"sn:{oid}"), ("✅ Бажарилди", f"dn:{oid}")]])


def describe(r):
    when = {"monthly": f"ҳар ойнинг {r['day']}-санаси", "weekly": f"ҳар {WD[r['day']].lower()}", "once": f"{r['date']}"}[r["freq"]]
    extra = f", {r['lead_days']} кун олдин" if r["lead_days"] else ""
    return f"{E(r['title'])} — {when}, {r['hhmm']}{extra}" + (f" · {E(r['amount'])}" if r["amount"] else "") + ("" if r["active"] else " ⏸")


def ask(step, d):
    """(матн, тугмалар) — ҳар қадам учун савол."""
    if step == "title":
        return "➕ <b>Янги эслатма</b>\nНимани эслатай? Шаблонни танланг ёки номини ёзинг:", kb([[(TEMPLATES[a], f"tpl:{a}"), (TEMPLATES[b], f"tpl:{b}")] for a, b in (("ar", "oy"), ("so", "wf"), ("cr", "ko"))])
    if step == "freq":
        return f"<b>{E(d['title'])}</b>\nҚанчалик тез-тез?", kb([[(v, f"fr:{k}")] for k, v in FREQ.items()])
    if step == "day":
        if d["freq"] == "weekly":
            return "Ҳафтанинг қайси куни?", kb([[(WD[i], f"wd:{i}") for i in (0, 1, 2, 3)], [(WD[i], f"wd:{i}") for i in (4, 5, 6)]])
        return "Ойнинг неча санаси?\nТугмани босинг ёки рақам ёзинг (1–31):", kb([[(str(n), f"dy:{n}") for n in (1, 5, 10, 15)], [(str(n), f"dy:{n}") for n in (20, 25, 30)], [("Ой охири", "dy:31")]])
    if step == "date":
        return "Санани ёзинг: <code>05.11.2026</code>", None
    if step == "time":
        return "Соат нечада эслатай?\nТугмани босинг ёки ёзинг (масалан 8:30):", kb([[(t, f"tm:{t}") for t in ("08:00", "09:00", "12:00")], [(t, f"tm:{t}") for t in ("15:00", "18:00")]])
    if step == "lead":
        return "Олдиндан огоҳлантирайми?", kb([[("Ўша куни", "ld:0"), ("1 кун олдин", "ld:1")], [("3 кун олдин", "ld:3"), ("7 кун олдин", "ld:7")]])
    if step == "amount":
        return "Сумма ёки изоҳ ёзинг (масалан <code>5 000 000</code>).\nКерак бўлмаса — ўтказиб юборинг:", kb([[("⏭ Ўтказиш", "am:skip")]])
    if step == "snooze_custom":
        return "Неча соатдан кейин эслатай? Рақам ёзинг (масалан <code>2</code> ёки <code>0.5</code>):", None


def next_step(d):
    if "title" not in d:
        return "title"
    if "freq" not in d:
        return "freq"
    if d["freq"] == "once" and "date" not in d:
        return "date"
    if d["freq"] != "once" and "day" not in d:
        return "day"
    for k, s in (("hhmm", "time"), ("lead", "lead"), ("amount", "amount")):
        if k not in d:
            return s
    return None


def snooze_kb(oid):
    return kb([[(f"{h} соат", f"sz:{oid}:{h}") for h in ("1", "2", "3")], [(f"{h} соат", f"sz:{oid}:{h}") for h in ("6", "12")] + [("🌅 Эртага", f"sz:{oid}:t")], [("✍️ Ўзим киритаман", f"sz:{oid}:c")]])


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
        return len(q) > 20

    def step(self, uid, chat, d):
        s = next_step(d)
        if s is None:
            rid = L.add_reminder(self.db, uid, d)
            L.clear_conv(self.db, uid)
            if rid is None:
                return self.tg.send(chat, f"Лимит: {L.MAX_REMINDERS} та эслатмадан ортиқ бўлмайди. Керак бўлмаганини ўчиринг.", MAIN_KB)
            L.sync(self.db, self.now())
            r = L.own_reminder(self.db, uid, rid)
            nd = L.next_due(r, L.local_dt(L.get_user(self.db, uid), self.now()).date())
            return self.tg.send(chat, f"✅ <b>Сақланди</b>\n{describe(r)}" + (f"\nКейинги муддат: {nd:%d.%m.%Y}" if nd else ""), MAIN_KB)
        L.set_conv(self.db, uid, s, d)
        text, markup = ask(s, d)
        self.tg.send(chat, text, markup)

    def on_message(self, m):
        if m["chat"]["type"] != "private" or "from" not in m:
            return
        uid, chat, text = m["from"]["id"], m["chat"]["id"], (m.get("text") or "").strip()
        if self.limited(uid):
            return
        u = L.ensure_user(self.db, uid, chat)
        cmd = text.split("@")[0].split()[0].lower() if text.startswith("/") else MENU.get(text, "")
        cmd = cmd.lstrip("/")
        if cmd == "start":
            L.clear_conv(self.db, uid)
            return self.tg.send(chat, "👋 <b>Салом! Мен — шахсий эслатма котибингизман.</b>\n\nТўлов, ойлик, солиқ, учрашув — ҳаммасини бир марта ёзиб қўйинг, мен вақтида эслатаман. Бажармагунча тинч қўймайман 😉\n\n🔒 Сизнинг маълумотингизни фақат ўзингиз кўрасиз.\n\nБошлаш учун: <b>➕ Янги эслатма</b>", MAIN_KB)
        if cmd == "add":
            L.set_conv(self.db, uid, "title", {})
            t, k = ask("title", {})
            return self.tg.send(chat, t, k)
        if cmd == "list":
            return self.show_list(uid, chat)
        if cmd == "soon":
            return self.show_soon(uid, chat, u)
        if cmd == "set":
            return self.show_settings(chat, u)
        if cmd == "cancel":
            L.clear_conv(self.db, uid)
            return self.tg.send(chat, "Бекор қилинди.", MAIN_KB)
        if cmd in ("privacy", "help"):
            return self.tg.send(chat, "🔒 <b>Махфийлик</b>\n• Эслатмаларингизни фақат сиз кўрасиз — бошқа фойдаланувчи улардан хабар топа олмайди.\n• Бот гуруҳда ишламайди, фақат шахсий чатда.\n• Ҳамма маълумотни ўчириш: /deleteme\n\nКомандалар: /add /list /soon /cancel /deleteme")
        if cmd == "deleteme":
            return self.tg.send(chat, "⚠️ Барча эслатма ва созламаларингиз <b>бутунлай ўчади</b>. Давом этамизми?", kb([[("🗑 Ҳа, ўчир", "del:yes"), ("Йўқ", "del:no")]]))
        step, d = L.get_conv(self.db, uid)
        if step is None:
            return self.tg.send(chat, "Менюдан танланг 👇", MAIN_KB)
        self.on_answer(uid, chat, step, d, text)

    def on_answer(self, uid, chat, step, d, text, now=None):
        now = now or self.now()
        u = L.get_user(self.db, uid)
        today = L.local_dt(u, now).date()
        if step == "title":
            v = L.clean(text, 80)
            if not v:
                return self.tg.send(chat, "Ном ёзинг.")
            d["title"] = v
        elif step == "day":
            v = L.parse_int(text, 1, 31)
            if v is None:
                return self.tg.send(chat, "1 дан 31 гача рақам ёзинг.")
            d["day"] = v
        elif step == "date":
            v = L.parse_date(text, today)
            if v is None:
                return self.tg.send(chat, "Сана нотўғри ёки ўтиб кетган. Мисол: <code>05.11.2026</code>")
            d["date"] = v.isoformat()
        elif step == "time":
            v = L.parse_time(text)
            if v is None:
                return self.tg.send(chat, "Вақтни шундай ёзинг: <code>8:30</code>")
            d["hhmm"] = v
        elif step == "amount":
            d["amount"] = L.clean(text, 40)
        elif step == "snooze_custom":
            h = L.parse_hours(text)
            if h is None:
                return self.tg.send(chat, "0.1 дан 72 гача рақам ёзинг (соат).")
            L.clear_conv(self.db, uid)
            if L.snooze(self.db, uid, d["oid"], now, hours=h) is None:
                return self.tg.send(chat, "Бу эслатма аллақачон ёпилган.")
            return self.tg.send(chat, f"⏰ Яхши, <b>{h:g} соатдан</b> кейин эслатаман.", MAIN_KB)
        else:
            return self.tg.send(chat, "Юқоридаги тугмалардан бирини босинг 👆")
        self.step(uid, chat, d)

    def on_callback(self, c):
        uid, msg = c["from"]["id"], c.get("message")
        if not msg or msg["chat"]["type"] != "private" or self.limited(uid):
            return self.tg.call("answerCallbackQuery", callback_query_id=c["id"])
        chat, mid, data = msg["chat"]["id"], msg["message_id"], c.get("data", "")
        u = L.ensure_user(self.db, uid, chat)
        now = self.now()
        self.tg.call("answerCallbackQuery", callback_query_id=c["id"])
        key, _, arg = data.partition(":")
        step, d = L.get_conv(self.db, uid)
        if key in ("dn", "sn", "sz") and arg.split(":")[0].isdigit():
            oid = int(arg.split(":")[0])
            o = L.own_occ(self.db, uid, oid)  # ЭГАЛИК текшируви
            if not o:
                return
            if key == "dn":
                L.mark_done(self.db, uid, oid)
                r = L.own_reminder(self.db, uid, o["reminder_id"])
                return self.tg.edit(chat, mid, f"✅ <s>{E(r['title'])}</s>\nБажарилди. Қойил! 👏")
            if o["status"] != "pending":
                return self.tg.edit(chat, mid, "Бу эслатма ёпилган.")
            if key == "sn":
                return self.tg.edit(chat, mid, "⏰ <b>Қачон қайта эслатай?</b>", snooze_kb(oid))
            val = arg.split(":")[1]
            if val == "c":
                L.set_conv(self.db, uid, "snooze_custom", {"oid": oid})
                return self.tg.send(chat, *ask("snooze_custom", {}))
            L.snooze(self.db, uid, oid, now, hours=None if val == "t" else float(val), tomorrow=val == "t")
            return self.tg.edit(chat, mid, "⏰ Хўп, " + ("эртага" if val == "t" else f"<b>{val} соатдан</b> кейин") + " эслатаман.")
        if key == "tpl" and arg in TEMPLATES:
            return self.step(uid, chat, {"title": TEMPLATES[arg].split(" ", 1)[1], "freq": "monthly"})
        if step is None and key in ("fr", "wd", "dy", "tm", "ld", "am"):
            return
        if key == "fr" and arg in FREQ and step == "freq":
            d["freq"] = arg
        elif key == "wd" and step == "day" and (v := L.parse_int(arg, 0, 6)) is not None:
            d["day"] = v
        elif key == "dy" and step == "day" and (v := L.parse_int(arg, 1, 31)) is not None:
            d["day"] = v
        elif key == "tm" and step == "time" and (v := L.parse_time(arg)):
            d["hhmm"] = v
        elif key == "ld" and step == "lead" and (v := L.parse_int(arg, 0, 7)) is not None:
            d["lead"] = v
        elif key == "am" and step == "amount":
            d["amount"] = ""
        elif key == "ls":
            return self.show_item(uid, chat, mid, arg)
        elif key in ("pz", "rm", "rmy"):
            return self.item_action(uid, chat, mid, key, arg)
        elif key == "tz" and (v := L.parse_hours(arg.lstrip("+")) if arg.lstrip("+").replace(".", "").isdigit() else None):
            self.db.execute("UPDATE users SET tz=? WHERE user_id=?", (v, uid)); self.db.commit()
            return self.tg.edit(chat, mid, f"✅ Вақт минтақаси: UTC+{v:g}")
        elif key == "rp" and (v := L.parse_int(arg, 1, 12)):
            self.db.execute("UPDATE users SET repeat_h=? WHERE user_id=?", (v, uid)); self.db.commit()
            return self.tg.edit(chat, mid, f"✅ Жавоб бермасангиз, ҳар <b>{v} соатда</b> эслатаман.")
        elif key == "del":
            if arg == "yes":
                L.delete_user_data(self.db, uid)
                return self.tg.edit(chat, mid, "🗑 Ҳамма маълумотингиз ўчирилди.")
            return self.tg.edit(chat, mid, "Бекор қилинди.")
        else:
            return
        self.step(uid, chat, d)

    # ---------- рўйхатлар ----------
    def show_list(self, uid, chat):
        rows = self.db.execute("SELECT * FROM reminders WHERE user_id=? ORDER BY id", (uid,)).fetchall()
        if not rows:
            return self.tg.send(chat, "Ҳозирча эслатма йўқ. <b>➕ Янги эслатма</b> ни босинг.", MAIN_KB)
        self.tg.send(chat, "📋 <b>Эслатмаларим</b>\nУстига босиб бошқаринг:", kb([[(f"{'⏸ ' if not r['active'] else ''}{r['title']}", f"ls:{r['id']}")] for r in rows]))

    def show_item(self, uid, chat, mid, rid):
        r = L.own_reminder(self.db, uid, int(rid)) if rid.isdigit() else None
        if not r:
            return
        self.tg.edit(chat, mid, describe(r), kb([[("▶️ Давом эттириш" if not r["active"] else "⏸ Тўхтатиш", f"pz:{r['id']}"), ("🗑 Ўчириш", f"rm:{r['id']}")]]))

    def item_action(self, uid, chat, mid, key, rid):
        r = L.own_reminder(self.db, uid, int(rid)) if rid.isdigit() else None
        if not r:
            return
        if key == "pz":
            self.db.execute("UPDATE reminders SET active=? WHERE id=? AND user_id=?", (0 if r["active"] else 1, r["id"], uid)); self.db.commit()
            return self.show_item(uid, chat, mid, rid)
        if key == "rm":
            return self.tg.edit(chat, mid, f"Ўчирайми: <b>{E(r['title'])}</b>?", kb([[("🗑 Ҳа", f"rmy:{r['id']}"), ("Йўқ", f"ls:{r['id']}")]]))
        self.db.execute("DELETE FROM occ WHERE reminder_id=? AND user_id=?", (r["id"], uid))
        self.db.execute("DELETE FROM reminders WHERE id=? AND user_id=?", (r["id"], uid)); self.db.commit()
        self.tg.edit(chat, mid, "🗑 Ўчирилди.")

    def show_soon(self, uid, chat, u):
        today = L.local_dt(u, self.now()).date()
        items = []
        for r in self.db.execute("SELECT * FROM reminders WHERE user_id=? AND active=1", (uid,)):
            nd = L.next_due(r, today)
            if nd and (nd - today).days <= 30:
                items.append((nd, r))
        if not items:
            return self.tg.send(chat, "Яқин 30 кунда эслатма йўқ ✨", MAIN_KB)
        lines = [f"{'🔴' if n == today else '🟡'} <b>{n:%d.%m}</b> · {E(r['title'])}" + (f" · {E(r['amount'])}" if r["amount"] else "") for n, r in sorted(items, key=lambda x: x[0])]
        self.tg.send(chat, "📅 <b>Яқин 30 кун</b>\n\n" + "\n".join(lines), MAIN_KB)

    def show_settings(self, chat, u):
        self.tg.send(chat, f"⚙️ <b>Созламалар</b>\n🌍 Вақт: UTC+{u['tz']:g}\n↻ Такрор: ҳар {u['repeat_h']:g} соат\n🌙 Тинч соатлар: {u['quiet_start']}:00–{u['quiet_end']}:00 (хабар келмайди)\n\n/privacy · /deleteme",
                     kb([[("🇺🇿 +5 Тошкент", "tz:5"), ("+3 Москва", "tz:3"), ("+6", "tz:6")], [("↻ 1 соат", "rp:1"), ("↻ 2", "rp:2"), ("↻ 3", "rp:3"), ("↻ 6", "rp:6")]]))

    # ---------- цикл ----------
    def tick(self):
        now = self.now()
        L.sync(self.db, now)
        for x in L.pop_due(self.db, now):
            try:
                self.tg.send(x["chat_id"], card(x["title"], x["due"], x["days_left"], x["amount"], x["sent_count"]), action_kb(x["oid"]))
            except Exception as e:
                print("юбориб бўлмади:", type(e).__name__, flush=True)


def run():
    conn = L.connect(DB_PATH)
    app = App(conn, Tg(os.environ["TELEGRAM_BOT_TOKEN"]))
    row = conn.execute("SELECT v FROM meta WHERE k='offset'").fetchone()
    offset = int(row["v"]) if row else 0
    while True:
        try:
            for up in app.tg.call("getUpdates", offset=offset, timeout=25, allowed_updates=["message", "callback_query"]).get("result", []):
                offset = up["update_id"] + 1
                try:
                    if "message" in up:
                        app.on_message(up["message"])
                    elif "callback_query" in up:
                        app.on_callback(up["callback_query"])
                except Exception as e:  # битта хато ботни тўхтатмайди; матн логга ёзилмайди
                    print("ишлов хатоси:", type(e).__name__, flush=True)
            conn.execute("INSERT OR REPLACE INTO meta VALUES('offset',?)", (str(offset),)); conn.commit()
            app.tick()
        except Exception as e:
            print("тармоқ хатоси:", type(e).__name__, flush=True)
            time.sleep(5)


if __name__ == "__main__":
    run()
