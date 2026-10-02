"""Site şifresini (cihaz girişi) belirler ya da değiştirir.
Şifre değişince giriş yapmış bütün cihazlar tekrar şifre sorar.

Sunucuda: cd /var/www/siparis-takip && venv/bin/python site_sifresi.py
"""
import getpass

from werkzeug.security import generate_password_hash

import app

app.init_db()
pw = getpass.getpass("Yeni site şifresi: ")
if len(pw) < 8:
    raise SystemExit("En az 8 karakter olmalı — şifre değişmedi.")
if getpass.getpass("Tekrar: ") != pw:
    raise SystemExit("Şifreler aynı değil — şifre değişmedi.")
app.set_setting("site_password_hash", generate_password_hash(pw))
print("Site şifresi kaydedildi.")
