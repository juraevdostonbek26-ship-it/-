"""Молия директори учун тўлов эслатма боти (Telegram). Фақат стандарт кутубхона."""
import calendar, json, os, time, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone

DIR = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(DIR, "payments.json")
STATE = os.path.join(DIR, "state.json")


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def due_date(p, year, month):
    """Тўлов шу ойда тушадими? Тушса санасини қайтаради."""
    freq = p.get("freq", "monthly")
    if freq == "quarterly" and (month - p.get("month", 1)) % 3:
        return None
    if freq == "yearly" and month != p.get("month", 1):
        return None
    if freq == "once":
        d = date.fromisoformat(p["date"])
        return d if (d.year, d.month) == (year, month) else None
    return date(year, month, min(p["day"], calendar.monthrange(year, month)[1]))


def upcoming(p, today, horizon=45):
    """Яқин келажакдаги (ёки бугунги) муддатлар рўйхати."""
    out, y, m = [], today.year, today.month
    for _ in range(14):
        d = due_date(p, y, m)
        if d and today <= d <= today + timedelta(days=horizon):
            out.append(d)
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def period_key(p, d):
    return f"{p['id']}:{d.isoformat()}"


def todays_reminders(cfg, state, today):
    """Бугун юбориладиган эслатмалар: (payment, due, days_left)."""
    res = []
    for p in cfg["payments"]:
        for d in upcoming(p, today):
            left = (d - today).days
            key = period_key(p, d)
            if key in state["paid"] or left not in p.get("remind_before", [0]):
                continue
            res.append((p, d, left))
    return sorted(res, key=lambda r: r[1])


def fmt(p, d, left):
    when = "БУГУН!" if left == 0 else f"{left} кундан кейин"
    extra = (f" — {p['amount']}" if p.get("amount") else "") + (f"\n   ℹ️ {p['note']}" if p.get("note") else "")
    icon = "🔴" if left == 0 else "🟡"
    return f"{icon} {p['name']}: {d.strftime('%d.%m.%Y')} ({when}){extra}\n   ✅ тўландими: /done {p['id']}_{d.isoformat()}"


class Bot:
    def __init__(self, token):
        self.api = f"https://api.telegram.org/bot{token}/"

    def call(self, method, **params):
        data = urllib.parse.urlencode(params).encode()
        with urllib.request.urlopen(self.api + method, data, timeout=60) as r:
            return json.load(r)

    def send(self, chat, text):
        self.call("sendMessage", chat_id=chat, text=text)


def now_local(cfg):
    return datetime.now(timezone.utc) + timedelta(hours=cfg.get("timezone_offset_hours", 5))


def handle(bot, cfg, state, msg):
    chat = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    today = now_local(cfg).date()
    if text.startswith("/start"):
        if chat not in state["chats"]:
            state["chats"].append(chat)
        bot.send(chat, "Салом! Мен тўлов эслатма ботиман.\n/soon — яқин 14 кун\n/list — барча тўловлар\n/done <код> — тўланди деб белгилаш")
    elif text.startswith("/list"):
        bot.send(chat, "\n".join(f"• {p['name']} — {p['freq']}, {p['day']}-сана (код: {p['id']})" for p in cfg["payments"]))
    elif text.startswith("/soon"):
        rows = sorted((d, p) for p in cfg["payments"] for d in upcoming(p, today, 14))
        bot.send(chat, "\n".join(f"{d:%d.%m} — {p['name']}" + (" ✅" if period_key(p, d) in state["paid"] else "") for d, p in rows) or "Яқин 14 кунда тўлов йўқ")
    elif text.startswith("/done"):
        arg = text.partition(" ")[2].strip()
        if arg:
            state["paid"][arg] = today.isoformat()
            bot.send(chat, f"✅ Белгиланди: {arg}")
        else:
            bot.send(chat, "Мисол: /done arenda_2026-11-05")


def run():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    bot = Bot(token)
    offset = None
    while True:
        cfg = load(CFG, {"payments": []})
        state = load(STATE, {"chats": [], "paid": {}, "last_sent": "", "offset": 0})
        if os.environ.get("CHAT_ID") and int(os.environ["CHAT_ID"]) not in state["chats"]:
            state["chats"].append(int(os.environ["CHAT_ID"]))
        try:
            for u in bot.call("getUpdates", timeout=30, offset=state["offset"]).get("result", []):
                state["offset"] = u["update_id"] + 1
                if "message" in u:
                    handle(bot, cfg, state, u["message"])
            now = now_local(cfg)
            if now.hour >= cfg.get("send_hour", 9) and state["last_sent"] != now.date().isoformat():
                rem = todays_reminders(cfg, state, now.date())
                if rem:
                    text = "📅 Бугунги эслатмалар:\n\n" + "\n\n".join(fmt(*r) for r in rem)
                    for c in state["chats"]:
                        bot.send(c, text)
                state["last_sent"] = now.date().isoformat()
        except Exception as e:  # тармоқ узилса бот тўхтамайди
            print("хато:", e, flush=True)
            time.sleep(10)
        save(STATE, state)


if __name__ == "__main__":
    run()
