"""Видонинг охири учун: ботнинг ҳақиқий меню матнлари билан Telegram'га ўхшатиб чизилган экран (ҳақиқий Telegram'ни ёзиб бўлмайди)."""
import base64, glob, os, re, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "eslatma_bot"))
from texts import TXT

AVATAR = base64.b64encode(open(os.path.join(ROOT, "dizayn", "avatar_doju.png"), "rb").read()).decode()


def html(lg):
    t = TXT[lg]
    strip = lambda s: re.sub(r"<[^>]+>", "", s)
    home = strip(t["home"]).split("\n")
    rows = [[t["m_add"], t["m_list"]], [t["m_soon"], t["m_set"]], [t["bg_btn"], t["sound_btn"]], [t["m_fb"]], [t["m_web"]]]
    btn = "".join('<div class="row">' + "".join(f'<div class="b{" web" if r[0] == t["m_web"] else ""}">{c}</div>' for c in r) + "</div>" for r in rows)
    sub = {"uz": "bot", "ru": "бот"}[lg]
    typing = {"uz": "Xabar", "ru": "Сообщение"}[lg]
    return f"""<!doctype html><meta charset=utf-8><style>
*{{box-sizing:border-box;margin:0}} body{{width:432px;height:768px;font:15px Inter,system-ui,sans-serif;color:#fff;overflow:hidden;
background:linear-gradient(180deg,#0e2430,#16404e)}}
.bar{{height:58px;background:#17212b;display:flex;align-items:center;gap:12px;padding:0 14px;border-bottom:1px solid #0e1621}}
.bar img{{width:40px;height:40px;border-radius:50%}} .bar b{{display:block;font-size:16px}} .bar small{{color:#6d7f8f;font-size:12px}}
.wall{{position:absolute;top:58px;bottom:62px;left:0;right:0;padding:16px 12px;
background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='210' height='110'%3E%3Cg fill='%23bee1e6' fill-opacity='.14' font-family='Arial' font-weight='800' font-size='21' text-anchor='middle'%3E%3Ctext x='52' y='36'%3EDOJU%3C/text%3E%3Ctext x='157' y='91'%3EDOJU%3C/text%3E%3C/g%3E%3C/svg%3E")}}
.msg{{background:#182533;border-radius:14px;padding:10px 12px;width:300px;line-height:1.4;box-shadow:0 1px 2px #0005}}
.msg b{{font-weight:700}} .kb{{width:300px;margin-top:4px}} .row{{display:flex;gap:4px;margin-top:4px}}
.b{{flex:1;background:#2b4a5acc;border-radius:9px;padding:10px 6px;text-align:center;font-weight:600;font-size:13.5px;backdrop-filter:blur(4px)}}
.web{{background:#2f6bffcc}}
.in{{position:absolute;left:0;right:0;bottom:0;height:62px;background:#17212b;display:flex;align-items:center;gap:10px;padding:0 12px}}
.menu{{background:#2f6bff;border-radius:20px;padding:9px 16px;font-weight:800;font-size:14px}} .field{{flex:1;color:#6d7f8f}}
</style>
<div class=bar><img src="data:image/png;base64,{AVATAR}"><div><b>DOJU Eslatma Kotibi</b><small>{sub}</small></div></div>
<div class=wall><div class=msg><b>{home[0]}</b><br><br>{home[2] if len(home)>2 else ''}</div><div class=kb>{btn}</div></div>
<div class=in><div class=menu>DOJU</div><div class=field>{typing}</div></div>"""


def render(lang, out_dir):
    from playwright.sync_api import sync_playwright
    ch = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")[0]
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=ch, args=["--no-sandbox"])
        pg = b.new_context(viewport={"width": 432, "height": 768}, device_scale_factor=2.5).new_page()
        pg.set_content(html(lang)); pg.wait_for_timeout(300)
        pg.screenshot(path=os.path.join(out_dir, f"{lang}_bot.png"))
        # «Veb oyna» тугмаси маркази (босиш нуқтаси учун)
        bb = pg.locator(".web").bounding_box(); b.close()
    return [round((bb["x"] + bb["width"] / 2) * 2.5), round((bb["y"] + bb["height"] / 2) * 2.5)]


if __name__ == "__main__":
    import json
    out = os.path.join(os.path.dirname(__file__), "shots")
    for lg in ("uz", "ru"):
        tap = render(lg, out)
        d = json.load(open(os.path.join(out, f"{lg}.json"))); d["bot"] = tap
        json.dump(d, open(os.path.join(out, f"{lg}.json"), "w")); print(lg, tap)
