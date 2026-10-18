# DOJU Эслатма Котиби — сервер қадамлари

Ҳамма калит (токен, база манзили) фақат `KALITLAR.txt` га ва Render'нинг Environment бўлимига ёзилади. Чатга ЁЗМАНГ.
FASO билан аралашмаслиги учун: алоҳида Neon лойиҳа, алоҳида Render хизмат, алоҳида токен.

## ҲОЗИР қилиш мумкин (мен кодни ёзаётганда)
1. **Neon** (neon.tech): Create project → номи `doju-eslatma`, регион Frankfurt (FASO билан бир хил). Яратилгач «Connection string» (postgresql://… билан бошланади) ни нусхалаб `KALITLAR.txt` га `NEON_DOJU=` деб ёзинг. Фақат шу. FASO базасига тегманг.
2. **Янги токен:** @BotFather → `/revoke` → `@eslatma_Kotibi_bot` → янги токенни `KALITLAR.txt` га `DOJU_BOT_TOKEN=` деб ёзинг. Эски токен шу заҳоти ўчади (компьютердаги ботни қайта ишга туширишда янги токен керак бўлади).
3. **Render:** GitHub ҳисобингизни репога (`juraevdostonbek26-ship-it/-`) рухсат берилганини текширинг (Render → Account → GitHub). Бошқа ҳеч нарса қилманг.

## Мен «код тайёр» деганимдан кейин
4. Render → New → **Web Service** → репо `-` → branch `claude/happy-carson-61yqi1`.
   - Name: `doju-eslatma` · Region: Frankfurt · Plan: **Free**
   - Root Directory: `eslatma_bot`
   - Build: `pip install -r requirements.txt` · Start: `python server.py` (аниқ буйруқни ўша пайт тасдиқлайман)
5. Render → Environment (қийматлар сизда, чатга ёзилмайди):
   - `TELEGRAM_BOT_TOKEN` (иккинчи қадамдаги)
   - `DATABASE_URL` (Neon'нинг)
   - `ADMIN_ID` (Telegram ID'нгиз)
   - `WEBHOOK_SECRET` (узун тасодифий матн; мен ясаб бераман)
   - `BASE_URL` = Render берган манзил (`https://doju-eslatma.onrender.com`)
6. **cron-job.org:** янги вазифа `DOJU bot` → URL `…/healthz`, ҳар 5 дақиқада, зона Asia/Tashkent, хатода почтага хабар. (Render Free 15 дақиқа сўровсиз ухлайди, шу уни уйғотиб туради.)
7. **BotFather → Bot Settings → Menu Button** → URL `…/app/` → тугма номи «Открыть» ўрнига «DOJU». 
8. Текшириш: ботга `/start`, эслатма қўшинг, «Открыть» ни босинг: бир хил кўриниши керак.

Керак бўлса айтинг: ҳар қадамни скриншот билан бирга текшираман.
