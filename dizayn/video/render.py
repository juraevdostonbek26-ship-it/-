"""DOJU видео қўлланма (тик 1080×1920, 30 fps): ҳақиқий веб ойна скриншотлари + анимация + субтитр + мусиқа/овоз эффектлари.
Ишга тушириш: python3 render.py uz  |  python3 render.py ru   (олдин: python3 capture.py <тил>; python3 botmock.py)"""
import json, math, os, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "shots")
OUT = os.path.join(HERE, "out")
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
W, H, FPS = 1080, 1920, 30
CARD_W = 760; CARD_H = round(CARD_W * 1920 / 1080); CARD_X = (W - CARD_W) // 2; CARD_Y = 120
GOLD = (240, 190, 100); NAVY = (14, 36, 48)
FD = "/usr/share/fonts/opentype/inter/"
font = lambda name, size: ImageFont.truetype(FD + name, size)

# (кадр, давомийлиги, сарлавҳа калити)
TIMELINE = [("home", 4.2, "c1"), ("new_empty", 3.2, "c2"), ("new_t2", 3.4, "c3"), ("new_day", 3.4, "c4"), ("new_time", 3.4, "c5"),
            ("new_amount", 3.4, "c6"), ("saved", 3.4, "c7"), ("later", 3.2, "c8"), ("done", 3.2, "c9"), ("list", 3.4, "c10"),
            ("edit_bottom", 3.6, "c11"), ("set_rep", 3.4, "c12"), ("set_bottom", 3.6, "c13"), ("bot", 5.0, "c14")]
INTRO, END = 4.0, 4.5
XFADE = 0.38

CAP = {
    "uz": {"c1": "Bugungi to'lov va ishlaringiz bir joyda", "c2": "Yangi eslatma: «Yangi» tugmasi", "c3": "Nomini yozing",
           "c4": "Qachon eslatay: masalan, har oyning 5-kuni", "c5": "Soatlarni tanlang: bir nechta bo'ladi", "c6": "Summani yozing va saqlang",
           "c7": "Tayyor! Vaqti kelganda bot eslatadi", "c8": "«Keyinroq»: keyinga qoldiring", "c9": "«Bajarildi»: ish tugadi",
           "c10": "Hamma eslatmalar bitta ro'yxatda", "c11": "Tahrirlang, to'xtating yoki o'chiring", "c12": "Takror eslatma har 1 daqiqada",
           "c13": "Tinch soatlarni o'zingiz tanlang", "c14": "Hammasi botning ichida ham bor",
           "title": "Video qo'llanma", "tag": "Hech narsani unutmang", "cta": "Botni oching:", "sub": "Eslatma Kotibi"},
    "ru": {"c1": "Платежи и дела на сегодня в одном месте", "c2": "Новое напоминание: кнопка «Новое»", "c3": "Напишите название",
           "c4": "Когда напомнить: например, 5-го числа каждого месяца", "c5": "Выберите время: можно несколько", "c6": "Введите сумму и сохраните",
           "c7": "Готово! В нужное время бот напомнит", "c8": "«Позже»: отложите на потом", "c9": "«Выполнено»: дело сделано",
           "c10": "Все напоминания в одном списке", "c11": "Меняйте, приостанавливайте или удаляйте", "c12": "Повтор напоминания каждую минуту",
           "c13": "Тихие часы выбираете сами", "c14": "Всё это есть и внутри бота",
           "title": "Видео-инструкция", "tag": "Ничего не забывайте", "cta": "Откройте бота:", "sub": "Секретарь-напоминатель"},
}


def ease(x): x = min(1, max(0, x)); return x * x * (3 - 2 * x)
def back(x): x = min(1, max(0, x)); c = 1.70158; return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def rounded_mask(w, h, r):
    m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255); return m


def make_bg():
    y = np.linspace(0, 1, H)[:, None]; x = np.linspace(0, 1, W)[None, :]
    t = np.clip(y * 0.85 + x * 0.15, 0, 1)
    top, bot = np.array([10, 28, 38]), np.array([24, 72, 88])
    g = (top[None, None, :] * (1 - t[..., None]) + bot[None, None, :] * t[..., None])
    return g.astype(np.float32)


def make_pattern():
    """DOJU чизмаси (юмшоқ суратда секин сурилади)."""
    tw, th = 420, 260
    tile = Image.new("RGBA", (tw, th), (0, 0, 0, 0)); d = ImageDraw.Draw(tile); f = font("Inter-ExtraBold.otf", 56)
    for (x, y) in ((100, 70), (310, 200)):
        d.text((x, y), "DOJU", font=f, fill=(190, 225, 230, 34), anchor="mm")
        d.rounded_rectangle((x - 46, y + 38, x + 46, y + 44), 3, fill=(240, 190, 100, 70))
    big = Image.new("RGBA", (W + tw, H + th), (0, 0, 0, 0))
    for i in range(0, W + tw, tw):
        for j in range(0, H + th, th): big.alpha_composite(tile, (i, j))
    return big


def shadow_for(w, h, r):
    pad = 90; im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((pad, pad + 24, pad + w, pad + h + 24), r, fill=(0, 0, 0, 150))
    return im.filter(ImageFilter.GaussianBlur(34)), pad


class Video:
    def __init__(self, lang):
        self.lang = lang; self.cap = CAP[lang]
        self.taps = json.load(open(os.path.join(SHOTS, f"{lang}.json")))
        self.bg = make_bg(); self.pat = make_pattern()
        self.cardmask = rounded_mask(CARD_W, CARD_H, 52)
        self.shadow, self.spad = shadow_for(CARD_W, CARD_H, 52)
        self.avatar = Image.open(os.path.join(ROOT, "dizayn", "avatar_doju.png")).convert("RGBA")
        self.imgs = {}
        for key, _, _ in TIMELINE:
            im = Image.open(os.path.join(SHOTS, f"{lang}_{key}.png")).convert("RGB") if key != "bot" else Image.open(os.path.join(SHOTS, f"{lang}_bot.png")).convert("RGB")
            self.imgs[key] = im.resize((CARD_W, CARD_H), Image.LANCZOS)
        # вақт жадвали
        self.starts, t = [], INTRO
        for key, dur, ck in TIMELINE:
            self.starts.append(t); t += dur
        self.main_end = t; self.total = t + END
        self.cap_cache = {}
        self.header = self._header()

    # ---------- статик қисмлар ----------
    def _header(self):
        im = Image.new("RGBA", (W, 150), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        av = self.avatar.resize((84, 84), Image.LANCZOS); m = rounded_mask(84, 84, 22)
        im.paste(av, (CARD_X, 40), m)
        d.text((CARD_X + 104, 52), "DOJU", font=font("Inter-ExtraBold.otf", 40), fill=(255, 255, 255, 255))
        d.text((CARD_X + 104, 98), f"{self.cap['sub']} · {self.cap['title']}", font=font("Inter-Medium.otf", 26), fill=(190, 225, 230, 230))
        return im

    def caption_img(self, text):
        if text in self.cap_cache: return self.cap_cache[text]
        f = font("Inter-SemiBold.otf", 50); maxw = 880
        words, lines, cur = text.split(), [], ""
        tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        for wd in words:
            t = (cur + " " + wd).strip()
            if tmp.textlength(t, font=f) <= maxw: cur = t
            else: lines.append(cur); cur = wd
        lines.append(cur)
        lh = 66; w = int(max(tmp.textlength(l, font=f) for l in lines)) + 90; h = lh * len(lines) + 54
        im = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        d.rounded_rectangle((10, 10, w + 10, h + 10), 44, fill=(8, 22, 30, 215), outline=(240, 190, 100, 120), width=2)
        for i, l in enumerate(lines):
            d.text(((w + 20) / 2, 10 + 27 + lh * i + lh / 2), l, font=f, fill=(255, 255, 255, 255), anchor="mm")
        self.cap_cache[text] = im; return im

    # ---------- кадр ----------
    def card_at(self, idx, lt, dur):
        """idx-кадр картасининг ичидаги ҳаракат (секин яқинлашиш + босиш нуқтаси)."""
        key = TIMELINE[idx][0]; im = self.imgs[key]
        p = ease(lt / dur); s = 1.0 + 0.05 * p
        tap = self.taps.get(key)
        fx = (tap[0] / 1080) if tap else 0.5; fy = (tap[1] / 1920) if tap else 0.5
        fx = 0.5 + (fx - 0.5) * 0.5; fy = 0.5 + (fy - 0.5) * 0.5
        sw, sh = int(CARD_W * s), int(CARD_H * s)
        sc = im.resize((sw, sh), Image.BILINEAR)
        left, top = int((sw - CARD_W) * fx), int((sh - CARD_H) * fy)
        view = sc.crop((left, top, left + CARD_W, top + CARD_H)).convert("RGBA")
        if tap and 0.45 <= lt <= 1.7:  # босиш белгиси: кенгаювчи ҳалқа
            tx = tap[0] * CARD_W / 1080 * s - left; ty = tap[1] * CARD_H / 1920 * s - top
            q = (lt - 0.45) / 1.25; ov = Image.new("RGBA", view.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
            r = 18 + 70 * ease(q); a = int(230 * (1 - q))
            d.ellipse((tx - r, ty - r, tx + r, ty + r), outline=GOLD + (a,), width=6)
            d.ellipse((tx - 16, ty - 16, tx + 16, ty + 16), fill=(255, 255, 255, int(220 * (1 - q * 0.6))))
            view.alpha_composite(ov)
        return view

    def frame(self, t):
        bgx, bgy = int((t * 14) % 420), int((t * 8) % 260)
        base = Image.fromarray(self.bg.astype(np.uint8), "RGB").convert("RGBA")
        base.alpha_composite(self.pat.crop((bgx, bgy, bgx + W, bgy + H)))
        if t < INTRO: return self.intro(base, t)
        if t >= self.main_end:
            e = self.end(base.copy(), t - self.main_end)
            if t - self.main_end < 0.45:
                last = self.frame(self.main_end - 0.02)
                return Image.blend(last, e, ease((t - self.main_end) / 0.45))
            return e
        # асосий қисм
        idx = max(i for i, s in enumerate(self.starts) if s <= t); lt = t - self.starts[idx]; dur = TIMELINE[idx][1]
        enter = ease((t - INTRO) / 0.7)  # биринчи кўриниш: юқорига сузиб чиқиш
        card = self.card_at(idx, lt, dur)
        if idx > 0 and lt < XFADE:
            pidx = idx - 1; prev = self.card_at(pidx, TIMELINE[pidx][1] - 0.05 + lt, TIMELINE[pidx][1])
            card = Image.blend(prev, card, ease(lt / XFADE))
        card.putalpha(self.cardmask)
        oy = int((1 - enter) * 160); ca = enter
        base.alpha_composite(self.shadow, (CARD_X - self.spad, CARD_Y - self.spad + oy))
        if ca < 1: card.putalpha(card.getchannel("A").point(lambda v: int(v * ca)))
        base.alpha_composite(card, (CARD_X, CARD_Y + oy))
        # сарлавҳа
        # субтитр
        cap = self.caption_img(self.cap[TIMELINE[idx][2]])
        cin, cout = ease(lt / 0.45), ease((dur - lt) / 0.3)
        a = min(cin, cout, 1.0)
        if a > 0:
            c = cap.copy(); c.putalpha(c.getchannel("A").point(lambda v: int(v * a)))
            base.alpha_composite(c, ((W - c.width) // 2, CARD_Y + CARD_H + 40 + int((1 - cin) * 36)))
        # прогресс чизиғи
        prog = (t - INTRO) / (self.main_end - INTRO); d = ImageDraw.Draw(base)
        d.rounded_rectangle((CARD_X, 1862, CARD_X + CARD_W, 1872), 5, fill=(255, 255, 255, 40))
        d.rounded_rectangle((CARD_X, 1862, CARD_X + int(CARD_W * prog), 1872), 5, fill=GOLD + (255,))
        return base.convert("RGB")

    def intro(self, base, t):
        d = ImageDraw.Draw(base)
        s = back(t / 0.9); size = int(420 * max(0.01, s))
        av = self.avatar.resize((size, size), Image.LANCZOS); m = rounded_mask(size, size, int(size * 0.24))
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ImageDraw.Draw(glow).ellipse((W / 2 - 420, 640 - 420, W / 2 + 420, 640 + 420), fill=(47, 107, 255, int(60 * ease(t / 1.0))))
        base.alpha_composite(glow.filter(ImageFilter.GaussianBlur(120)))
        base.paste(av, ((W - size) // 2, 640 - size // 2), m)
        a = ease((t - 0.7) / 0.6)
        tx = Image.new("RGBA", (W, 520), (0, 0, 0, 0)); td = ImageDraw.Draw(tx)
        td.text((W / 2, 70), "DOJU", font=font("Inter-Black.otf", 190), fill=(255, 255, 255, int(255 * a)), anchor="mm")
        td.rounded_rectangle((W / 2 - 150, 190, W / 2 + 150, 202), 6, fill=(240, 190, 100, int(255 * a)))
        td.text((W / 2, 280), self.cap["sub"], font=font("Inter-SemiBold.otf", 58), fill=(190, 225, 230, int(255 * ease((t - 1.0) / 0.6))), anchor="mm")
        td.text((W / 2, 370), self.cap["tag"], font=font("Inter-Medium.otf", 46), fill=(255, 255, 255, int(220 * ease((t - 1.5) / 0.6))), anchor="mm")
        base.alpha_composite(tx, (0, 1000))
        out = ease((INTRO - t) / 0.4)  # охирида сўниш
        fade = Image.new("RGBA", (W, H), NAVY + (int(255 * (1 - out)),)); base.alpha_composite(fade)
        return base.convert("RGB")

    def end(self, base, t):
        a = ease(t / 0.6); s = back(t / 0.9)
        size = int(360 * max(0.01, s)); av = self.avatar.resize((size, size), Image.LANCZOS); m = rounded_mask(size, size, int(size * 0.24))
        base.paste(av, ((W - size) // 2, 520 - size // 2), m)
        tx = Image.new("RGBA", (W, 760), (0, 0, 0, 0)); td = ImageDraw.Draw(tx)
        td.text((W / 2, 60), "DOJU", font=font("Inter-Black.otf", 170), fill=(255, 255, 255, int(255 * a)), anchor="mm")
        td.text((W / 2, 200), self.cap["cta"], font=font("Inter-Medium.otf", 50), fill=(190, 225, 230, int(255 * ease((t - 0.5) / 0.5))), anchor="mm")
        pa = int(255 * ease((t - 0.8) / 0.5)); td.rounded_rectangle((90, 270, W - 90, 410), 70, fill=(226, 48, 66, pa))
        td.text((W / 2, 340), "@eslatma_Kotibi_bot", font=font("Inter-ExtraBold.otf", 64), fill=(255, 255, 255, pa), anchor="mm")
        td.text((W / 2, 480), "t.me/eslatma_Kotibi_bot", font=font("Inter-Medium.otf", 46), fill=(190, 225, 230, int(255 * ease((t - 1.1) / 0.5))), anchor="mm")
        base.alpha_composite(tx, (0, 800))
        return base.convert("RGB")

    # ---------- овоз ----------
    def audio(self, path):
        sr = 44100; n = int(self.total * sr); L = np.zeros(n, np.float32); R = np.zeros(n, np.float32)
        tt = np.arange(n) / sr
        bar = 60 / 72 * 4
        chords = [(220.00, 261.63, 329.63), (174.61, 220.00, 261.63), (261.63, 329.63, 392.00), (196.00, 246.94, 293.66)]
        for i in range(int(self.total / bar) + 2):
            f0 = chords[i % 4]; s0 = int(i * bar * sr); s1 = min(n, int((i + 1) * bar * sr + 0.6 * sr))
            if s0 >= n: break
            seg = np.arange(s1 - s0) / sr
            env = np.minimum(1, seg / 0.9) * np.exp(-np.maximum(0, seg - bar) * 5)
            pad = sum(np.sin(2 * math.pi * f * seg) + 0.35 * np.sin(2 * math.pi * 2 * f * seg + 0.3) + 0.12 * np.sin(2 * math.pi * 3 * f * seg) for f in f0 for _ in (0,)) * 0.055 * env
            pad += np.sin(2 * math.pi * (f0[0] / 2) * seg) * 0.07 * env
            L[s0:s1] += pad; R[s0:s1] += pad
            for k in range(8):  # юмшоқ арпеджио (пастдан юқорига)
                note = f0[k % 3] * (2 if k >= 3 else 1) * (2 if k == 7 else 1); st = s0 + int(k * bar / 8 * sr)
                if st >= n: break
                e = min(n, st + int(0.7 * sr)); lt = np.arange(e - st) / sr
                tone = np.sin(2 * math.pi * note * lt) * np.exp(-lt * 6) * 0.05 * (0.8 + 0.2 * (k % 2))
                (L if k % 2 == 0 else R)[st:e] += tone; (R if k % 2 == 0 else L)[st:e] += tone * 0.45
        def blip(at, freq, dur=0.12, vol=0.09):
            s0 = int(at * sr); e = min(n, s0 + int(dur * sr))
            if s0 >= n: return
            lt = np.arange(e - s0) / sr; tone = np.sin(2 * math.pi * freq * lt) * np.exp(-lt * 38) * vol
            L[s0:e] += tone; R[s0:e] += tone
        def swoosh(at, dur=0.35, vol=0.05):
            s0 = int(at * sr); e = min(n, s0 + int(dur * sr))
            if s0 >= n: return
            rng = np.random.default_rng(int(at * 100)); noise = rng.standard_normal(e - s0).astype(np.float32)
            lt = np.arange(e - s0) / sr; env = np.sin(math.pi * np.clip(lt / dur, 0, 1)) ** 2
            k = np.ones(40) / 40; noise = np.convolve(noise, k, mode="same")  # юмшатиш (паст частота)
            L[s0:e] += noise * env * vol * 4; R[s0:e] += noise * env * vol * 4
        for i, (key, dur, ck) in enumerate(TIMELINE):
            st = self.starts[i]
            if i > 0: swoosh(st - 0.05)
            tap = self.taps.get(key)
            if tap: blip(st + 0.5, 1046.5 if key in ("saved", "done") else 784.0)
            if key in ("saved", "done"): blip(st + 0.62, 1568.0, 0.4, 0.07)  # «дин»
        swoosh(INTRO - 0.4, 0.5, 0.06); swoosh(self.main_end - 0.1, 0.5, 0.06)
        for (at, fr) in ((0.5, 523.25), (0.62, 659.25), (0.74, 783.99), (0.9, 1046.5)): blip(at, fr, 0.5, 0.06)
        fade = np.minimum(1, tt / 1.5) * np.minimum(1, (self.total - tt) / 2.5)
        L *= fade; R *= fade
        peak = max(np.abs(L).max(), np.abs(R).max(), 1e-6); g = 0.55 / peak; L *= g; R *= g
        pcm = (np.stack([L, R], 1) * 32767).astype("<i2")
        with wave.open(path, "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())


def main(lang, limit=None, preview=False):
    os.makedirs(OUT, exist_ok=True)
    v = Video(lang); wav = os.path.join(OUT, f"{lang}.wav"); v.audio(wav)
    total = v.total if not limit else limit
    out = os.path.join(OUT, f"doju_{lang}{'_preview' if limit else ''}.mp4")
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav, "-t", f"{total:.2f}",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(total * FPS)
    for i in range(n):
        p.stdin.write(np.asarray(v.frame(i / FPS), dtype=np.uint8).tobytes())
        if i % 150 == 0: print(f"{lang}: {i}/{n}", flush=True)
    p.stdin.close(); p.wait(); print("tayyor:", out, f"{v.total:.1f}s")


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else None)
