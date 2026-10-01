from flask import Flask, render_template, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import socket
import threading
import base64
import secrets
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024  # fatura yüklemeleri için 15MB sınırı
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)  # Z Raporu girişi 30 gün hatırlanır
DB_PATH = os.path.join(os.path.dirname(__file__), "restaurant.db")

RECEIPT_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads", "expenses")
ALLOWED_RECEIPT_EXT = {"png", "jpg", "jpeg", "webp", "pdf"}
os.makedirs(RECEIPT_UPLOAD_DIR, exist_ok=True)

# Mutfak terminali kategori filtreleri (küçük harf, kısmi eşleşme)
PIZZA_KEYWORDS = ["pizza"]

def tr_lower(s):
    """Türkçe büyük İ/I karakterlerini doğru küçülten lower()."""
    return s.replace("İ", "i").replace("I", "ı").lower()


def is_pizza_category(cat):
    return any(k in tr_lower(cat or "") for k in PIZZA_KEYWORDS)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        for col, typ in [("payment_method", "TEXT"), ("closed_at", "TIMESTAMP"), ("waiter", "TEXT"), ("discount", "REAL"), ("ikram_note", "TEXT")]:
            try:
                conn.execute(f"ALTER TABLE orders ADD COLUMN {col} {typ}")
            except Exception:
                pass
        try:
            conn.execute("ALTER TABLE expenses ADD COLUMN receipt_image TEXT")
        except Exception:
            pass
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS waiters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                pin TEXT NOT NULL DEFAULT '0000'
            );
        """)
        for name, pin in [("Sami","1111"),("Rahman","2222"),("Engin","3333"),("Bedirhan","4444")]:
            try:
                conn.execute("INSERT INTO waiters (name, pin) VALUES (?, ?)", (name, pin))
            except Exception:
                pass
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                category TEXT DEFAULT 'Genel'
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_number TEXT NOT NULL,
                status TEXT DEFAULT 'Aktif',
                notes TEXT,
                total REAL DEFAULT 0,
                payment_method TEXT,
                waiter TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
                menu_item_id INTEGER,
                item_name TEXT NOT NULL,
                item_price REAL NOT NULL,
                quantity INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS stock_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                quantity REAL DEFAULT 0,
                unit TEXT DEFAULT 'adet',
                min_quantity REAL DEFAULT 0,
                menu_item_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS bungalov_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bungalov_no INTEGER NOT NULL,
                guest_name TEXT NOT NULL,
                checkin_date TEXT NOT NULL,
                checkout_date TEXT,
                status TEXT DEFAULT 'Açık',
                payment_method TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS bungalov_charges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER REFERENCES bungalov_accounts(id) ON DELETE CASCADE,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                order_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS print_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station TEXT NOT NULL,
                ticket_data TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS ingredients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                unit TEXT NOT NULL DEFAULT 'kg',
                unit_cost REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS menu_item_ingredients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                menu_item_id INTEGER NOT NULL REFERENCES menu_items(id) ON DELETE CASCADE,
                ingredient_id INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
                quantity REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expense_date TEXT NOT NULL,
                vendor TEXT,
                category TEXT DEFAULT 'Genel',
                description TEXT,
                amount REAL NOT NULL DEFAULT 0,
                receipt_image TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)


# ── AYARLAR ───────────────────────────────────────────────────────────────────

def get_setting(key, default=None):
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value)
        )


# ── FİŞ YAZICI (ESC/POS fiş üretimi — gerçek yazdırma dükkândaki print-agent.py'de) ──

LINE_WIDTH = 48  # 80mm termal yazıcı için tipik karakter genişliği

ESC = b"\x1b"
GS  = b"\x1d"


TR_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜâîûÂÎÛ", "cgiosuCGIOSUaiuAIU")


def _p(text):
    """Fiş metnini düz ASCII'ye çevirir — yazıcı Türkçe karakter basamıyor (Çoban -> Coban)."""
    return text.translate(TR_ASCII).encode("ascii", errors="replace")


def build_ticket(title, table, waiter, items, notes):
    parts = [
        ESC + b"@",                 # yazıcıyı sıfırla
        b"\x1c.",                   # Çince karakter modunu kapat (Xprinter'da fabrika ayarı açık)
        ESC + b"a" + bytes([1]),    # ortala
        ESC + b"!" + bytes([0x30]), # çift genişlik + çift yükseklik
        _p(title + "\n"),
        ESC + b"!" + bytes([0x00]), # normal boy
        ESC + b"a" + bytes([0]),    # sola hizala
        _p("-" * LINE_WIDTH + "\n"),
        _p(f"Masa: {table}\n"),
    ]
    if waiter:
        parts.append(_p(f"Garson: {waiter}\n"))
    parts.append(_p(datetime.now().strftime("%d.%m.%Y %H:%M") + "\n"))
    parts.append(_p("-" * LINE_WIDTH + "\n"))
    for it in items:
        parts.append(_p(f"{it['quantity']} x {it['name']}\n"))
    if notes:
        parts.append(_p("-" * LINE_WIDTH + "\n"))
        parts.append(_p(f"Not: {notes}\n"))
    parts.append(_p("\n"))
    parts.append(ESC + b"d" + bytes([6]))  # son satırlar bıçağı geçsin diye 6 satır ilerlet
    parts.append(GS + b"V" + bytes([1]))  # kısmi kesim
    return b"".join(parts)


def enqueue_ticket(station, title, table, waiter, items, notes):
    """Fişi ESC/POS baytlarına çevirir ve kuyruğa (print_queue) yazar.
    Sunucu artık dükkândaki yazıcıya doğrudan bağlanamıyor (bulutta çalışıyor) —
    dükkândaki print-agent.py bu kuyruğu çekip gerçek yazdırmayı yapıyor."""
    if not items:
        return
    data = build_ticket(title, table, waiter, items, notes)
    b64  = base64.b64encode(data).decode("ascii")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO print_queue (station, ticket_data, status) VALUES (?, ?, 'pending')",
            (station, b64)
        )


def route_and_print_new_items(table, waiter, items, notes, menu_categories, cancel=False):
    """Yeni eklenen ürünleri kategorisine göre pizza/mutfak fişine böler ve kuyruğa ekler.
    cancel=True: adisyondan çıkarılan ürünler için "IPTAL" fişi basar."""
    if get_setting("printer_enabled", "0") != "1":
        return
    pizza_items, mutfak_items = [], []
    for it in items:
        cat = menu_categories.get(it.get("menu_item_id"), "")
        (pizza_items if is_pizza_category(cat) else mutfak_items).append(it)
    prefix = "IPTAL - " if cancel else ""

    def worker():
        if pizza_items:
            enqueue_ticket("pizza", prefix + "PIZZA TEZGAHI", table, waiter, pizza_items, notes)
        if mutfak_items:
            enqueue_ticket("mutfak", prefix + "MUTFAK", table, waiter, mutfak_items, notes)

    threading.Thread(target=worker, daemon=True).start()


def get_or_create_agent_token():
    token = get_setting("print_agent_token")
    if not token:
        token = secrets.token_hex(16)
        set_setting("print_agent_token", token)
    return token


def check_agent_token():
    token = request.headers.get("X-Agent-Token", "")
    expected = get_or_create_agent_token()
    return bool(token) and secrets.compare_digest(token, expected)


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/garson")
def garson():
    return render_template("garson.html")

@app.route("/api/waiters", methods=["GET"])
def list_waiters():
    with get_db() as conn:
        rows = conn.execute("SELECT id, name FROM waiters ORDER BY name").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/waiters/<int:wid>/pin", methods=["PUT"])
def update_waiter_pin(wid):
    data = request.json
    pin  = data.get("pin", "").strip()
    if not pin.isdigit() or len(pin) != 4:
        return jsonify({"error": "PIN 4 haneli rakam olmalı"}), 400
    with get_db() as conn:
        conn.execute("UPDATE waiters SET pin=? WHERE id=?", (pin, wid))
    return jsonify({"ok": True})

@app.route("/api/auth/pin", methods=["POST"])
def verify_pin():
    data = request.json
    name = data.get("name", "").strip()
    pin  = data.get("pin", "").strip()
    with get_db() as conn:
        row = conn.execute("SELECT id FROM waiters WHERE name=? AND pin=?", (name, pin)).fetchone()
    if row:
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 401


# ── Z RAPORU EKRANI (kullanıcı adı + şifre ile giriş) ───────────────────────────

OWNERS_SCHEMA = """
    CREATE TABLE IF NOT EXISTS owners (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""


@app.before_request
def ensure_secret_key():
    """Oturum anahtarını veritabanında saklar — sunucu yeniden başlasa da (ve gunicorn
    işçileri arasında) patron girişleri geçerli kalır."""
    if app.secret_key:
        return
    with get_db() as conn:
        conn.executescript(OWNERS_SCHEMA)
        try:
            conn.execute("ALTER TABLE owners ADD COLUMN display_name TEXT")  # karşılama adı ("Hoş geldin, Ahmet")
        except sqlite3.OperationalError:
            pass
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('session_secret', ?)",
                     (secrets.token_hex(32),))
        app.secret_key = conn.execute(
            "SELECT value FROM settings WHERE key='session_secret'").fetchone()["value"]


def current_owner_row():
    """Oturumdaki patronun güncel kaydı — hesap silindiyse None (oturum düşer)."""
    owner_id = session.get("owner_id")
    if not owner_id:
        return None
    with get_db() as conn:
        return conn.execute("SELECT username, display_name FROM owners WHERE id=?", (owner_id,)).fetchone()


def current_owner():
    row = current_owner_row()
    return row["username"] if row else None


@app.route("/z-raporu")
def z_raporu_page():
    return render_template("z_raporu.html")


@app.route("/api/patron/login", methods=["POST"])
def patron_login():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    with get_db() as conn:
        row = conn.execute("SELECT id, username, display_name, password_hash FROM owners WHERE username=?",
                           (username,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify({"ok": False, "error": "Kullanıcı adı veya şifre hatalı"}), 401
    session.permanent = True
    session["owner_id"] = row["id"]
    return jsonify({"ok": True, "username": row["username"], "display_name": row["display_name"] or row["username"]})


@app.route("/api/patron/logout", methods=["POST"])
def patron_logout():
    session.pop("owner_id", None)
    return jsonify({"ok": True})


@app.route("/api/patron/me")
def patron_me():
    with get_db() as conn:
        has_owner = conn.execute("SELECT 1 FROM owners LIMIT 1").fetchone() is not None
    row = current_owner_row()
    return jsonify({
        "username":     row["username"] if row else None,
        "display_name": (row["display_name"] or row["username"]) if row else None,
        "has_owner":    has_owner,
    })


def _z_summary(period, date_str):
    import datetime as dt
    import calendar
    d = dt.date.fromisoformat(date_str or dt.date.today().isoformat())
    if period == "weekly":
        start = d - dt.timedelta(days=d.weekday())
        end = start + dt.timedelta(days=6)
        prev_start, prev_end = start - dt.timedelta(days=7), end - dt.timedelta(days=7)
    elif period == "monthly":
        start = d.replace(day=1)
        end = d.replace(day=calendar.monthrange(d.year, d.month)[1])
        prev_end = start - dt.timedelta(days=1)
        prev_start = prev_end.replace(day=1)
    else:
        period = "daily"
        start = end = d
        prev_start = prev_end = d - dt.timedelta(days=1)

    report = _report_for_range(start.isoformat(), end.isoformat())
    prev = _report_for_range(prev_start.isoformat(), prev_end.isoformat())
    rng = (start.isoformat(), end.isoformat())
    with get_db() as conn:
        active = conn.execute(
            "SELECT COUNT(*) AS cnt, COALESCE(SUM(total), 0) AS amount FROM orders WHERE status='Aktif'"
        ).fetchone()
        # "Kahvaltı" kategorisindeki ürünler (menüden silinmişse ürün adından yakalanır)
        breakfast_items = conn.execute("""
            SELECT oi.item_name,
                   SUM(oi.quantity)                 AS total_qty,
                   SUM(oi.item_price * oi.quantity) AS total_amount
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            LEFT JOIN menu_items mi ON mi.id = oi.menu_item_id
            WHERE DATE(o.created_at, '+3 hours') BETWEEN ? AND ? AND o.status = 'Ödendi'
              AND (mi.category LIKE '%ahvalt%' OR oi.item_name LIKE '%ahvalt%')
            GROUP BY oi.item_name ORDER BY total_qty DESC
        """, rng).fetchall()
        # Pizza satışı: pizza tezgahına giden kategori ("Pizzalar"); menüden silinmişse ürün adından
        pizza_items = conn.execute("""
            SELECT oi.item_name,
                   SUM(oi.quantity)                 AS total_qty,
                   SUM(oi.item_price * oi.quantity) AS total_amount
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            LEFT JOIN menu_items mi ON mi.id = oi.menu_item_id
            WHERE DATE(o.created_at, '+3 hours') BETWEEN ? AND ? AND o.status = 'Ödendi'
              AND (LOWER(mi.category) LIKE '%pizza%' OR LOWER(oi.item_name) LIKE '%pizza%')
            GROUP BY oi.item_name ORDER BY total_qty DESC, total_amount DESC
        """, rng).fetchall()
    pizza_items = [dict(r) for r in pizza_items]

    # İçecek satışı: adında çay/kahve geçenler "Çay & Kahve", İçecekler kategorisindeki diğerleri "Meşrubat"
    with get_db() as conn:
        categories = {r["name"]: r["category"] for r in conn.execute("SELECT name, category FROM menu_items")}
    drinks = {"mesrubat": [], "sicak": []}
    for it in report["items"]:
        name = tr_lower(it["item_name"])
        if "çay" in name or "kahve" in name:
            drinks["sicak"].append(it)
        elif "içecek" in tr_lower(categories.get(it["item_name"]) or ""):
            drinks["mesrubat"].append(it)
    for key, rows in drinks.items():
        report[f"{key}_items"] = rows
        report[f"{key}_qty"] = sum(r["total_qty"] for r in rows)
        report[f"{key}_total"] = round(sum(r["total_amount"] for r in rows), 2)

    report.update({
        "pizza_items": pizza_items,
        "pizza_qty":   sum(i["total_qty"] for i in pizza_items),
        "pizza_total": round(sum(i["total_amount"] for i in pizza_items), 2),
    })
    # Servis ayrımı ürüne göre (menü fiyatlarıyla): kahvaltı ürünleri kahvaltı servisi, geri kalanı akşam.
    # İndirim burada düşülmez; toplam kazanç ise tahsil edilen (indirimli) tutardır.
    breakfast_items = [dict(r) for r in breakfast_items]
    breakfast_total = round(sum(i["total_amount"] for i in breakfast_items), 2)
    items_total = sum(i["total_amount"] or 0 for i in report["items"])
    report.update({
        "breakfast_items": breakfast_items,
        "breakfast_qty":   sum(i["total_qty"] for i in breakfast_items),
        "breakfast_total": breakfast_total,
        "dinner_total":    round(max(0, items_total - breakfast_total), 2),
        "period":        period,
        "prev_total":    prev["total_amount"],
        "active_count":  active["cnt"],
        "active_amount": active["amount"],
        "other_total":   round(max(0, report["total_amount"] - report["nakit_total"] - report["kart_total"]), 2),
    })
    # Konaklama tahsilatları ayrı tutulur; kasa satırı restoran + konaklama toplamıdır (POS ile karşılaştırma için)
    report.update(_lodging_for_range(start.isoformat(), end.isoformat()))
    report["kasa_nakit"] = round(report["nakit_total"] + report["lodging_nakit"], 2)
    report["kasa_kart"] = round(report["kart_total"] + report["lodging_kart"], 2)
    report["kasa_havale"] = report["lodging_havale"]  # havale sadece konaklamada; POS/kasadan geçmez
    report.update(_cash_float_for_range(start.isoformat(), end.isoformat()))
    return report


@app.route("/api/patron/summary")
def patron_summary():
    if not current_owner():
        return jsonify({"error": "Giriş gerekli"}), 401
    return jsonify(_z_summary(request.args.get("period", "daily"), request.args.get("date")))


def _money(v):
    """12345.5 -> '12.345,50 TL'"""
    return f"{v or 0:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " TL"


def _row(left, right, width=None):
    """Solda açıklama, sağda tutar — fiş satırını tam genişliğe yayar."""
    width = width or LINE_WIDTH
    left = left[: width - len(right) - 1]
    return left + " " * (width - len(left) - len(right)) + right + "\n"


def build_z_ticket(r, username):
    """Z Raporu özetini POS fişi görünümünde ESC/POS baytlarına çevirir."""
    import datetime as dt
    f = dt.date.fromisoformat(r["date_from"]).strftime("%d.%m.%Y")
    t = dt.date.fromisoformat(r["date_to"]).strftime("%d.%m.%Y")
    period_name = {"daily": "Gunluk", "weekly": "Haftalik", "monthly": "Aylik"}[r["period"]]
    line = "-" * LINE_WIDTH + "\n"

    def section(title):
        pad = LINE_WIDTH - len(title) - 2
        return "-" * (pad // 2) + " " + title + " " + "-" * (pad - pad // 2) + "\n"

    body = line
    body += _row("Donem", f if f == t else f"{f} - {t}")
    body += _row("Rapor turu", period_name)
    body += _row("Yazdirma", datetime.now().strftime("%d.%m.%Y %H:%M"))
    body += _row("Kullanici", username)
    body += line
    body += _row("Kapanan adisyon", str(r["total_orders"]))
    avg = r["total_amount"] / r["total_orders"] if r["total_orders"] else 0
    body += _row("Ortalama adisyon", _money(avg))
    body += _row("Acik masa", f"{r['active_count']} ({_money(r['active_amount'])})")
    body += section("ODEME DAGILIMI")
    body += _row("Nakit", _money(r["nakit_total"]))
    body += _row("Kredi Karti", _money(r["kart_total"]))
    if r["other_total"] > 0.5:
        body += _row("Diger", _money(r["other_total"]))
    body += section("SERVIS DAGILIMI")
    body += _row(f"Kahvalti servisi ({r['breakfast_qty']} porsiyon)", _money(r["breakfast_total"]))
    body += _row("Aksam yemegi servisi", _money(r["dinner_total"]))
    body += section("PIZZA SATISI")
    for it in r["pizza_items"]:
        body += _row(f"{it['total_qty']} x {it['item_name']}", _money(it["total_amount"]))
    body += _row(f"Toplam {r['pizza_qty']} pizza", _money(r["pizza_total"]))
    body += section("ICECEK SATISI")
    body += _row(f"Mesrubat ({r['mesrubat_qty']} adet)", _money(r["mesrubat_total"]))
    body += _row(f"Cay & Kahve ({r['sicak_qty']} adet)", _money(r["sicak_total"]))
    body += section("KONAKLAMA TAHSILATI")
    for p in r["lodging_payments"]:
        who = f"{p['unit']}" + (f" {p['guest_name']}" if p["guest_name"] else "")
        short = {"Nakit": "Nakit", "Kredi Kartı": "Kart", "Havale": "Havale"}.get(p["payment_method"], p["payment_method"])
        body += _row(f"{who} ({short})", _money(p["amount"]))
    if not r["lodging_payments"]:
        body += "Tahsilat yok\n"
    body += _row("Konaklama toplam", _money(r["lodging_total"]))
    body += section("IKRAM (UCRETSIZ)")
    for o in r["ikram_orders"]:
        who = o["table_number"] + (f" {o['ikram_note']}" if o["ikram_note"] else "")
        body += _row(who, _money(o["total"]))
    if not r["ikram_orders"]:
        body += "Ikram yok\n"
    body += _row(f"Ikram toplam ({r['ikram_count']} adisyon)", _money(r["ikram_total"]))
    body += section("KASA (RESTORAN + KONAKLAMA)")
    body += _row("Nakit", _money(r["kasa_nakit"]))
    body += _row("Kredi Karti", _money(r["kasa_kart"]))
    if r["kasa_havale"]:
        body += _row("Havale (banka)", _money(r["kasa_havale"]))
    body += _row("Acilis kasasi (devreden)",
                 _money(r["float_opening"]) if r["float_opening"] is not None else "girilmedi")
    body += _row("Kasada birakilan (yarina)",
                 _money(r["float_closing"]) if r["float_closing"] is not None else "girilmedi")
    body += section("GARSON SATISLARI")
    for w in r["waiters"]:
        body += _row(f"{w['waiter']} ({w['order_count']} adisyon)", _money(w["total_amount"]))
    if not r["waiters"]:
        body += "Satis yok\n"
    body += section("URUN SATISLARI")
    for it in r["items"]:
        body += _row(f"{it['total_qty']} x {it['item_name']}", _money(it["total_amount"]))
    if not r["items"]:
        body += "Satis yok\n"
    body += section("GIDER / NET")
    body += _row("Giderler", _money(r["expense_total"]))
    body += _row("Net (satis - gider)", _money(r["net_amount"]))
    body += line

    parts = [
        ESC + b"@",
        b"\x1c.",                   # Çince karakter modunu kapat
        ESC + b"a" + bytes([1]),    # ortala
        _p("SAPANCA CIFTLIK RESTORAN\n"),
        ESC + b"!" + bytes([0x30]), # çift boy
        _p("Z RAPORU\n"),
        ESC + b"!" + bytes([0x00]),
        ESC + b"a" + bytes([0]),
        _p(body),
        ESC + b"!" + bytes([0x30]), # toplam çift boy: yarım genişlikte satır
        _p(_row("TOPLAM", _money(r["total_amount"]), LINE_WIDTH // 2)),
        ESC + b"!" + bytes([0x00]),
        _p(line),
        ESC + b"a" + bytes([1]),
        _p("MALI DEGERI YOKTUR - BILGI FISIDIR\n"),
        ESC + b"a" + bytes([0]),
        ESC + b"d" + bytes([6]),    # son satırlar bıçağı geçsin
        GS + b"V" + bytes([1]),
    ]
    return b"".join(parts)


@app.route("/api/patron/print", methods=["POST"])
def patron_print():
    username = current_owner()
    if not username:
        return jsonify({"error": "Giriş gerekli"}), 401
    data = request.json or {}
    report = _z_summary(data.get("period", "daily"), data.get("date"))
    ticket = build_z_ticket(report, username)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO print_queue (station, ticket_data, status) VALUES ('mutfak', ?, 'pending')",
            (base64.b64encode(ticket).decode("ascii"),)
        )
    return jsonify({"ok": True})


# Z Raporu hesap yönetimi — ana paneldeki "Z Raporu Hesapları" bölümü kullanır
@app.route("/api/owners", methods=["GET"])
def list_owners():
    with get_db() as conn:
        rows = conn.execute("SELECT id, username, display_name, created_at FROM owners ORDER BY username").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/owners", methods=["POST"])
def add_owner():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    display_name = (data.get("display_name") or "").strip() or None
    if len(username) < 3:
        return jsonify({"error": "Kullanıcı adı en az 3 karakter olmalı"}), 400
    if len(password) < 6:
        return jsonify({"error": "Şifre en az 6 karakter olmalı"}), 400
    try:
        with get_db() as conn:
            conn.execute("INSERT INTO owners (username, password_hash, display_name) VALUES (?, ?, ?)",
                         (username, generate_password_hash(password), display_name))
    except sqlite3.IntegrityError:
        return jsonify({"error": "Bu kullanıcı adı zaten var"}), 400
    return jsonify({"ok": True}), 201


@app.route("/api/owners/<int:owner_id>", methods=["PUT"])
def update_owner(owner_id):
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if username and len(username) < 3:
        return jsonify({"error": "Kullanıcı adı en az 3 karakter olmalı"}), 400
    if password and len(password) < 6:
        return jsonify({"error": "Şifre en az 6 karakter olmalı"}), 400
    try:
        with get_db() as conn:
            if username:
                conn.execute("UPDATE owners SET username=? WHERE id=?", (username, owner_id))
            if password:
                conn.execute("UPDATE owners SET password_hash=? WHERE id=?",
                             (generate_password_hash(password), owner_id))
            if "display_name" in data:
                conn.execute("UPDATE owners SET display_name=? WHERE id=?",
                             ((data.get("display_name") or "").strip() or None, owner_id))
    except sqlite3.IntegrityError:
        return jsonify({"error": "Bu kullanıcı adı zaten var"}), 400
    return jsonify({"ok": True})


@app.route("/api/owners/<int:owner_id>", methods=["DELETE"])
def delete_owner(owner_id):
    with get_db() as conn:
        conn.execute("DELETE FROM owners WHERE id=?", (owner_id,))
    return jsonify({"ok": True})


@app.route("/pizza")
def pizza_display():
    return render_template("pizza.html")

@app.route("/mutfak")
def mutfak_display():
    return render_template("mutfak.html")

@app.route("/adisyon/<int:order_id>")
def adisyon(order_id):
    with get_db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            return "Sipariş bulunamadı", 404
        items = conn.execute("SELECT * FROM order_items WHERE order_id=?", (order_id,)).fetchall()
    return render_template("adisyon.html", order=dict(order), items=[dict(i) for i in items])


# ── MENU ──────────────────────────────────────────────────────────────────────

@app.route("/api/menu", methods=["GET"])
def list_menu():
    with get_db() as conn:
        items = conn.execute("SELECT * FROM menu_items ORDER BY category, name").fetchall()
        cost_rows = conn.execute("""
            SELECT mii.menu_item_id AS id, SUM(mii.quantity * i.unit_cost) AS cost
            FROM menu_item_ingredients mii
            JOIN ingredients i ON i.id = mii.ingredient_id
            GROUP BY mii.menu_item_id
        """).fetchall()
    costs = {r["id"]: r["cost"] for r in cost_rows}
    result = []
    for r in items:
        item = dict(r)
        item["cost"] = round(costs.get(item["id"], 0) or 0, 2)
        result.append(item)
    return jsonify(result)


@app.route("/api/menu", methods=["POST"])
def add_menu_item():
    data = request.json
    name = data.get("name", "").strip()
    price = float(data.get("price", 0))
    category = data.get("category", "Genel").strip()
    if not name or price <= 0:
        return jsonify({"error": "Geçersiz veri"}), 400
    with get_db() as conn:
        cur = conn.execute("INSERT INTO menu_items (name, price, category) VALUES (?, ?, ?)", (name, price, category))
    return jsonify({"id": cur.lastrowid, "name": name, "price": price, "category": category}), 201


@app.route("/api/menu/<int:item_id>", methods=["PUT"])
def update_menu_item(item_id):
    data = request.json
    name = data.get("name", "").strip()
    price = float(data.get("price", 0))
    category = data.get("category", "Genel").strip()
    if not name or price <= 0:
        return jsonify({"error": "Geçersiz veri"}), 400
    with get_db() as conn:
        conn.execute("UPDATE menu_items SET name=?, price=?, category=? WHERE id=?", (name, price, category, item_id))
    return jsonify({"ok": True})


@app.route("/api/menu/<int:item_id>", methods=["DELETE"])
def delete_menu_item(item_id):
    with get_db() as conn:
        conn.execute("DELETE FROM menu_items WHERE id=?", (item_id,))
    return jsonify({"ok": True})


# ── MALZEMELER (MALİYET HESABI) ─────────────────────────────────────────────────

@app.route("/api/ingredients", methods=["GET"])
def list_ingredients():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM ingredients ORDER BY name").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/ingredients", methods=["POST"])
def add_ingredient():
    data = request.json
    name = data.get("name", "").strip()
    unit = data.get("unit", "kg").strip() or "kg"
    unit_cost = float(data.get("unit_cost", 0) or 0)
    if not name or unit_cost < 0:
        return jsonify({"error": "Geçersiz veri"}), 400
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO ingredients (name, unit, unit_cost) VALUES (?, ?, ?)",
            (name, unit, unit_cost)
        )
    return jsonify({"id": cur.lastrowid, "name": name, "unit": unit, "unit_cost": unit_cost}), 201


@app.route("/api/ingredients/<int:ing_id>", methods=["PUT"])
def update_ingredient(ing_id):
    data = request.json
    name = data.get("name", "").strip()
    unit = data.get("unit", "kg").strip() or "kg"
    unit_cost = float(data.get("unit_cost", 0) or 0)
    if not name or unit_cost < 0:
        return jsonify({"error": "Geçersiz veri"}), 400
    with get_db() as conn:
        conn.execute(
            "UPDATE ingredients SET name=?, unit=?, unit_cost=? WHERE id=?",
            (name, unit, unit_cost, ing_id)
        )
    return jsonify({"ok": True})


@app.route("/api/ingredients/<int:ing_id>", methods=["DELETE"])
def delete_ingredient(ing_id):
    with get_db() as conn:
        conn.execute("DELETE FROM ingredients WHERE id=?", (ing_id,))
    return jsonify({"ok": True})


@app.route("/api/menu/<int:item_id>/recipe", methods=["GET"])
def get_menu_recipe(item_id):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT mii.id, mii.ingredient_id, mii.quantity,
                   i.name AS ingredient_name, i.unit, i.unit_cost
            FROM menu_item_ingredients mii
            JOIN ingredients i ON i.id = mii.ingredient_id
            WHERE mii.menu_item_id = ?
            ORDER BY i.name
        """, (item_id,)).fetchall()
    result = []
    total_cost = 0.0
    for r in rows:
        row = dict(r)
        row["line_cost"] = round(row["quantity"] * row["unit_cost"], 2)
        total_cost += row["line_cost"]
        result.append(row)
    return jsonify({"items": result, "total_cost": round(total_cost, 2)})


@app.route("/api/menu/<int:item_id>/recipe", methods=["PUT"])
def update_menu_recipe(item_id):
    data = request.json
    lines = data.get("items", [])
    with get_db() as conn:
        conn.execute("DELETE FROM menu_item_ingredients WHERE menu_item_id=?", (item_id,))
        for line in lines:
            ingredient_id = line.get("ingredient_id")
            quantity = float(line.get("quantity", 0) or 0)
            if ingredient_id and quantity > 0:
                conn.execute(
                    "INSERT INTO menu_item_ingredients (menu_item_id, ingredient_id, quantity) VALUES (?, ?, ?)",
                    (item_id, ingredient_id, quantity)
                )
    return jsonify({"ok": True})


# ── GİDERLER (Metro / Macrocenter vb. alışverişler) ─────────────────────────────

@app.route("/api/expenses", methods=["GET"])
def list_expenses():
    date_from = request.args.get("date_from")
    date_to   = request.args.get("date_to")
    with get_db() as conn:
        if date_from and date_to:
            rows = conn.execute(
                "SELECT * FROM expenses WHERE expense_date BETWEEN ? AND ? ORDER BY expense_date DESC, id DESC",
                (date_from, date_to)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM expenses ORDER BY expense_date DESC, id DESC LIMIT 200").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/expenses", methods=["POST"])
def add_expense():
    data = request.json
    expense_date = data.get("expense_date", "").strip()
    vendor       = data.get("vendor", "").strip()
    category     = data.get("category", "Genel").strip() or "Genel"
    description  = data.get("description", "").strip()
    amount       = float(data.get("amount", 0) or 0)
    if not expense_date or amount <= 0:
        return jsonify({"error": "Tarih ve tutar gerekli"}), 400
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO expenses (expense_date, vendor, category, description, amount) VALUES (?, ?, ?, ?, ?)",
            (expense_date, vendor, category, description, amount)
        )
    return jsonify({"id": cur.lastrowid}), 201


@app.route("/api/expenses/<int:exp_id>", methods=["DELETE"])
def delete_expense(exp_id):
    with get_db() as conn:
        row = conn.execute("SELECT receipt_image FROM expenses WHERE id=?", (exp_id,)).fetchone()
        conn.execute("DELETE FROM expenses WHERE id=?", (exp_id,))
    if row and row["receipt_image"]:
        try:
            os.remove(os.path.join(RECEIPT_UPLOAD_DIR, row["receipt_image"]))
        except OSError:
            pass
    return jsonify({"ok": True})


@app.route("/api/expenses/<int:exp_id>/receipt", methods=["POST"])
def upload_expense_receipt(exp_id):
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "Dosya bulunamadı"}), 400
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_RECEIPT_EXT:
        return jsonify({"error": "Desteklenmeyen dosya türü (png, jpg, webp, pdf olmalı)"}), 400
    with get_db() as conn:
        row = conn.execute("SELECT receipt_image FROM expenses WHERE id=?", (exp_id,)).fetchone()
        if not row:
            return jsonify({"error": "Gider bulunamadı"}), 404
        if row["receipt_image"]:
            try:
                os.remove(os.path.join(RECEIPT_UPLOAD_DIR, row["receipt_image"]))
            except OSError:
                pass
        filename = f"{exp_id}_{secrets.token_hex(4)}.{ext}"
        file.save(os.path.join(RECEIPT_UPLOAD_DIR, filename))
        conn.execute("UPDATE expenses SET receipt_image=? WHERE id=?", (filename, exp_id))
    return jsonify({"ok": True, "receipt_image": filename})


# ── FİŞ YAZICI AYARLARI ────────────────────────────────────────────────────────

@app.route("/api/settings/printers", methods=["GET"])
def get_printer_settings():
    return jsonify({
        "mutfak_ip":   get_setting("printer_mutfak_ip", "") or "",
        "pizza_ip":    get_setting("printer_pizza_ip", "") or "",
        "enabled":     get_setting("printer_enabled", "0") == "1",
        "agent_token": get_or_create_agent_token(),
    })


@app.route("/api/settings/printers", methods=["PUT"])
def update_printer_settings():
    data = request.json
    set_setting("printer_mutfak_ip", (data.get("mutfak_ip") or "").strip())
    set_setting("printer_pizza_ip",  (data.get("pizza_ip") or "").strip())
    set_setting("printer_enabled",   "1" if data.get("enabled") else "0")
    return jsonify({"ok": True})


@app.route("/api/settings/printers/test", methods=["POST"])
def test_printer():
    data = request.json
    station = (data.get("station") or "").strip()
    if station not in ("mutfak", "pizza"):
        return jsonify({"ok": False, "error": "Geçersiz istasyon"}), 400
    enqueue_ticket(station, "TEST FİŞİ", "—", "", [{"name": "Test ürünü", "quantity": 1}], "Bu bir test fişidir")
    return jsonify({"ok": True, "queued": True})


# ── PRINT AGENT (dükkândaki köprü programı buradan besleniyor) ─────────────────

@app.route("/api/print-agent/printers", methods=["GET"])
def agent_get_printers():
    if not check_agent_token():
        return jsonify({"error": "Yetkisiz"}), 401
    return jsonify({
        "mutfak_ip": get_setting("printer_mutfak_ip", "") or "",
        "pizza_ip":  get_setting("printer_pizza_ip", "") or "",
    })


@app.route("/api/print-agent/jobs", methods=["GET"])
def agent_get_jobs():
    if not check_agent_token():
        return jsonify({"error": "Yetkisiz"}), 401
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, station, ticket_data FROM print_queue WHERE status='pending' ORDER BY id LIMIT 20"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/print-agent/jobs/<int:job_id>/ack", methods=["POST"])
def agent_ack_job(job_id):
    if not check_agent_token():
        return jsonify({"error": "Yetkisiz"}), 401
    with get_db() as conn:
        conn.execute("UPDATE print_queue SET status='done' WHERE id=?", (job_id,))
    return jsonify({"ok": True})


# ── KITCHEN DISPLAY ───────────────────────────────────────────────────────────

@app.route("/api/kitchen/orders")
def kitchen_orders():
    station = request.args.get("station", "pizza")
    with get_db() as conn:
        rows = conn.execute("""
            SELECT o.id, o.table_number, o.waiter,
                   datetime(o.created_at, '+3 hours') AS created_at,
                   o.notes,
                   oi.item_name, oi.quantity,
                   COALESCE(m.category, '') AS category
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.id
            LEFT JOIN menu_items m ON m.id = oi.menu_item_id
            WHERE o.status = 'Aktif'
            ORDER BY o.created_at, o.id
        """).fetchall()

    orders = {}
    for row in rows:
        r   = dict(row)
        cat = r["category"]
        if station == "pizza" and not is_pizza_category(cat):
            continue
        if station == "mutfak" and is_pizza_category(cat):
            continue
        oid = r["id"]
        if oid not in orders:
            orders[oid] = {
                "id":           oid,
                "table_number": r["table_number"],
                "waiter":       r["waiter"],
                "created_at":   r["created_at"],
                "notes":        r["notes"],
                "items":        [],
            }
        orders[oid]["items"].append({"name": r["item_name"], "quantity": r["quantity"]})

    return jsonify(list(orders.values()))


# ── ORDERS ────────────────────────────────────────────────────────────────────

@app.route("/api/orders/active-by-table")
def active_order_by_table():
    table = request.args.get("table", "").strip()
    if not table:
        return jsonify(None)
    with get_db() as conn:
        order = conn.execute(
            "SELECT * FROM orders WHERE table_number=? AND status='Aktif' ORDER BY id DESC LIMIT 1",
            (table,)
        ).fetchone()
        if not order:
            return jsonify(None)
        o = dict(order)
        items = conn.execute("SELECT * FROM order_items WHERE order_id=?", (o["id"],)).fetchall()
        o["items"] = [dict(i) for i in items]
    return jsonify(o)


@app.route("/api/orders/<int:order_id>/items", methods=["POST"])
def add_items_to_order(order_id):
    data  = request.json
    items = data.get("items", [])
    notes = data.get("notes", "").strip()
    if not items:
        return jsonify({"error": "En az bir ürün gerekli"}), 400
    extra = sum(i["price"] * i["quantity"] for i in items)
    with get_db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=? AND status='Aktif'", (order_id,)).fetchone()
        if not order:
            return jsonify({"error": "Sipariş bulunamadı veya kapalı"}), 404
        for item in items:
            conn.execute(
                "INSERT INTO order_items (order_id, menu_item_id, item_name, item_price, quantity) VALUES (?, ?, ?, ?, ?)",
                (order_id, item.get("menu_item_id"), item["name"], item["price"], item["quantity"])
            )
            if item.get("menu_item_id"):
                conn.execute(
                    "UPDATE stock_items SET quantity = quantity - ? WHERE menu_item_id = ?",
                    (item["quantity"], item["menu_item_id"])
                )
        conn.execute("UPDATE orders SET total = total + ? WHERE id=?", (extra, order_id))
        if notes:
            existing = order["notes"] or ""
            new_notes = (existing + " / " + notes).strip(" /")
            conn.execute("UPDATE orders SET notes=? WHERE id=?", (new_notes, order_id))
        menu_categories = {r["id"]: r["category"] for r in conn.execute("SELECT id, category FROM menu_items")}
    route_and_print_new_items(order["table_number"], order["waiter"], items, notes, menu_categories)
    return jsonify({"ok": True, "added": extra})


@app.route("/api/orders/<int:order_id>/items/<int:item_id>", methods=["PUT"])
def update_order_item_quantity(order_id, item_id):
    """Açık adisyondaki ürünün adedini değiştirir (0 = ürünü çıkar); tutar ve stok güncellenir,
    çıkarılan adet için mutfağa/pizza tezgahına İPTAL fişi gider."""
    try:
        new_qty = int((request.json or {}).get("quantity"))
    except (TypeError, ValueError):
        return jsonify({"error": "Geçersiz adet"}), 400
    if new_qty < 0:
        return jsonify({"error": "Geçersiz adet"}), 400
    with get_db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=? AND status='Aktif'", (order_id,)).fetchone()
        if not order:
            return jsonify({"error": "Sipariş bulunamadı veya kapalı"}), 404
        item = conn.execute("SELECT * FROM order_items WHERE id=? AND order_id=?", (item_id, order_id)).fetchone()
        if not item:
            return jsonify({"error": "Ürün bulunamadı"}), 404
        delta = new_qty - item["quantity"]
        if delta == 0:
            return jsonify({"ok": True})
        if new_qty == 0:
            conn.execute("DELETE FROM order_items WHERE id=?", (item_id,))
        else:
            conn.execute("UPDATE order_items SET quantity=? WHERE id=?", (new_qty, item_id))
        conn.execute("UPDATE orders SET total = MAX(0, total + ?) WHERE id=?", (delta * item["item_price"], order_id))
        if item["menu_item_id"]:
            conn.execute("UPDATE stock_items SET quantity = quantity - ? WHERE menu_item_id = ?",
                         (delta, item["menu_item_id"]))
        new_total = conn.execute("SELECT total FROM orders WHERE id=?", (order_id,)).fetchone()["total"]
        # Bungalov hesabına yazılmış siparişse oradaki tutarı da güncelle
        conn.execute("UPDATE bungalov_charges SET amount=? WHERE order_id=?", (new_total, order_id))
        menu_categories = {r["id"]: r["category"] for r in conn.execute("SELECT id, category FROM menu_items")}
    if delta < 0:
        removed = [{"menu_item_id": item["menu_item_id"], "name": item["item_name"], "quantity": -delta}]
        route_and_print_new_items(order["table_number"], order["waiter"], removed, "", menu_categories, cancel=True)
    return jsonify({"ok": True, "total": new_total})


@app.route("/api/orders", methods=["GET"])
def list_orders():
    # ?date=YYYY-MM-DD → açık siparişlerin hepsi + o güne ait kapanmış siparişler (Z raporuyla aynı gün tanımı)
    date = request.args.get("date")
    with get_db() as conn:
        if date:
            orders = conn.execute(
                """SELECT * FROM orders WHERE status='Aktif' OR DATE(created_at, '+3 hours') = ?
                   ORDER BY created_at DESC""", (date,)
            ).fetchall()
        else:
            orders = conn.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
        result = []
        for o in orders:
            order = dict(o)
            items = conn.execute("SELECT * FROM order_items WHERE order_id=?", (o["id"],)).fetchall()
            order["items"] = [dict(i) for i in items]
            result.append(order)
    return jsonify(result)


@app.route("/api/orders", methods=["POST"])
def create_order():
    data = request.json
    table       = data.get("table_number", "").strip()
    notes       = data.get("notes", "").strip()
    waiter      = data.get("waiter", "").strip()
    bungalov_no = data.get("bungalov_no")
    items       = data.get("items", [])
    if not table or not items:
        return jsonify({"error": "Masa numarası ve en az bir ürün gerekli"}), 400
    total = sum(i["price"] * i["quantity"] for i in items)
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO orders (table_number, status, notes, total, waiter) VALUES (?, 'Aktif', ?, ?, ?)",
            (table, notes, total, waiter)
        )
        order_id = cur.lastrowid
        for item in items:
            conn.execute(
                "INSERT INTO order_items (order_id, menu_item_id, item_name, item_price, quantity) VALUES (?, ?, ?, ?, ?)",
                (order_id, item.get("menu_item_id"), item["name"], item["price"], item["quantity"])
            )
            if item.get("menu_item_id"):
                conn.execute(
                    "UPDATE stock_items SET quantity = quantity - ? WHERE menu_item_id = ?",
                    (item["quantity"], item["menu_item_id"])
                )
        if bungalov_no:
            account = conn.execute(
                "SELECT id FROM bungalov_accounts WHERE bungalov_no=? AND status='Açık' ORDER BY id DESC LIMIT 1",
                (bungalov_no,)
            ).fetchone()
            if account:
                conn.execute(
                    "INSERT INTO bungalov_charges (account_id, description, amount, order_id) VALUES (?, ?, ?, ?)",
                    (account["id"], f"Restoran — Masa {table}", total, order_id)
                )
        menu_categories = {r["id"]: r["category"] for r in conn.execute("SELECT id, category FROM menu_items")}
    route_and_print_new_items(table, waiter, items, notes, menu_categories)
    return jsonify({"id": order_id, "total": total}), 201


@app.route("/api/orders/<int:order_id>/table", methods=["PUT"])
def change_order_table(order_id):
    data  = request.json
    table = data.get("table_number", "").strip()
    if not table:
        return jsonify({"error": "Masa numarası boş olamaz"}), 400
    with get_db() as conn:
        conn.execute("UPDATE orders SET table_number=? WHERE id=? AND status='Aktif'", (table, order_id))
    return jsonify({"ok": True})


@app.route("/api/orders/<int:order_id>/status", methods=["PUT"])
def update_order_status(order_id):
    data = request.json
    status = data.get("status")
    payment_method = data.get("payment_method")
    discount = float(data.get("discount") or 0)
    if status not in ["Aktif", "Ödendi", "İkram"]:
        return jsonify({"error": "Geçersiz durum"}), 400
    with get_db() as conn:
        if status == "İkram":
            # Ücret alınmadan kapatılır (patron misafiri); satış/kasa toplamlarına girmez, Z raporunda ayrı görünür
            note = (data.get("ikram_note") or "").strip() or None
            conn.execute(
                "UPDATE orders SET status='İkram', payment_method='İkram', ikram_note=?, closed_at=datetime('now') WHERE id=?",
                (note, order_id))
        elif status == "Ödendi":
            if discount > 0:
                order = conn.execute("SELECT total FROM orders WHERE id=?", (order_id,)).fetchone()
                new_total = max(0, (order["total"] or 0) - discount)
                conn.execute(
                    "UPDATE orders SET status=?, payment_method=?, discount=?, total=?, closed_at=datetime('now') WHERE id=?",
                    (status, payment_method, discount, new_total, order_id))
            elif payment_method:
                conn.execute(
                    "UPDATE orders SET status=?, payment_method=?, closed_at=datetime('now') WHERE id=?",
                    (status, payment_method, order_id))
            else:
                conn.execute(
                    "UPDATE orders SET status=?, closed_at=datetime('now') WHERE id=?",
                    (status, order_id))
        else:
            if payment_method:
                conn.execute("UPDATE orders SET status=?, payment_method=? WHERE id=?",
                             (status, payment_method, order_id))
            else:
                conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    return jsonify({"ok": True})


@app.route("/api/orders/<int:order_id>/payment", methods=["PUT"])
def update_order_payment(order_id):
    """Ödenmiş siparişin sadece ödeme yöntemini düzeltir (yanlış işaretleme için);
    kapanış saati ve tutar değişmez."""
    import re
    method = ((request.json or {}).get("payment_method") or "").strip()
    karma = re.fullmatch(r"Nakit: ₺[\d.,]+ / Kart: ₺[\d.,]+", method)
    if method not in ("Nakit", "Kredi Kartı") and not karma:
        return jsonify({"error": "Geçersiz ödeme yöntemi"}), 400
    with get_db() as conn:
        order = conn.execute("SELECT status FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            return jsonify({"error": "Sipariş bulunamadı"}), 404
        if order["status"] != "Ödendi":
            return jsonify({"error": "Sadece ödenmiş siparişin ödemesi düzenlenebilir"}), 400
        conn.execute("UPDATE orders SET payment_method=? WHERE id=?", (method, order_id))
    return jsonify({"ok": True})


@app.route("/api/orders/<int:order_id>", methods=["DELETE"])
def delete_order(order_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT menu_item_id, quantity FROM order_items WHERE order_id=?", (order_id,)
        ).fetchall()
        for row in rows:
            if row["menu_item_id"]:
                conn.execute(
                    "UPDATE stock_items SET quantity = quantity + ? WHERE menu_item_id = ?",
                    (row["quantity"], row["menu_item_id"])
                )
        conn.execute("DELETE FROM orders WHERE id=?", (order_id,))
    return jsonify({"ok": True})


# ── STOCK ─────────────────────────────────────────────────────────────────────

@app.route("/api/stock", methods=["GET"])
def list_stock():
    with get_db() as conn:
        items = conn.execute("SELECT * FROM stock_items ORDER BY name").fetchall()
    return jsonify([dict(r) for r in items])


@app.route("/api/stock", methods=["POST"])
def add_stock_item():
    data = request.json
    name        = data.get("name", "").strip()
    quantity    = float(data.get("quantity", 0))
    unit        = data.get("unit", "adet").strip() or "adet"
    min_qty     = float(data.get("min_quantity", 0))
    menu_item_id = data.get("menu_item_id") or None
    if not name:
        return jsonify({"error": "Ürün adı zorunlu"}), 400
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO stock_items (name, quantity, unit, min_quantity, menu_item_id) VALUES (?, ?, ?, ?, ?)",
            (name, quantity, unit, min_qty, menu_item_id)
        )
    return jsonify({"id": cur.lastrowid}), 201


@app.route("/api/stock/<int:item_id>", methods=["PUT"])
def update_stock_item(item_id):
    data = request.json
    name        = data.get("name", "").strip()
    quantity    = float(data.get("quantity", 0))
    unit        = data.get("unit", "adet").strip() or "adet"
    min_qty     = float(data.get("min_quantity", 0))
    menu_item_id = data.get("menu_item_id") or None
    if not name:
        return jsonify({"error": "Ürün adı zorunlu"}), 400
    with get_db() as conn:
        conn.execute(
            "UPDATE stock_items SET name=?, quantity=?, unit=?, min_quantity=?, menu_item_id=? WHERE id=?",
            (name, quantity, unit, min_qty, menu_item_id, item_id)
        )
    return jsonify({"ok": True})


@app.route("/api/stock/<int:item_id>", methods=["DELETE"])
def delete_stock_item(item_id):
    with get_db() as conn:
        conn.execute("DELETE FROM stock_items WHERE id=?", (item_id,))
    return jsonify({"ok": True})


@app.route("/api/stock/<int:item_id>/add", methods=["POST"])
def add_stock_quantity(item_id):
    data   = request.json
    amount = float(data.get("amount", 0))
    if amount <= 0:
        return jsonify({"error": "Geçersiz miktar"}), 400
    with get_db() as conn:
        conn.execute("UPDATE stock_items SET quantity = quantity + ? WHERE id=?", (amount, item_id))
        item = conn.execute("SELECT * FROM stock_items WHERE id=?", (item_id,)).fetchone()
    return jsonify(dict(item))


# ── BUNGALOV ──────────────────────────────────────────────────────────────────

@app.route("/api/bungalov")
def list_bungalov():
    result = []
    with get_db() as conn:
        for no in range(1, 5):
            account = conn.execute(
                "SELECT * FROM bungalov_accounts WHERE bungalov_no=? AND status='Açık' ORDER BY id DESC LIMIT 1",
                (no,)
            ).fetchone()
            if account:
                charges = conn.execute(
                    "SELECT * FROM bungalov_charges WHERE account_id=? ORDER BY created_at",
                    (account["id"],)
                ).fetchall()
                a = dict(account)
                a["charges"] = [dict(c) for c in charges]
                a["total"]   = sum(c["amount"] for c in charges)
                result.append({"no": no, "account": a})
            else:
                result.append({"no": no, "account": None})
    return jsonify(result)


@app.route("/api/bungalov/<int:no>/open", methods=["POST"])
def open_bungalov_account(no):
    if no not in range(1, 5):
        return jsonify({"error": "Geçersiz bungalov"}), 400
    data         = request.json
    guest_name   = data.get("guest_name", "").strip()
    checkin_date = data.get("checkin_date", "").strip()
    notes        = data.get("notes", "").strip()
    if not guest_name or not checkin_date:
        return jsonify({"error": "Misafir adı ve giriş tarihi zorunlu"}), 400
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM bungalov_accounts WHERE bungalov_no=? AND status='Açık'", (no,)
        ).fetchone()
        if existing:
            return jsonify({"error": "Bu bungalov için zaten açık hesap var"}), 400
        cur = conn.execute(
            "INSERT INTO bungalov_accounts (bungalov_no, guest_name, checkin_date, notes) VALUES (?, ?, ?, ?)",
            (no, guest_name, checkin_date, notes)
        )
    return jsonify({"id": cur.lastrowid}), 201


@app.route("/api/bungalov/account/<int:account_id>")
def get_bungalov_account(account_id):
    with get_db() as conn:
        account = conn.execute(
            "SELECT * FROM bungalov_accounts WHERE id=?", (account_id,)
        ).fetchone()
        if not account:
            return jsonify({"error": "Hesap bulunamadı"}), 404
        charges = conn.execute(
            "SELECT * FROM bungalov_charges WHERE account_id=? ORDER BY created_at",
            (account_id,)
        ).fetchall()
        a = dict(account)
        a["charges"] = [dict(c) for c in charges]
        a["total"]   = sum(c["amount"] for c in charges)
    return jsonify(a)


@app.route("/api/bungalov/account/<int:account_id>/charge", methods=["POST"])
def add_bungalov_charge(account_id):
    data        = request.json
    description = data.get("description", "").strip()
    amount      = float(data.get("amount", 0))
    if not description or amount <= 0:
        return jsonify({"error": "Açıklama ve tutar zorunlu"}), 400
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO bungalov_charges (account_id, description, amount) VALUES (?, ?, ?)",
            (account_id, description, amount)
        )
    return jsonify({"id": cur.lastrowid}), 201


@app.route("/api/bungalov/account/<int:account_id>/menu-items", methods=["POST"])
def add_bungalov_menu_items(account_id):
    """Menüden seçilen ürünleri bungalov cari hesabına yazar; restorandan sipariş olduğu için
    mutfak/pizza fişi basılır ve stoktan düşülür."""
    items = (request.json or {}).get("items") or []
    items = [i for i in items if int(i.get("quantity") or 0) > 0]
    if not items:
        return jsonify({"error": "En az bir ürün seçin"}), 400
    with get_db() as conn:
        account = conn.execute("SELECT * FROM bungalov_accounts WHERE id=? AND status='Açık'", (account_id,)).fetchone()
        if not account:
            return jsonify({"error": "Açık hesap bulunamadı"}), 404
        menu = {r["id"]: r for r in conn.execute("SELECT id, name, price, category FROM menu_items")}
        lines = []
        for i in items:
            m = menu.get(i.get("menu_item_id"))
            if not m:
                return jsonify({"error": "Menüde olmayan ürün"}), 400
            qty = int(i["quantity"])
            # Fiyat menüden alınır (tarayıcıdan gelen fiyata güvenilmez)
            conn.execute(
                "INSERT INTO bungalov_charges (account_id, description, amount) VALUES (?, ?, ?)",
                (account_id, f"{qty} × {m['name']}", m["price"] * qty)
            )
            conn.execute("UPDATE stock_items SET quantity = quantity - ? WHERE menu_item_id = ?", (qty, m["id"]))
            lines.append({"menu_item_id": m["id"], "name": m["name"], "quantity": qty})
        menu_categories = {mid: r["category"] for mid, r in menu.items()}
    unit = LODGING_UNITS[account["bungalov_no"] - 1] if 1 <= account["bungalov_no"] <= len(LODGING_UNITS) else f"Bungalov {account['bungalov_no']}"
    route_and_print_new_items(unit, "", lines, f"Misafir: {account['guest_name']}", menu_categories)
    return jsonify({"ok": True})


@app.route("/api/bungalov/charge/<int:charge_id>", methods=["DELETE"])
def delete_bungalov_charge(charge_id):
    with get_db() as conn:
        conn.execute("DELETE FROM bungalov_charges WHERE id=?", (charge_id,))
    return jsonify({"ok": True})


@app.route("/api/bungalov/account/<int:account_id>/checkout", methods=["PUT"])
def checkout_bungalov(account_id):
    data           = request.json
    payment_method = data.get("payment_method", "").strip()
    checkout_date  = data.get("checkout_date", "").strip()
    if not payment_method or not checkout_date:
        return jsonify({"error": "Ödeme yöntemi ve çıkış tarihi zorunlu"}), 400
    if payment_method not in ("Nakit", "Kredi Kartı", "Havale", "Karma"):
        return jsonify({"error": "Geçersiz ödeme yöntemi"}), 400
    with _lodging_db() as conn:
        account = conn.execute("SELECT * FROM bungalov_accounts WHERE id=? AND status='Açık'", (account_id,)).fetchone()
        if not account:
            return jsonify({"error": "Açık hesap bulunamadı"}), 404
        # Restoranda ayrıca ödenmiş siparişler kasaya zaten girdi; onlar hariç tahsil edilen tutar
        total = conn.execute(
            """SELECT COALESCE(SUM(ch.amount), 0) FROM bungalov_charges ch
               LEFT JOIN orders o ON o.id = ch.order_id
               WHERE ch.account_id=? AND (o.id IS NULL OR o.status NOT IN ('Ödendi', 'İkram'))""",
            (account_id,)
        ).fetchone()[0]
        if payment_method == "Karma":
            try:
                nakit = float(data.get("nakit_amount") or 0)
            except (TypeError, ValueError):
                nakit = -1
            if not 0 <= nakit <= total:
                return jsonify({"error": "Nakit tutarı 0 ile toplam arasında olmalı"}), 400
            parts = [("Nakit", nakit), ("Kredi Kartı", total - nakit)]
        else:
            parts = [(payment_method, total)]
        conn.execute(
            "UPDATE bungalov_accounts SET status='Kapandı', payment_method=?, checkout_date=? WHERE id=?",
            (payment_method, checkout_date, account_id)
        )
        # Tahsilat, ödemenin alındığı günün (şu an) kasasına konaklama tahsilatı olarak yazılır
        no = account["bungalov_no"]
        unit = LODGING_UNITS[no - 1] if 1 <= no <= len(LODGING_UNITS) else f"Bungalov {no}"
        for method, amount in parts:
            if amount > 0:
                conn.execute(
                    "INSERT INTO lodging_payments (unit, guest_name, amount, payment_method, notes) VALUES (?, ?, ?, ?, ?)",
                    (unit, account["guest_name"], round(amount, 2), method, "Hesap kapanışı")
                )
    return jsonify({"ok": True})


# ── KONAKLAMA ÖDEMELERİ (misafirin kalan konaklama ücreti tahsilatı) ──────────

LODGING_UNITS = ["Bungalov 1", "Bungalov 2", "Dağ Evi", "Kütük Ev"]
LODGING_SCHEMA = """
    CREATE TABLE IF NOT EXISTS lodging_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unit TEXT NOT NULL,
        guest_name TEXT,
        amount REAL NOT NULL,
        payment_method TEXT NOT NULL,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
"""


def _lodging_db():
    conn = get_db()
    conn.executescript(LODGING_SCHEMA)
    return conn


@app.route("/api/lodging-payments", methods=["GET"])
def list_lodging_payments():
    import datetime as dt
    date = request.args.get("date", dt.date.today().isoformat())
    with _lodging_db() as conn:
        rows = conn.execute(
            "SELECT * FROM lodging_payments WHERE DATE(created_at, '+3 hours') = ? ORDER BY created_at DESC",
            (date,)
        ).fetchall()
    return jsonify({"units": LODGING_UNITS, "payments": [dict(r) for r in rows]})


@app.route("/api/lodging-payments", methods=["POST"])
def add_lodging_payment():
    data = request.json or {}
    unit = (data.get("unit") or "").strip()
    method = (data.get("payment_method") or "").strip()
    try:
        amount = float(data.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0
    if unit not in LODGING_UNITS:
        return jsonify({"error": "Konaklama yeri seçin"}), 400
    if amount <= 0:
        return jsonify({"error": "Tutar girin"}), 400
    if method not in ("Nakit", "Kredi Kartı", "Havale"):
        return jsonify({"error": "Ödeme yöntemi seçin"}), 400
    with _lodging_db() as conn:
        cur = conn.execute(
            "INSERT INTO lodging_payments (unit, guest_name, amount, payment_method, notes) VALUES (?, ?, ?, ?, ?)",
            (unit, (data.get("guest_name") or "").strip() or None, amount, method,
             (data.get("notes") or "").strip() or None)
        )
    return jsonify({"ok": True, "id": cur.lastrowid}), 201


@app.route("/api/lodging-payments/<int:pid>", methods=["DELETE"])
def delete_lodging_payment(pid):
    with _lodging_db() as conn:
        conn.execute("DELETE FROM lodging_payments WHERE id=?", (pid,))
    return jsonify({"ok": True})


# ── KASA DEVRİ (gün sonunda ertesi gün için kasada bırakılan bozuk para) ─────

CASH_FLOAT_SCHEMA = """
    CREATE TABLE IF NOT EXISTS cash_floats (
        float_date TEXT PRIMARY KEY,
        amount REAL NOT NULL,
        notes TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
"""


def _cash_db():
    conn = get_db()
    conn.executescript(CASH_FLOAT_SCHEMA)
    return conn


@app.route("/api/cash-floats", methods=["GET"])
def list_cash_floats():
    with _cash_db() as conn:
        rows = conn.execute("SELECT * FROM cash_floats ORDER BY float_date DESC LIMIT 30").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/cash-floats", methods=["PUT"])
def save_cash_float():
    data = request.json or {}
    date = (data.get("date") or "").strip()
    try:
        datetime.strptime(date, "%Y-%m-%d")
        amount = float(data.get("amount"))
    except (TypeError, ValueError):
        return jsonify({"error": "Tarih ve tutar girin"}), 400
    if amount < 0:
        return jsonify({"error": "Tutar eksi olamaz"}), 400
    with _cash_db() as conn:
        conn.execute(
            """INSERT INTO cash_floats (float_date, amount, notes, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(float_date) DO UPDATE SET amount=excluded.amount, notes=excluded.notes,
                                                     updated_at=CURRENT_TIMESTAMP""",
            (date, amount, (data.get("notes") or "").strip() or None)
        )
    return jsonify({"ok": True})


@app.route("/api/cash-floats/<date>", methods=["DELETE"])
def delete_cash_float(date):
    with _cash_db() as conn:
        conn.execute("DELETE FROM cash_floats WHERE float_date=?", (date,))
    return jsonify({"ok": True})


def _cash_float_for_range(date_from, date_to):
    """Açılış = aralıktan önceki son devir; kapanış = aralığın son gününde bırakılan."""
    with _cash_db() as conn:
        opening = conn.execute(
            "SELECT float_date, amount FROM cash_floats WHERE float_date < ? ORDER BY float_date DESC LIMIT 1",
            (date_from,)
        ).fetchone()
        closing = conn.execute(
            "SELECT float_date, amount FROM cash_floats WHERE float_date = ?", (date_to,)
        ).fetchone()
    return {
        "float_opening":      opening["amount"] if opening else None,
        "float_opening_date": opening["float_date"] if opening else None,
        "float_closing":      closing["amount"] if closing else None,
    }


def _lodging_for_range(date_from, date_to):
    with _lodging_db() as conn:
        rows = conn.execute(
            """SELECT unit, guest_name, amount, payment_method FROM lodging_payments
               WHERE DATE(created_at, '+3 hours') BETWEEN ? AND ? ORDER BY created_at""",
            (date_from, date_to)
        ).fetchall()
    nakit = sum(r["amount"] for r in rows if r["payment_method"] == "Nakit")
    kart = sum(r["amount"] for r in rows if r["payment_method"] == "Kredi Kartı")
    havale = sum(r["amount"] for r in rows if r["payment_method"] == "Havale")
    return {
        "lodging_payments": [dict(r) for r in rows],
        "lodging_total":    round(nakit + kart + havale, 2),
        "lodging_nakit":    round(nakit, 2),
        "lodging_kart":     round(kart, 2),
        "lodging_havale":   round(havale, 2),
    }


@app.route("/api/bungalov/history")
def bungalov_history():
    with get_db() as conn:
        accounts = conn.execute(
            "SELECT * FROM bungalov_accounts WHERE status='Kapandı' ORDER BY checkout_date DESC LIMIT 50"
        ).fetchall()
        result = []
        for a in accounts:
            acc = dict(a)
            charges = conn.execute(
                "SELECT * FROM bungalov_charges WHERE account_id=?", (a["id"],)
            ).fetchall()
            acc["total"]        = sum(c["amount"] for c in charges)
            acc["charge_count"] = len(charges)
            result.append(acc)
    return jsonify(result)


# ── REPORT ────────────────────────────────────────────────────────────────────

def _report_for_range(date_from, date_to):
    import re
    with get_db() as conn:
        items = conn.execute("""
            SELECT oi.item_name,
                   SUM(oi.quantity)                 AS total_qty,
                   SUM(oi.item_price * oi.quantity) AS total_amount
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            WHERE DATE(o.created_at, '+3 hours') BETWEEN ? AND ? AND o.status = 'Ödendi'
            GROUP BY oi.item_name ORDER BY total_qty DESC
        """, (date_from, date_to)).fetchall()

        waiters = conn.execute("""
            SELECT COALESCE(NULLIF(waiter,''), '—') AS waiter,
                   COUNT(*)                          AS order_count,
                   COALESCE(SUM(total), 0)           AS total_amount
            FROM orders
            WHERE DATE(created_at, '+3 hours') BETWEEN ? AND ? AND status = 'Ödendi'
            GROUP BY waiter ORDER BY total_amount DESC
        """, (date_from, date_to)).fetchall()

        totals = conn.execute("""
            SELECT COUNT(*) AS order_count, COALESCE(SUM(total), 0) AS total_amount
            FROM orders
            WHERE DATE(created_at, '+3 hours') BETWEEN ? AND ? AND status = 'Ödendi'
        """, (date_from, date_to)).fetchone()

        paid_orders = conn.execute("""
            SELECT payment_method, total FROM orders
            WHERE DATE(created_at, '+3 hours') BETWEEN ? AND ? AND status = 'Ödendi'
        """, (date_from, date_to)).fetchall()

        ikram_orders = conn.execute("""
            SELECT table_number, waiter, ikram_note, total, created_at FROM orders
            WHERE DATE(created_at, '+3 hours') BETWEEN ? AND ? AND status = 'İkram'
            ORDER BY created_at
        """, (date_from, date_to)).fetchall()

        expense_total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE expense_date BETWEEN ? AND ?",
            (date_from, date_to)
        ).fetchone()["total"]

    def _tr_float(s):
        return float(s.replace('.', '').replace(',', '.')) if s else 0.0

    nakit_total = kart_total = 0.0
    for o in paid_orders:
        m = o["payment_method"] or ""
        t = o["total"] or 0
        if m == "Nakit":
            nakit_total += t
        elif m == "Kredi Kartı":
            kart_total += t
        elif "Nakit:" in m and "Kart:" in m:
            nm = re.search(r'Nakit:\s*₺([\d.,]+)', m)
            km = re.search(r'/\s*Kart:\s*₺([\d.,]+)', m)
            nakit_total += _tr_float(nm.group(1) if nm else None)
            kart_total  += _tr_float(km.group(1) if km else None)

    total_amount = totals["total_amount"] or 0
    return {
        "date_from":     date_from,
        "date_to":       date_to,
        "items":         [dict(r) for r in items],
        "waiters":       [dict(r) for r in waiters],
        "total_orders":  totals["order_count"] or 0,
        "total_amount":  total_amount,
        "nakit_total":   round(nakit_total, 2),
        "kart_total":    round(kart_total, 2),
        "expense_total": round(expense_total or 0, 2),
        "ikram_orders":  [dict(r) for r in ikram_orders],
        "ikram_count":   len(ikram_orders),
        "ikram_total":   round(sum(r["total"] or 0 for r in ikram_orders), 2),
        "net_amount":    round(total_amount - (expense_total or 0), 2),
    }


if __name__ == "__main__":
    init_db()
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"\n{'='*55}")
    print(f"  Ana Bilgisayar  : http://localhost:5000")
    print(f"  Tablet / Telefon: http://{local_ip}:5000")
    print(f"  Garson Tableti  : http://{local_ip}:5000/garson")
    print(f"  Pizza Tezgahı   : http://{local_ip}:5000/pizza")
    print(f"  Mutfak Ekranı   : http://{local_ip}:5000/mutfak")
    print(f"{'='*55}\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
