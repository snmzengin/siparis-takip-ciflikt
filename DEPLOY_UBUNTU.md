# Sapanca Çiftlik Restoran — Ubuntu VDS Kurulum Rehberi

GüzelHosting'ten aldığın VDS'e (Ubuntu) bu sistemi kurma adımları.
Alan adını `siparis.seninsiten.com` olarak varsaydım — gerçek alan adınla değiştir.

---

## 0) ÖNEMLİ — Kuruluma başlamadan bil

Bu panelde (`/` admin ekranı) şu an **giriş/parola koruması yok**. Yerel ağda
sadece dükkândaki WiFi'a bağlı biri görebildiği için sorun değildi. İnternete
açılınca **herkes** bu adrese girip siparişleri, menüyü, fiyatları görüp
değiştirebilir. Bu yüzden aşağıdaki adımlarda nginx üzerinden tüm siteye
**kullanıcı adı + parola koruması (Basic Auth)** ekliyoruz — bu koruma bir
kere tarayıcıda girilir, tarayıcı hatırlar (tabletlerde/ekranlarda tekrar
sormaz, sekme kapanana kadar).

---

## 1) Sunucuya bağlan

Windows'ta PowerShell'den:
```powershell
ssh root@SUNUCU_IP_ADRESI
```
(GüzelHosting sana kullanıcı adı/parola veya SSH anahtarı verecek)

---

## 2) Sistemi güncelle, gerekli paketleri kur

```bash
apt update && apt upgrade -y
apt install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx ufw apache2-utils
```

---

## 3) Proje dosyalarını sunucuya yükle

Kendi bilgisayarından (PowerShell, proje klasöründeyken):
```powershell
scp -r "C:\Users\TR\Desktop\İREMTOŞ\siparis-takip" root@SUNUCU_IP_ADRESI:/var/www/siparis-takip
```
`print_agent` klasörünü ve `.md` dosyalarını sunucuya göndermene gerek yok
(onlar dükkândaki bilgisayarda kalacak) ama zararı olmaz.

---

## 4) Python ortamı kur

Sunucuda (SSH içinde):
```bash
cd /var/www/siparis-takip
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-prod.txt
deactivate
```

---

## 5) Uygulamayı servis olarak çalıştır (systemd)

```bash
nano /etc/systemd/system/siparis-takip.service
```
İçine:
```ini
[Unit]
Description=Sapanca Ciftlik Restoran - Siparis Takip
After=network.target

[Service]
User=root
WorkingDirectory=/var/www/siparis-takip
ExecStart=/var/www/siparis-takip/venv/bin/gunicorn -w 3 -b 127.0.0.1:8000 --timeout 30 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Servisi başlat:
```bash
systemctl daemon-reload
systemctl enable siparis-takip
systemctl start siparis-takip
systemctl status siparis-takip
```
`active (running)` görüyorsan tamam. Loglara bakmak için: `journalctl -u siparis-takip -f`

---

## 6) Basic Auth şifre dosyası oluştur

```bash
htpasswd -c /etc/nginx/.siparis-htpasswd iremtis
```
(kullanıcı adını istediğin gibi değiştir, parola soracak — güçlü bir şey seç,
bunu tabletlere/ekranlara ilk açılışta bir kere gireceksin)

---

## 7) nginx reverse proxy ayarı

```bash
nano /etc/nginx/sites-available/siparis-takip
```
İçine:
```nginx
server {
    listen 80;
    server_name siparis.seninsiten.com;

    # print-agent kendi token'ıyla kimlik doğruluyor,
    # bu yüzden Basic Auth'tan HARİÇ tutulmalı — yoksa yazıcı köprüsü çalışmaz
    location /api/print-agent/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        auth_basic "Sapanca Ciftlik Restoran";
        auth_basic_user_file /etc/nginx/.siparis-htpasswd;

        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Etkinleştir:
```bash
ln -s /etc/nginx/sites-available/siparis-takip /etc/nginx/sites-enabled/
nginx -t
systemctl restart nginx
```

---

## 8) Alan adını sunucuya yönlendir

Alan adını aldığın yerin (mevcut domain sağlayıcın) DNS panelinden:
- **A kaydı** ekle: `siparis` (veya seçtiğin alt alan adı) → VDS'in IP adresi

DNS yayılması 5 dk – birkaç saat sürebilir. `nslookup siparis.seninsiten.com`
ile IP'nin doğru göründüğünü kontrol edebilirsin.

---

## 9) Ücretsiz HTTPS (Let's Encrypt)

DNS yayıldıktan sonra:
```bash
certbot --nginx -d siparis.seninsiten.com
```
Sorulara e-posta gir, şartları kabul et. Otomatik olarak nginx config'ini
HTTPS'e çevirir ve sertifikayı 90 günde bir kendisi yeniler.

---

## 10) Güvenlik duvarı (ufw)

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable
```

---

## 11) Test et

Tarayıcıda `https://siparis.seninsiten.com` — Basic Auth kullanıcı adı/parola
soracak, girince panel açılmalı.

---

## 12) Dükkânda print-agent'ı kur

`print_agent` klasörünü dükkândaki bilgisayara USB ile taşı (bu klasör
sunucuya değil, dükkândaki PC'ye gidecek):

1. `print_agent.py` dosyasını aç, en üstteki `SERVER_URL` ve `AGENT_TOKEN`
   değerlerini panelin "Fiş Yazıcıları" sekmesinden kopyaladığın bilgilerle
   doldur (`SERVER_URL = "https://siparis.seninsiten.com"`)
2. `yazici-kopru-baslat.bat`'e çift tıkla, pencereyi açık bırak
3. Otomatik başlaması için bu .bat'in kısayolunu Windows Başlangıç
   klasörüne koy: `Win+R` → `shell:startup` → kısayolu oraya sürükle

---

## Güncelleme yapman gerektiğinde

Kod değiştiğinde sunucuya yeniden yükleyip servisi yeniden başlatman gerekir:
```powershell
scp -r "C:\Users\TR\Desktop\İREMTOŞ\siparis-takip\app.py" root@SUNUCU_IP_ADRESI:/var/www/siparis-takip/app.py
```
```bash
systemctl restart siparis-takip
```

---

## Sorun giderme

| Belirti | Kontrol et |
|---|---|
| Site açılmıyor | `systemctl status siparis-takip`, `systemctl status nginx` |
| 502 Bad Gateway | Gunicorn servisi çalışmıyor olabilir — `journalctl -u siparis-takip -f` |
| Basic Auth sürekli soruyor | Kullanıcı adı/parolayı `htpasswd` ile yeniden oluştur |
| Fişler basılmıyor | Dükkânda `yazici-kopru-baslat.bat` açık mı? Panelden "Otomatik yazdırmayı etkinleştir" işaretli mi? |
| HTTPS sertifika hatası | DNS'in gerçekten VDS IP'sine işaret ettiğinden emin ol, sonra `certbot --nginx -d ...` tekrar çalıştır |
