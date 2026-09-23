"""
Sapanca Ciftlik Restoran - Yazici Koprusu (Print Agent)
==========================================================
Bu program DUKKANDAKI bilgisayarda calisir (bulut sunucuda DEGIL).

Ne yapar:
  - Bulut sunucudaki panelin biriktirdigi fis isteklerini (print_queue)
    duzenli araliklarla kontrol eder
  - Her fisi, ayni yerel agdaki (WiFi/Ethernet) termal yaziciya
    ESC/POS komutlariyla gonderir
  - Basilan fisi sunucuya "tamamlandi" olarak bildirir

Kurulum:
  1. Asagidaki SERVER_URL ve AGENT_TOKEN degerlerini panelden
     ("Fis Yazicilari" sekmesi) kopyaladigin bilgilerle doldur.
  2. Bu klasordeki yazici-kopru-baslat.bat dosyasina cift tikla.
  3. Pencereyi acik birak (arka planda calismaya devam eder).
     Bilgisayar her acildiginda otomatik baslamasi icin
     yazici-kopru-baslat.bat kisayolunu Windows Baslangic
     klasorune koyabilirsin (win+R -> shell:startup).
"""
import time
import socket
import base64
import json
import urllib.request
import urllib.error

# ── AYARLAR — panelden ("Fiş Yazıcıları" sekmesi) kopyala ──────────────────────
SERVER_URL   = "https://BURAYA-PANEL-ADRESIN.gir"   # örn: https://siparis.restoranadi.com
AGENT_TOKEN  = "BURAYA-PANELDEKI-TOKEN-KODUNU-YAPISTIR"

POLL_SECONDS = 3       # sunucuyu kaç saniyede bir kontrol etsin
PRINTER_PORT = 9100    # ağ üzerinden termal yazıcıların standart portu


def api_get(path):
    req = urllib.request.Request(
        SERVER_URL + path,
        headers={"X-Agent-Token": AGENT_TOKEN},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def api_post(path):
    req = urllib.request.Request(
        SERVER_URL + path,
        method="POST",
        headers={"X-Agent-Token": AGENT_TOKEN},
    )
    urllib.request.urlopen(req, timeout=10)


def send_to_printer(ip, data):
    with socket.create_connection((ip, PRINTER_PORT), timeout=5) as sock:
        sock.sendall(data)


def process_once():
    printers = api_get("/api/print-agent/printers")
    jobs     = api_get("/api/print-agent/jobs")

    if not jobs:
        return 0

    printed = 0
    for job in jobs:
        station = job["station"]
        ip      = printers.get(f"{station}_ip")
        if not ip:
            print(f"[ATLANDI] Fiş #{job['id']} ({station}) — bu istasyon için IP tanımlı değil")
            continue
        data = base64.b64decode(job["ticket_data"])
        try:
            send_to_printer(ip, data)
        except OSError as e:
            print(f"[HATA] Fiş #{job['id']} ({station}, {ip}) basılamadı: {e} — sonraki turda tekrar denenecek")
            continue
        api_post(f"/api/print-agent/jobs/{job['id']}/ack")
        printed += 1
        print(f"[OK] Fiş #{job['id']} -> {station} ({ip})")
    return printed


def main_loop():
    print("=" * 55)
    print("  Yazici Koprusu (Print Agent) baslatildi")
    print(f"  Sunucu : {SERVER_URL}")
    print(f"  Kontrol araligi: {POLL_SECONDS} saniye")
    print("=" * 55)
    print("Bu pencereyi kapatma — arka planda calismaya devam eder.\n")

    while True:
        try:
            process_once()
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print("[HATA] Yetkisiz — AGENT_TOKEN yanlış olabilir, panelden kontrol et.")
            else:
                print(f"[HATA] Sunucu hatası: {e}")
        except urllib.error.URLError as e:
            print(f"[HATA] Sunucuya bağlanılamadı: {e}")
        except Exception as e:
            print(f"[HATA] Beklenmeyen hata: {e}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main_loop()
