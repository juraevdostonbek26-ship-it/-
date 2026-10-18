# DOJU Эслатма Котиби — сервер қадамлари (код тайёр)

Калитлар фақат `KALITLAR.txt` нинг DOJU бўлимида ва Render'нинг махфий майдонларида. Чатга ЁЗМАНГ.

## Олдиндан керак (сизда)
- `NEON_DOJU=` — Neon уланиш манзили (тайёр)
- `DOJU_BOT_TOKEN=` — BotFather'дан янги токен (`/revoke` → `@eslatma_Kotibi_bot`)
- `ADMIN_ID=5421990729`

## Render (Blueprint — битта тугма билан)
1. dashboard.render.com → **New +** → **Blueprint**.
2. Репо: `juraevdostonbek26-ship-it/-` (GitHub рухсат сўраса, рухсат беринг). **Branch: `claude/happy-carson-61yqi1`**.
3. Render `render.yaml` ни ўқиб `doju-eslatma` хизматини кўрсатади (Free, Frankfurt). Сўралган 3 та махфий майдонга **ўз файлингиздан** қийматларни ёпиштиринг:
   - `TELEGRAM_BOT_TOKEN` = `DOJU_BOT_TOKEN` қиймати
   - `DATABASE_URL` = `NEON_DOJU` қиймати (бутун `postgresql://…` манзил)
   - `ADMIN_ID` = `5421990729`
4. **Apply / Deploy**. 3–5 дақиқа кутинг. Ўртасида «Live» ёзуви чиқади.
5. Текшириш: Render берган манзилнинг охирига `/healthz` ёзиб очинг (масалан `https://doju-eslatma.onrender.com/healthz`). `{"ok": true}` чиқиши керак.
6. Telegram'да ботга `/start`. Жавоб келса, ишлаяпти.

## Уйғотувчи (cron-job.org)
Render Free 15 дақиқа сўров бўлмаса ухлайди. Шунинг учун:
- cron-job.org → **Create cronjob** → номи `DOJU bot` → URL: `https://<хизмат-манзили>/healthz` → ҳар **5 дақиқада** → Time zone `Asia/Tashkent` → «Notify on failure» ёқинг → Create.
FASO вазифасига тегманг, алоҳида янги вазифа очинг.

## Агар ишламаса
Render → хизмат → **Logs** бўлимидаги охирги қаторлар скриншотини юборинг (махфий қийматларни ёпиб).
