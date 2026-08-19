# Сервер

Хост: `root@msk-1-vm-xcjy`
Каталог: `/var/opt/ilya-demo-balkon`
Поллинг, белый IP не нужен. Заходим root, отдельный пользователь не нужен.

На сервере, уже стоя в каталоге или из любого места:

```bash
cd /var/opt
# если каталог не пустой — убрать старое демо в сторону
[ -d ilya-demo-balkon ] && [ -n "$(ls -A ilya-demo-balkon 2>/dev/null)" ] && mv ilya-demo-balkon ilya-demo-balkon.bak.$(date +%F-%H%M)
git clone https://github.com/Krutoymuzhik12/iliya.git /var/opt/ilya-demo-balkon
cd /var/opt/ilya-demo-balkon
python3 -m venv .venv
.venv/bin/pip install -U pip -r requirements.txt
```

`.env` с рабочей машины (секреты в git не лежат):

```bash
scp .env root@msk-1-vm-xcjy:/var/opt/ilya-demo-balkon/.env
```

На сервере:

```bash
chmod 600 /var/opt/ilya-demo-balkon/.env
cd /var/opt/ilya-demo-balkon && .venv/bin/python -c "from config.settings import SETTINGS; print('avito:', SETTINGS.avito_ready(), 'poe:', SETTINGS.poe_ready())"
```

Запуск:

```bash
cp /var/opt/ilya-demo-balkon/deploy/iliya-avito.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now iliya-avito
systemctl status iliya-avito --no-pager
journalctl -u iliya-avito -f
```

Обновление кода:

```bash
cd /var/opt/ilya-demo-balkon && git pull && .venv/bin/pip install -r requirements.txt && systemctl restart iliya-avito
```
