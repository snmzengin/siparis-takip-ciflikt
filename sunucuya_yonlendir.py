"""Sistem buluta taşındı — eski yerel adrese (http://<bu-pc>:5000/...) gelen tabletleri
aynı sayfanın sunucudaki adresine yönlendirir."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SUNUCU = "http://45.84.191.102"


class Yonlendir(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(302)
        self.send_header("Location", SUNUCU + self.path)
        self.end_headers()

    do_POST = do_HEAD = do_GET

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"Eski adres yonlendiriliyor -> {SUNUCU}")
    ThreadingHTTPServer(("0.0.0.0", 5000), Yonlendir).serve_forever()
