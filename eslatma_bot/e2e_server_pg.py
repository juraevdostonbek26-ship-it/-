"""Сервер + Postgres охиригача синови (маҳаллий Postgres керак, порт 5544). Ишга тушириш: python3 e2e_server_pg.py"""
import json, os, subprocess, sys, time, urllib.request
sys.path.insert(0, "/home/user/-/eslatma_bot")
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
from fake_telegram import FakeTelegram
SECRET = "e2e_secret_0123456789_abcdefgh"
fake = FakeTelegram()
env = dict(os.environ, TELEGRAM_BOT_TOKEN="123:FAKE", TELEGRAM_API=fake.url, WEBHOOK_SECRET=SECRET, BASE_URL="https://doju.test",
           DATABASE_URL="postgresql://postgres@127.0.0.1:5544/dojusrv", PORT="18080", ADMIN_ID="999")
p = subprocess.Popen([sys.executable, "-u", "server.py"], cwd="/home/user/-/eslatma_bot", env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
def get(path): return urllib.request.urlopen("http://127.0.0.1:18080" + path, timeout=10).read()
def post(up): 
    r = urllib.request.Request(f"http://127.0.0.1:18080/webhook/{SECRET}", json.dumps(up).encode(), {"Content-Type": "application/json", "X-Telegram-Bot-Api-Secret-Token": SECRET})
    return urllib.request.urlopen(r, timeout=20).status
ok = lambda n, c: print(("OK   " if c else "FAIL ") + n)
for _ in range(50):
    try: get("/healthz"); break
    except Exception: time.sleep(0.2)
ok("healthz", json.loads(get("/healthz")) == {"ok": True})
ok("webhook ўрнатилди", getattr(fake, "webhook", {}).get("url") == f"https://doju.test/webhook/{SECRET}")
fake.say(7, "/start"); post(fake.updates[-1])
ok("биринчи хабарга жавоб (тил сўрови)", any("Tilni" in x[2] for x in fake.visible(7) if x[1] == "bot"))
fake.click(7, "🇺🇿 UZB"); post(fake.updates[-1])
ok("тил танланди, меню чиқди", any("DOJU" in x[2] for x in fake.visible(7) if x[1] == "bot"))
fake.menu = None
# Neon ухлаб уйғонишини тақлид: Postgres'ни қайта ишга тушириш
subprocess.run(["su", "postgres", "-c", "/usr/lib/postgresql/16/bin/pg_ctl -D /tmp/pgdata_doju -o '-p 5544 -k /tmp' -l /tmp/pg.log restart -w >/dev/null"], check=True)
fake.tap_menu(7, "📩 Asoschiga yozish"); post(fake.updates[-1])
ok("база қайта ишга тушгандан кейин ҳам ишлайди", any("Asoschiga" in x[2] for x in fake.visible(7) if x[1] == "bot"))
fake.say(7, "Test xato haqida"); post(fake.updates[-1])
adm = [x for x in fake.visible(999) if x[1] == "bot"]
ok("«Асосчига ёзиш» хати ADMIN_ID га келди, юборувчи номисиз", adm and "Test xato" in adm[-1][2] and "7" not in adm[-1][2].replace("#1", ""))
p.terminate(); out = p.communicate(timeout=10)[0]
ok("логда махфий қиймат йўқ", SECRET not in out and "123:FAKE" not in out)
print(out[-400:])
