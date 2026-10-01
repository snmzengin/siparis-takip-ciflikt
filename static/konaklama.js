/* Konaklama hesapları — panel (Giriş / Çıkış › Ev Ev) ve Z Raporu (Konaklama) aynı rakamı
   göstersin diye ikisi de bu dosyayı kullanır. Veri: /api/konaklama */

/* Tablodaki ödeme yazısından tutarlar: "16.000₺ Ödendi" + "16.000₺ Kapıda / 32.000₺ TOPLAM"
   → önden 16.000, kapıda 16.000, toplam 32.000. "TAMAMI ÖDENDİ" ise toplam = önden alınan. */
function konaklamaMoney(s) {
  if (s._money) return s._money;
  const txt = `${s.paid} ${s.balance}`.replace(/İ/g, "i").replace(/I/g, "ı").toLowerCase();
  const num = word => {
    const m = txt.match(new RegExp(`(\\d[\\d.,]*)\\s*(?:₺|tl)?\\s*${word}`));
    return m ? parseFloat(m[1].replace(/\./g, "").replace(",", ".")) || 0 : null;
  };
  let prepaid = num("ödendi"), due = num("kap[ıi]da"), total = num("toplam");
  // Üçü de yazılıysa tablonun kendi içinde tutması gerekir (örn. 15.000 + 18.000 ≠ 38.000)
  const mismatch = total != null && prepaid != null && due != null && Math.abs(total - prepaid - due) >= 1;
  if (due == null && s.fully_paid) due = 0;
  if (total == null && (prepaid != null || due != null)) total = (prepaid || 0) + (due || 0);
  if (due == null && total != null && prepaid != null) due = Math.max(total - prepaid, 0);
  if (prepaid == null && total != null && due != null) prepaid = Math.max(total - due, 0);
  return (s._money = { prepaid: prepaid || 0, due: due || 0, total: total || 0, known: total != null, mismatch });
}

const _kDay = s => Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)) / 86400000;

function konaklamaNextMonth(month) { // "2026-09" → "2026-10-01"
  const [y, m] = month.split("-").map(Number);
  return m === 12 ? `${y + 1}-01-01` : `${y}-${String(m + 1).padStart(2, "0")}-01`;
}

/* Bir ayın istatistikleri. unit boşsa tüm evler.
   Para: ay sınırını aşan konaklama giriş yaptığı aya yazılır → toplam = önden + kapıda.
   Doluluk: o ayın içine düşen geceler sayılır (sarkan konaklamanın gecesi her iki aya da düşer). */
function konaklamaMonthStats(data, unit, month) {
  const first = `${month}-01`, after = konaklamaNextMonth(month), today = data.today;
  const units = unit ? [unit] : data.units;
  const mine = data.stays.filter(s => units.includes(s.unit));
  const overlapping = mine.filter(s => s.checkin < after && s.checkout > first);
  const started = overlapping.filter(s => s.checkin >= first);
  const dim = _kDay(after) - _kDay(first);
  const busy = overlapping.reduce((n, s) =>
    n + Math.max(0, _kDay(s.checkout < after ? s.checkout : after) - _kDay(s.checkin > first ? s.checkin : first)), 0);
  const sum = (list, f) => list.reduce((n, s) => n + f(konaklamaMoney(s)), 0);
  const isFuture = s => s.checkin >= today; // henüz gelmemiş (bugün gelecekler dahil)
  return {
    overlapping, started, dim, busy,
    capacity: dim * units.length,
    occupancy: dim ? Math.round(busy * 100 / (dim * units.length)) : 0,
    startedNights: started.reduce((n, s) => n + s.nights, 0),
    total:   sum(started, m => m.total),
    prepaid: sum(started, m => m.prepaid),
    left:    sum(started.filter(isFuture), m => m.due),            // kalan ödenecek
    doorPaid: sum(started.filter(s => !isFuture(s)), m => m.due),  // kapıda alınmış (misafir geldi)
    unknown: started.filter(s => !konaklamaMoney(s).known).length,
  };
}

function konaklamaMonths(data) {
  // Eski önbellekte "months" yoksa konaklamalardan çıkar
  return data.months && data.months.length ? data.months : [...new Set(data.stays.map(s => s.checkin.slice(0, 7)))].sort();
}
