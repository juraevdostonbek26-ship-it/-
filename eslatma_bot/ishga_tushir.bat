@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  DOJU ESLATMA KOTIBI
echo  Tokenni shu yerga qo^yib Enter bosing:
set /p TELEGRAM_BOT_TOKEN=Token: 
echo.
echo  Bot ishlayapti. Bu oynani YOPMANG. To^xtatish: Ctrl+C
echo.
set PYTHONUTF8=1
python bot.py
echo.
echo  Bot to^xtadi. Yuqoridagi xatoni oling.
pause
