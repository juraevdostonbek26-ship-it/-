# Серверга жойлаш (Linux, systemd)

```bash
sudo useradd -r -s /usr/sbin/nologin eslatma
sudo mkdir -p /opt/eslatma_bot /var/lib/eslatma
sudo cp eslatma_bot/bot.py eslatma_bot/logic.py /opt/eslatma_bot/
sudo chown -R eslatma: /var/lib/eslatma
echo 'TELEGRAM_BOT_TOKEN=ТОКЕН' | sudo tee /etc/eslatma-bot.env >/dev/null
sudo chmod 600 /etc/eslatma-bot.env
sudo cp deploy/eslatma-bot.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now eslatma-bot
journalctl -u eslatma-bot -f      # лог
```
Бот ташқаридан порт очмайди (Telegram'га ўзи уланади), шунинг учун сервер файрволида фақат SSH қолади.

## Сервер хавфсизлиги (бузиб киришдан)
- SSH: фақат калит билан кириш (`PasswordAuthentication no`), root билан кириш ўчирилган.
- Файрвол: фақат 22 порт (`ufw allow 22 && ufw enable`), `fail2ban` ўрнатилган.
- Бот алоҳида фойдаланувчи (`eslatma`) остида, токен файли рухсати 600.
- `data.db` нусхасини (backup) мунтазам олиб туринг.
