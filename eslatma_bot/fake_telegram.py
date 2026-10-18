"""Тест учун сохта Telegram Bot API сервери: ҳақиқий қоидаларни текширади (HTML, тугма ҳажми, ўчирилган хабар...)."""
import json, re, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ALLOWED = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "a", "tg-spoiler", "blockquote"}


def html_error(text):
    stack = []
    for m in re.finditer(r"<[^>]*>|<|&[#\w]*;?", text):
        tok = m.group(0)
        if tok.startswith("&"):
            if not re.fullmatch(r"&(lt|gt|amp|quot|#\d+|#x[0-9a-fA-F]+);", tok) and tok != "&":
                return f"Unsupported entity {tok}"
            continue
        t = re.fullmatch(r"<(/?)([a-zA-Z-]+)[^>]*>", tok)
        if not t or t.group(2).lower() not in ALLOWED:
            return f"Unsupported start tag {tok!r}"
        if t.group(1):
            if not stack or stack.pop() != t.group(2).lower():
                return "Can't find end tag corresponding to start tag"
        else:
            stack.append(t.group(2).lower())
    return "Can't find end tag" if stack else None


def markup_error(mk, edit=False):
    if mk is None:
        return None
    if "keyboard" in mk:
        return "reply keyboard can't be used when editing" if edit else None
    rows = mk.get("inline_keyboard")
    if not isinstance(rows, list) or not rows:
        return "bad inline keyboard"
    total = 0
    for row in rows:
        if not row or len(row) > 8:
            return "too many buttons in a row"
        for b in row:
            total += 1
            if not b.get("text"):
                return "button text empty"
            if "url" in b:  # оддий ҳавола тугмаси
                if not str(b["url"]).startswith(("https://", "tg://")):
                    return "BUTTON_URL_INVALID"
                continue
            if "web_app" in b:  # Mini App тугмаси: https манзил керак
                if not str(b["web_app"].get("url", "")).startswith("https://"):
                    return "BUTTON_URL_INVALID"
                continue
            if len(b.get("callback_data", "").encode()) > 64 or "callback_data" not in b:
                return "BUTTON_DATA_INVALID"
    return "too many buttons" if total > 100 else None


class FakeTelegram:
    def __init__(self):
        self.lock = threading.Lock()
        self.chats, self.updates, self.errors, self.toasts, self.harmless = {}, [], [], [], []
        self.uid = 0
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                method = self.path.rsplit("/", 1)[-1]
                with fake.lock:
                    try:
                        res = getattr(fake, "m_" + method)(body)
                        out, code = {"ok": True, "result": res}, 200
                    except ValueError as e:
                        (fake.harmless if "not modified" in str(e) else fake.errors).append((method, str(e)))
                        out, code = {"ok": False, "error_code": 400, "description": "Bad Request: " + str(e)}, 400
                data = json.dumps(out).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()

    # ---- Bot API ----
    def chat(self, cid):
        return self.chats.setdefault(cid, {"msgs": {}, "next": 1, "kbd": None})

    def m_getMe(self, b):
        return {"id": 1, "is_bot": True, "username": "fake_bot"}

    def _media(self, b, kind):
        c = self.chat(b["chat_id"])
        mid = c["next"]; c["next"] += 1
        self.media = getattr(self, "media", []) + [(kind, b.get(kind.replace("send", "").lower()), b.get("caption", ""))]
        c["msgs"][mid] = {"from": "bot", "text": f"[{kind}] {b.get('caption', '')}", "markup": None, "deleted": False}
        return {"message_id": mid}

    def m_sendAudio(self, b):
        if not str(b.get("audio", "")).startswith("https://"):
            raise ValueError("wrong file identifier/HTTP URL specified")
        return self._media(b, "sendAudio")

    def m_sendPhoto(self, b):
        if not str(b.get("photo", "")).startswith("https://"):
            raise ValueError("wrong file identifier/HTTP URL specified")
        return self._media(b, "sendPhoto")

    def m_setChatMenuButton(self, b):
        self.menu_button = b
        return True

    def m_setWebhook(self, b):
        self.webhook = b
        return True

    def m_getUpdates(self, b):
        off = b.get("offset") or 0
        return [u for u in self.updates if u["update_id"] >= off]

    def _check(self, b, edit=False):
        text = b.get("text", "")
        if not text.strip():
            raise ValueError("message text is empty")
        if len(text) > 4096:
            raise ValueError("message is too long")
        if b.get("parse_mode") == "HTML" and (e := html_error(text)):
            raise ValueError("can't parse entities: " + e)
        if e := markup_error(b.get("reply_markup"), edit):
            raise ValueError(e)

    def m_sendMessage(self, b):
        self._check(b)
        c = self.chat(b["chat_id"])
        mid = c["next"]; c["next"] += 1
        mk = b.get("reply_markup")
        c["msgs"][mid] = {"from": "bot", "text": b["text"], "markup": mk if mk and "inline_keyboard" in mk else None, "deleted": False}
        if mk and "keyboard" in mk:
            c["kbd"] = [x["text"] for row in mk["keyboard"] for x in row]
            c["kbd_mid"] = mid
        return {"message_id": mid}

    def m_editMessageText(self, b):
        self._check(b, edit=True)
        m = self.chat(b["chat_id"])["msgs"].get(b["message_id"])
        if not m or m["deleted"] or m["from"] != "bot":
            raise ValueError("message to edit not found")
        mk = b.get("reply_markup")
        if m["text"] == b["text"] and m["markup"] == mk:
            raise ValueError("message is not modified")
        m["text"], m["markup"] = b["text"], mk
        return True

    def m_deleteMessage(self, b):
        m = self.chat(b["chat_id"])["msgs"].get(b["message_id"])
        if not m or m["deleted"]:
            raise ValueError("message to delete not found")
        m["deleted"] = True
        c = self.chat(b["chat_id"])
        if c.get("kbd_mid") == b["message_id"]:  # ҳақиқий Telegram'да кузатилган: ташувчи хабар ўчса, пастки меню ҳам йўқолади
            c["kbd"], c["kbd_mid"] = None, None
        return True

    def m_answerCallbackQuery(self, b):
        if len(b.get("text", "")) > 200:
            raise ValueError("text too long")
        self.toasts.append(b.get("text", ""))
        return True

    # ---- фойдаланувчи ҳаракатлари ----
    def _upd(self, **kw):
        self.uid += 1
        self.updates.append({"update_id": self.uid, **kw})

    def say(self, uid, text):
        with self.lock:
            c = self.chat(uid)
            mid = c["next"]; c["next"] += 1
            c["msgs"][mid] = {"from": "user", "text": text, "markup": None, "deleted": False}
            self._upd(message={"message_id": mid, "chat": {"id": uid, "type": "private"}, "from": {"id": uid}, "text": text})

    def tap_menu(self, uid, label):
        with self.lock:
            kbd = self.chat(uid)["kbd"] or []
        assert label in kbd, f"меню тугмаси йўқ: {label!r}, бор: {kbd}"
        self.say(uid, label)

    def press(self, uid, mid, data):
        with self.lock:
            self._upd(callback_query={"id": f"cq{self.uid}", "from": {"id": uid}, "data": data,
                                      "message": {"message_id": mid, "chat": {"id": uid, "type": "private"}}})

    def buttons(self, uid):
        with self.lock:
            return [(mid, b["text"], b.get("callback_data", "web_app")) for mid, m in sorted(self.chat(uid)["msgs"].items())
                    if not m["deleted"] and m["markup"] for row in m["markup"]["inline_keyboard"] for b in row]

    def click(self, uid, label):
        """Одамдек: экрандаги тугмани матни бўйича босади (энг пастки хабардан қидиради)."""
        found = [x for x in self.buttons(uid) if x[1] == label]
        assert found, f"экранда «{label}» тугмаси йўқ. Бор тугмалар: {[x[1] for x in self.buttons(uid)]}"
        self.press(uid, found[-1][0], found[-1][2])

    def visible(self, uid):
        with self.lock:
            return [(mid, m["from"], m["text"]) for mid, m in sorted(self.chat(uid)["msgs"].items()) if not m["deleted"]]

    def last(self, uid):
        v = [x for x in self.visible(uid) if x[1] == "bot"]
        return v[-1][2] if v else ""
