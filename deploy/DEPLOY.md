# Сервер

Поллинг, белый IP не нужен.

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
sudo useradd -r -s /bin/bash -d /opt/iliya_avito iliya
sudo mkdir -p /opt/iliya_avito && sudo chown iliya:iliya /opt/iliya_avito
sudo -u iliya git clone https://github.com/Krutoymuzhik12/iliya.git /opt/iliya_avito
cd /opt/iliya_avito
sudo -u iliya python3 -m venv .venv
sudo -u iliya .venv/bin/pip install -U pip -r requirements.txt
```

Положить `.env` в `/opt/iliya_avito/.env` (ключи Avito и `POE_API_KEY`), права 600:

```bash
sudo nano /opt/iliya_avito/.env
sudo chown iliya:iliya /opt/iliya_avito/.env
sudo chmod 600 /opt/iliya_avito/.env
```

```bash
sudo cp /opt/iliya_avito/deploy/iliya-avito.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now iliya-avito
sudo journalctl -u iliya-avito -f
```
