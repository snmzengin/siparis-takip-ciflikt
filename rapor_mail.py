"""Rapor maili: dönem hesapları, HTML mail tasarımı ve SMTP ile gönderme.

Veriyi toplamaz — app.py'deki build_report_data() hazırlayıp buraya verir.
Böylece bu dosya veritabanına / Flask'a bağımlı değil.
"""
import datetime as dt
import html as _html
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

KINDS = {"weekly": "Haftalık", "monthly": "Aylık", "half": "6 Aylık", "yearly": "Yıllık"}
SEND_HOUR = 8  # dönem bittikten sonraki gün, Türkiye saatiyle 08:00'den sonra gönderilir

TR_MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


# ── DÖNEMLER ─────────────────────────────────────────────────────────────────

def last_period(kind, today):
    """Bugünden önce tamamlanmış en son dönem: (anahtar, başlangıç, bitiş) — tarihler dahil."""
    if kind == "weekly":  # pazartesi–pazar
        start = today - dt.timedelta(days=today.weekday() + 7)
        end = start + dt.timedelta(days=6)
        iso = start.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}", start, end
    if kind == "monthly":
        end = today.replace(day=1) - dt.timedelta(days=1)
        return f"{end.year}-{end.month:02d}", end.replace(day=1), end
    if kind == "half":
        if today.month >= 7:
            return f"{today.year}-H1", dt.date(today.year, 1, 1), dt.date(today.year, 6, 30)
        return f"{today.year - 1}-H2", dt.date(today.year - 1, 7, 1), dt.date(today.year - 1, 12, 31)
    if kind == "yearly":
        y = today.year - 1
        return str(y), dt.date(y, 1, 1), dt.date(y, 12, 31)
    raise ValueError(kind)


def previous_period(kind, start):
    """Karşılaştırma için bir önceki aynı uzunlukta dönem."""
    return last_period(kind, start)[1:]


def due_at(end):
    """Dönemin raporunun gönderilebileceği an (Türkiye saati)."""
    return dt.datetime.combine(end + dt.timedelta(days=1), dt.time(SEND_HOUR))


def period_label(start, end):
    if start == end:
        return f"{start.day} {TR_MONTHS[start.month - 1]} {start.year}"
    if start.year != end.year:
        return f"{start.day} {TR_MONTHS[start.month - 1]} {start.year} – {end.day} {TR_MONTHS[end.month - 1]} {end.year}"
    if start.month != end.month:
        if start.day == 1 and (end + dt.timedelta(days=1)).day == 1:  # tam aylar (6 aylık / yıllık)
            if start.month == 1 and end.month == 12:
                return str(start.year)
            return f"{TR_MONTHS[start.month - 1]} – {TR_MONTHS[end.month - 1]} {end.year}"
        return f"{start.day} {TR_MONTHS[start.month - 1]} – {end.day} {TR_MONTHS[end.month - 1]} {end.year}"
    if start.day == 1 and (end + dt.timedelta(days=1)).day == 1:
        return f"{TR_MONTHS[start.month - 1]} {start.year}"
    return f"{start.day}–{end.day} {TR_MONTHS[start.month - 1]} {end.year}"


# ── HTML ─────────────────────────────────────────────────────────────────────
# E-posta istemcileri CSS dosyası/flex desteklemez: tablo + satır içi stil kullanılır.

C = {"ink": "#211C12", "ink2": "#4A4132", "ink3": "#6B6250", "line": "#E7E0CF", "bg": "#F8F3E6",
     "card": "#FFFFFF", "olive": "#1E3B26", "accent": "#2F6B3F", "nakit": "#C0673A", "kart": "#3E6FB0",
     "gold": "#B9852E", "down": "#B4432F"}


def tl(v):
    return "₺" + f"{round(v or 0):,}".replace(",", ".")


def e(s):
    return _html.escape(str(s if s is not None else ""))


def _pct(a, b):
    return round(a * 100 / b) if b else 0


def _kpi(label, value, sub="", color=None):
    return (f'<td style="padding:12px 14px;background:{C["card"]};border:1px solid {C["line"]};border-radius:10px;vertical-align:top;width:33%">'
            f'<div style="font-size:12px;color:{C["ink3"]}">{e(label)}</div>'
            f'<div style="font-size:21px;font-weight:700;color:{color or C["ink"]};margin-top:4px">{e(value)}</div>'
            f'<div style="font-size:12px;color:{C["ink3"]};margin-top:3px">{sub}</div></td>')


def _kpi_grid(cells, per_row=3):
    rows = [cells[i:i + per_row] for i in range(0, len(cells), per_row)]
    body = "".join("<tr>" + "".join(r) + "".join("<td></td>" for _ in range(per_row - len(r))) + "</tr>" for r in rows)
    return f'<table role="presentation" width="100%" cellspacing="8" cellpadding="0" style="border-collapse:separate">{body}</table>'


def _section(title, inner, hint=""):
    return (f'<tr><td style="padding:22px 24px 4px"><div style="font-size:17px;font-weight:700;color:{C["olive"]}">{e(title)}</div>'
            + (f'<div style="font-size:12px;color:{C["ink3"]};margin-top:2px">{e(hint)}</div>' if hint else "")
            + f'</td></tr><tr><td style="padding:6px 16px 0">{inner}</td></tr>')


def _table(headers, rows, align=None, empty="Kayıt yok"):
    if not rows:
        return f'<div style="padding:10px 8px;color:{C["ink3"]};font-size:13px">{e(empty)}</div>'
    align = align or ["left"] + ["right"] * (len(headers) - 1)
    th = "".join(f'<th style="text-align:{a};padding:7px 8px;font-size:12px;color:{C["ink3"]};font-weight:600;border-bottom:2px solid {C["line"]}">{e(h)}</th>'
                 for h, a in zip(headers, align))
    tr = "".join("<tr>" + "".join(f'<td style="text-align:{a};padding:7px 8px;font-size:13px;color:{C["ink"]};border-bottom:1px solid {C["line"]}">{c}</td>'
                                  for c, a in zip(r, align)) + "</tr>" for r in rows)
    head = f"<tr>{th}</tr>" if any(headers) else ""  # başlıksız tablo (etiket — tutar listeleri)
    return f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse">{head}{tr}</table>'


def _lines(pairs):
    """Etiket — tutar satırları (renkli nokta isteğe bağlı)."""
    rows = []
    for label, value, color in pairs:
        dot = f'<span style="display:inline-block;width:9px;height:9px;border-radius:3px;background:{color};margin-right:8px"></span>' if color else ""
        rows.append([f"{dot}{label}", f"<b>{value}</b>"])
    return _table(["", ""], rows)


def render_report(d):
    """d: app.build_report_data() çıktısı → (konu, html, düz metin)."""
    kind_name = KINDS[d["kind"]]
    label = period_label(d["start"], d["end"])
    r, k, x = d["restaurant"], d["lodging"], d["expenses"]
    lodging_total = k["total"] if k.get("ok") else 0
    income = r["total_amount"] + lodging_total
    net = income - x["total"]

    if r["prev_total"] > 0:
        ch = _pct(r["total_amount"] - r["prev_total"], r["prev_total"])
        delta = f'<span style="color:{C["accent"] if ch >= 0 else C["down"]};font-weight:600">{"▲" if ch >= 0 else "▼"} %{abs(ch)}</span> önceki döneme göre'
    else:
        delta = "önceki dönemde satış yok"

    parts = []
    # Özet
    parts.append(_section("Özet", _kpi_grid([
        _kpi("Toplam gelir", tl(income), "restoran + konaklama", C["olive"]),
        _kpi("Restoran satışı", tl(r["total_amount"]), delta),
        _kpi("Konaklama geliri", tl(lodging_total) if k.get("ok") else "—",
             f'%{k["occupancy"]} doluluk' if k.get("ok") else e(k.get("error", ""))),
        _kpi("Giderler", tl(x["total"]), f'{x["count"]} kayıt', C["nakit"]),
        _kpi("Net", tl(net), "gelir − gider", C["accent"] if net >= 0 else C["down"]),
        _kpi("Kapanan adisyon", str(r["total_orders"]),
             f'ortalama {tl(r["total_amount"] / r["total_orders"])}' if r["total_orders"] else "—"),
    ])))

    # Ay ay döküm (6 aylık / yıllık)
    if d.get("monthly"):
        rows = [[e(m["label"]), tl(m["restaurant"]), tl(m["lodging"]) if m["lodging"] is not None else "—",
                 tl(m["expenses"]), f'<b>{tl(m["net"])}</b>'] for m in d["monthly"]]
        parts.append(_section("Ay ay döküm", _table(["Ay", "Restoran", "Konaklama", "Gider", "Net"], rows)))

    # Restoran
    other = f'<br><span style="color:{C["ink3"]}">Diğer: {tl(r["other_total"])}</span>' if r["other_total"] > 0.5 else ""
    parts.append(_section("Restoran", _lines([
        ("Nakit", tl(r["nakit_total"]), C["nakit"]),
        ("Kredi kartı", tl(r["kart_total"]) + other, C["kart"]),
        (f'Kahvaltı servisi <span style="color:{C["ink3"]}">({r["breakfast_qty"]} porsiyon)</span>', tl(r["breakfast_total"]), C["gold"]),
        ("Akşam servisi", tl(r["dinner_total"]), C["accent"]),
        (f'Pizza <span style="color:{C["ink3"]}">({r["pizza_qty"]} adet)</span>', tl(r["pizza_total"]), None),
        (f'Meşrubat <span style="color:{C["ink3"]}">({r["mesrubat_qty"]} adet)</span>', tl(r["mesrubat_total"]), None),
        (f'Çay &amp; kahve <span style="color:{C["ink3"]}">({r["sicak_qty"]} adet)</span>', tl(r["sicak_total"]), None),
        (f'İkram — ücret alınmayan <span style="color:{C["ink3"]}">({r["ikram_count"]} adisyon)</span>', tl(r["ikram_total"]), None),
    ]), "Kapanan adisyonlar · servis ayrımı menü fiyatlarıyla"))

    waiters = [[e(w["waiter"]), str(w["order_count"]), f'%{_pct(w["total_amount"], r["total_amount"])}', f'<b>{tl(w["total_amount"])}</b>']
               for w in r["waiters"]]
    parts.append(_section("Garson bazlı satış", _table(["Garson", "Adisyon", "Pay", "Tutar"], waiters, empty="Satış yok")))

    items = [[str(i + 1), e(it["item_name"]), str(it["total_qty"]), tl(it["total_amount"])] for i, it in enumerate(r["items"])]
    parts.append(_section("Ürün bazlı satış", _table(["#", "Ürün", "Adet", "Tutar"], items, ["left", "left", "right", "right"], "Satış yok"),
                          f'{len(r["items"])} farklı ürün · adede göre'))

    # Giderler
    cats = [[e(c["category"] or "Diğer"), str(c["count"]), f'%{_pct(c["total"], x["total"])}', f'<b>{tl(c["total"])}</b>'] for c in x["categories"]]
    inner = _table(["Kategori", "Kayıt", "Pay", "Tutar"], cats, empty="Gider yok")
    if x.get("rows"):
        inner += '<div style="height:10px"></div>' + _table(
            ["Tarih", "Satıcı", "Açıklama", "Tutar"],
            [[e(g["expense_date"][8:10] + "." + g["expense_date"][5:7]), e(g["vendor"] or ""), e(g["description"] or g["category"] or ""), tl(g["amount"])]
             for g in x["rows"]], ["left", "left", "left", "right"])
    parts.append(_section("Giderler", inner, f'Toplam {tl(x["total"])}'))

    # Konaklama (Google E-Tablolar)
    if k.get("ok"):
        houses = [[e(h["unit"]), str(h["stays"]), f'{h["busy"]} / {h["capacity"]}', f'%{h["occupancy"]}', f'<b>{tl(h["total"])}</b>']
                  for h in k["houses"]]
        inner = _kpi_grid([
            _kpi("Toplam kazanç", tl(k["total"]), f'{k["stays"]} konaklama · {k["nights"]} gece', C["olive"]),
            _kpi("Önden alınan", tl(k["prepaid"]), f'toplamın %{_pct(k["prepaid"], k["total"])}\'i'),
            _kpi("Kapıda alınan", tl(k["door_paid"]), "misafir geldiğinde"),
            _kpi("Kalan ödenecek", tl(k["left"]) if k["left"] else "—", "henüz gelmemiş misafirler", C["nakit"]),
            _kpi("Doluluk", f'%{k["occupancy"]}', f'{k["busy"]} / {k["capacity"]} gece dolu'),
            _kpi("Gece başı gelir", tl(k["total"] / k["nights"]) if k["nights"] else "—", "ortalama"),
        ]) + '<div style="height:6px"></div>' + _table(["Ev", "Konaklama", "Dolu gece", "Doluluk", "Kazanç"], houses)
        if k.get("list"):
            inner += '<div style="height:10px"></div>' + _table(
                ["Tarih", "Ev", "Misafir", "Gece", "Tutar"],
                [[e(s["dates"]), e(s["unit"]), e(s["guest"]), str(s["nights"]),
                  (tl(s["total"]) if s["known"] else "—")
                  + (f' <span style="color:{C["down"]};font-weight:700" title="Tablodaki tutar hatalı görünüyor">⚠</span>' if s.get("mismatch") else "")]
                 for s in k["list"]],
                ["left", "left", "left", "right", "right"])
        hint = "Google E-Tablolar'daki konaklama tablosundan · ay sınırını aşan konaklama giriş yaptığı döneme yazılır"
        if k["unknown"]:
            hint += f' · {k["unknown"]} konaklamada tutar yok'
        if k.get("suspect"):
            hint += f' · ⚠ {k["suspect"]} konaklamada tablodaki tutar hatalı görünüyor (örn. "16.0000₺"), tabloda kontrol edin'
        if k.get("missing"):
            hint += f' · tabloda sekmesi olmayan aylar hesaba katılmadı: {", ".join(k["missing"])}'
        parts.append(_section("Konaklama", inner, hint))
    else:
        parts.append(_section("Konaklama", f'<div style="padding:10px 8px;color:{C["down"]};font-size:13px">{e(k.get("error", "Konaklama verisi alınamadı"))}</div>'))

    # Kasa
    parts.append(_section("Kasa", _lines([
        ("Nakit (restoran + konaklama tahsilatı)", tl(r["kasa_nakit"]), C["nakit"]),
        ("Kredi kartı / POS", tl(r["kasa_kart"]), C["kart"]),
        ("Havale (konaklama)", tl(r["kasa_havale"]), C["gold"]),
        ("Panelden girilen konaklama tahsilatı", tl(r["lodging_total"]), None),
    ]), "POS ve kasa ile karşılaştırmak için"))

    subject = f"{kind_name} Rapor · {label} · Sapanca Çiftlik"
    html = f"""<!DOCTYPE html><html lang="tr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:{C['bg']};font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:{C['ink']}">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{C['bg']}"><tr><td align="center" style="padding:20px 10px">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:680px;background:#FCFAF1;border-radius:16px;border:1px solid {C['line']}">
<tr><td style="padding:22px 24px;background:{C['olive']};border-radius:16px 16px 0 0">
  <div style="font-size:12px;letter-spacing:2px;color:#D9A441;font-weight:600">SAPANCA ÇİFTLİK RESTORAN</div>
  <div style="font-size:24px;font-weight:700;color:#FCFAF1;margin-top:4px">{e(kind_name)} Rapor</div>
  <div style="font-size:15px;color:#E7E0CF;margin-top:2px">{e(label)}</div>
</td></tr>
{''.join(parts)}
<tr><td style="padding:22px 24px;font-size:12px;color:{C['ink3']}">Bu rapor otomatik gönderildi ({e(d['generated'])}). Alıcı ve rapor ayarları: Z Raporu › Ayarlar › Rapor Maili.</td></tr>
</table></td></tr></table></body></html>"""

    text = (f"Sapanca Çiftlik Restoran — {kind_name} Rapor ({label})\n\n"
            f"Toplam gelir: {tl(income)}\nRestoran satışı: {tl(r['total_amount'])}\n"
            f"Konaklama geliri: {tl(lodging_total) if k.get('ok') else '—'}\nGiderler: {tl(x['total'])}\nNet: {tl(net)}\n\n"
            "Ayrıntılar için maili HTML görünümünde açın.")
    return subject, html, text


# ── GÖNDERME ─────────────────────────────────────────────────────────────────

def send_mail(cfg, to_list, subject, html, text):
    """cfg: host, port, user, password. Hata olursa anlaşılır Türkçe mesajla RuntimeError fırlatır."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("Sapanca Çiftlik Restoran", cfg["user"]))
    msg["To"] = ", ".join(to_list)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    port = int(cfg.get("port") or 587)
    ctx = ssl.create_default_context()
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(cfg["host"], port, timeout=30, context=ctx)
        else:
            server = smtplib.SMTP(cfg["host"], port, timeout=30)
            server.starttls(context=ctx)
        with server:
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError("Gönderen hesabın kullanıcı adı ya da uygulama şifresi hatalı "
                           "(Gmail'de normal şifre çalışmaz, 16 haneli uygulama şifresi gerekir)")
    except smtplib.SMTPRecipientsRefused:
        raise RuntimeError("Alıcı mail adresi kabul edilmedi — adresi kontrol edin")
    except (OSError, smtplib.SMTPException) as ex:
        raise RuntimeError(f"Mail sunucusuna bağlanılamadı ({type(ex).__name__}: {ex})")
