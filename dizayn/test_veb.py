"""Веб намунани ҲАҚИҚИЙ браузерда битта-битта босиб текширади (талаб I8). Ишга тушириш: python3 test_veb.py"""
import glob, sys
from playwright.sync_api import sync_playwright

CH = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")[0]
URL = "file://" + __file__.rsplit("/", 1)[0] + "/doju_veb_oyna.html"
res = []

def check(name, cond):
    res.append((name, bool(cond)))
    print(("OK   " if cond else "FAIL ") + name)

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CH, args=["--no-sandbox"])
    pg = b.new_context(viewport={"width": 400, "height": 850}).new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL)
    txt = lambda: pg.inner_text("#view")
    tab = lambda n: pg.click(f'#tabs button[data-tab="{n}"]')

    check("Бугун очилади, 3 та ҳисоблағич", pg.locator(".stat").count() == 3)
    # ---- Бугун: бажарилди / кейинроқ
    n0 = pg.locator('[data-act="done"]').count()
    pg.locator('[data-act="done"]').first.click()
    check("«Бажарилди» босилса камаяди", pg.locator('[data-act="done"]').count() == n0 - 1)
    pg.locator('[data-act="later"]').first.click()
    check("«Кейинроқ» вариантлар очади", pg.locator('[data-act="snz"]').count() == 3)
    pg.locator('[data-act="snz"]').nth(0).click()
    check("Кейинроқ танланса карточка тушади", pg.locator('[data-act="snz"]').count() == 0)
    # ---- Ҳаммаси: ичига кириш, ўзгартириш
    tab("list")
    pg.locator('.card [data-act="open"]').first.click()
    check("Эслатма очилади (таҳрирлаш)", pg.locator("#f-title").count() == 1 and "✏️" in txt())
    check("Ном тўлдирилган", pg.input_value("#f-title") != "")
    pg.fill("#f-title", "Ofis ijarasi YANGI")
    pg.locator('.day[data-v="20"]').click()
    pg.locator('[data-act="time"][data-v="12:00"]').click()
    pg.fill("#f-time", "15:30"); pg.click('[data-act="addtime"]')
    check("Бошқа вақт қўшилди", pg.locator('[data-act="time"][data-v="15:30"].on').count() == 1)
    pg.click('[data-act="save"]')
    tab("list")
    check("Ном ўзгарди", "Ofis ijarasi YANGI" in txt())
    check("Кун ва вақт ўзгарди", "20-kuni" in txt() and "12:00" in txt() and "15:30" in txt())
    # ---- таҳрир: бекор, ўчириш
    pg.locator('.card [data-act="open"]').first.click(); pg.click('[data-act="cancelEdit"]')
    check("Бекор қилиш рўйхатга қайтаради", "hammasi" in txt().lower())
    cnt = pg.locator(".card").count()
    pg.locator('[data-act="del"]').first.click()
    check("Ўчиришда тасдиқ сўрайди", pg.locator('[data-act="delyes"]').count() == 1)
    pg.click('[data-act="delno"]'); check("Тасдиқни бекор қилса қолади", pg.locator(".card").count() == cnt)
    pg.locator('[data-act="del"]').first.click(); pg.click('[data-act="delyes"]')
    check("Ўчирилди", pg.locator(".card").count() == cnt - 1)
    # таҳрир ичидан ўчириш
    pg.locator('.card [data-act="open"]').first.click(); pg.click('[data-act="del"]'); pg.click('[data-act="delyes"]')
    check("Таҳрир ичидан ўчириш", pg.locator(".card").count() == cnt - 2)
    # ---- Янги: ҳар тур
    tab("new")
    pg.click('[data-act="save"]'); check("Бўш номда хато", pg.inner_text("#err") != "")
    pg.fill("#f-title", "Test oylik"); pg.click('[data-act="save"]'); check("Кун танланмаса хато", pg.inner_text("#err") != "")
    pg.locator('.day[data-v="end"]').click(); pg.fill("#f-amt", "1234567")
    check("Сумма гуруҳланди", pg.input_value("#f-amt") == "1 234 567")
    pg.click('[data-act="save"]'); check("Ой охири билан сақланди", "Test oylik" in pg.inner_text("#view") or pg.locator(".card").count() > 0)
    tab("list"); check("Рўйхатда кўринади", "Test oylik" in txt() and "oxirgi" in txt())
    tab("new"); pg.fill("#f-title", "Haftalik"); pg.click('[data-act="freq"][data-v="weekly"]')
    pg.click('[data-act="wd"][data-v="2"]'); pg.click('[data-act="save"]'); tab("list")
    check("Ҳафталик сақланди", "Haftalik" in txt() and "chorshanba" in txt())
    tab("new"); pg.fill("#f-title", "Bir marta"); pg.click('[data-act="freq"][data-v="once"]')
    pg.click('[data-act="save"]'); check("Санасиз хато", pg.inner_text("#err") != "")
    from datetime import date, timedelta
    pg.fill("#f-date", (date.today() + timedelta(days=9)).isoformat()); pg.click('[data-act="save"]'); tab("list")
    check("Бир марталик сақланди", "Bir marta" in txt())
    tab("new"); pg.fill("#f-title", "Kunlik"); pg.click('[data-act="freq"][data-v="daily"]'); pg.click('[data-act="save"]'); tab("list")
    check("Ҳар кунги сақланди", "Kunlik" in txt())
    tab("new"); pg.fill("#f-title", "X"); pg.click('[data-act="freq"][data-v="daily"]')
    for t_ in ("09:00",): pg.click(f'[data-act="time"][data-v="{t_}"]')
    pg.click('[data-act="save"]'); check("Соатсиз хато", pg.inner_text("#err") != "")
    # ---- Созламалар: ҲАР бири
    tab("set")
    pg.click('[data-act="lang"][data-v="ru"]')
    check("Тил РУС: матн ўзгарди", "Настройки" in pg.inner_text("#tabs") and "Язык" in txt())
    check("РУС тугма танланган", pg.locator('[data-act="lang"][data-v="ru"].on').count() == 1)
    tab("home"); check("РУС: Бугун экрани", "Просрочено" in txt() or "Сегодня" in txt())
    tab("list"); check("РУС: рўйхат", "все (" in txt().lower() and "Интернет" in txt())
    tab("new"); check("РУС: янги форма", "О чём напомнить?" in txt()); tab("set")
    pg.click('[data-act="lang"][data-v="uz"]'); check("Тил UZB қайтди", "Sozlamalar" in pg.inner_text("#tabs"))
    c1 = pg.inner_text("#clock"); pg.click('[data-act="tz"][data-v="3"]')
    check("Вақт зонаси +3 танланди", pg.locator('[data-act="tz"][data-v="3"].on').count() == 1 and pg.inner_text("#clock") != c1)
    pg.click('[data-act="tz"][data-v="5"]'); check("Вақт зонаси +5 қайтди", pg.locator('[data-act="tz"][data-v="5"].on').count() == 1)
    for v in ("5", "0", "1"):
        pg.click(f'[data-act="rep"][data-v="{v}"]'); check(f"Такрор {v} танланди", pg.locator(f'[data-act="rep"][data-v="{v}"].on').count() == 1)
    pg.select_option("#qs", "23"); pg.select_option("#qe", "8")
    check("Тинч соат танланди", pg.input_value("#qs") == "23" and pg.input_value("#qe") == "8")
    on0 = pg.locator(".tog.on").count(); pg.click('[data-act="digest"]'); check("Хулоса тугмаси алмашади", pg.locator(".tog.on").count() == 1 - on0)
    pg.click('[data-act="fbtoggle"]'); check("Асосчига ёзиш очилади", pg.locator("#f-fb").count() == 1)
    pg.click('[data-act="fbsend"]'); check("Бўш хатга огоҳлантириш", pg.inner_text("#fberr") != "")
    pg.fill("#f-fb", "Salom"); pg.click('[data-act="fbsend"]'); check("Хат юборилди", pg.locator("#f-fb").count() == 0 and "Rahmat" in pg.inner_text("#toast"))
    pg.click('[data-act="privtoggle"]'); check("Махфийлик очилади", "faqat siz" in txt())
    # сақланиш: саҳифани янгилаш
    pg.reload(); tab("set")
    check("Созламалар сақланган (қайта очилганда)", pg.input_value("#qs") == "23" and pg.input_value("#qe") == "8")
    pg.click('[data-act="reset"]'); tab("list")
    check("Қайта бошлаш намунани тиклайди", "Test oylik" not in txt() and pg.locator(".card").count() == 6)
    check("JS хатолар йўқ", not errs)
    if errs: print(errs)
    b.close()
bad = [n for n, ok in res if not ok]
print(f"\nЖами: {len(res)}, муваффақиятсиз: {len(bad)}")
sys.exit(1 if bad else 0)
