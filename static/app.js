/* ── STATE ──────────────────────────────────────────────────────────────── */
let menuItems   = [];
let orders      = [];
let stockItems  = [];
let ingredients = [];
let expenses    = [];
let selectedItems         = {};
let activeFilter          = "Aktif";
let pendingPaymentOrderId = null;
let pendingPaymentTotal   = 0;
let pendingRestockId      = null;
const BUNGALOV_NAMES = { 1: "Bungalov 1", 2: "Bungalov 2", 3: "Dağ Evi", 4: "Kütük Ev" };

let bungalovData          = [];
let activeBungalovNo      = null;
let activeBungalovAccId   = null;
let pendingCheckoutAccId  = null;

const GARDEN_LAYOUT = [
  { section: "Sağ",  tables: ["sağ 1","sağ 2","sağ 3","sağ 4","sağ 5","sağ 6","sağ 7"] },
  { section: "Orta", tables: ["orta 1","orta 2","orta 3","orta 4","orta 5","orta 6"] },
  { section: "Sol",  tables: ["sol 1","sol 2","sol 3","sol 4","sol 5","sol 6"] },
  { section: "Salon", tables: ["salon 1","salon 2","salon 3","salon 4","salon 5","salon 6","salon 7","salon 8"] },
  { section: "Loca",  tables: ["geyikli loca"] },
];

const TAB_NAMES = {
  orders:      "Siparişler",
  garden:      "Bahçe Haritası",
  bungalov:    "Bungalov",
  stock:       "Stok",
  menu:        "Menü Yönetimi",
  ingredients: "Malzemeler",
  expenses:    "Giderler",
  waiters:     "Garsonlar",
  printers:    "Fiş Yazıcıları",
  owners:      "Z Raporu Hesapları",
  lodging:     "Konaklama Ödemeleri",
  cashfloat:   "Kasa Devri",
};

/* ── INIT ────────────────────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".nav-item").forEach(btn => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
  document.querySelectorAll(".filter-btn").forEach(btn => {
    btn.addEventListener("click", () => setFilter(btn.dataset.filter));
  });
  document.querySelectorAll(".filter-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.filter === activeFilter);
  });

  document.getElementById("expense-date").value = todayLocal();

  updateClock();
  setInterval(updateClock, 1000);

  loadMenu();
  loadOrders();
  loadStock();
  loadBungalov();
  setInterval(loadOrders, 5000);
});

function updateClock() {
  const now = new Date();
  const cl  = document.getElementById("sidebar-clock");
  const dt  = document.getElementById("sidebar-date");
  if (cl) cl.textContent = now.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
  if (dt) dt.textContent = now.toLocaleDateString("tr-TR", { weekday: "long", day: "numeric", month: "long" });
}

/* ── TABS ────────────────────────────────────────────────────────────────── */
function switchTab(tab) {
  document.querySelectorAll(".tab").forEach(s => s.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
  document.getElementById(`tab-${tab}`).classList.add("active");
  const navItem = document.querySelector(`.nav-item[data-tab="${tab}"]`);
  if (navItem) navItem.classList.add("active");
  const titleEl = document.getElementById("mobile-title");
  if (titleEl) titleEl.textContent = TAB_NAMES[tab] || tab;
  // Mobilde sidebar'ı kapat
  document.getElementById("sidebar").classList.remove("open");
  document.getElementById("sidebar-overlay").classList.add("hidden");
  if (tab === "stock")       renderStockAlerts();
  if (tab === "bungalov")    loadBungalov();
  if (tab === "waiters")     loadWaiters();
  if (tab === "printers")    loadPrinterSettings();
  if (tab === "owners")      loadOwners();
  if (tab === "lodging")     loadLodgingPayments();
  if (tab === "cashfloat")   loadCashFloats();
  if (tab === "ingredients") loadIngredients();
  if (tab === "expenses")    loadExpenses();
}

function toggleSidebar() {
  const sidebar  = document.getElementById("sidebar");
  const overlay  = document.getElementById("sidebar-overlay");
  const isOpen   = sidebar.classList.contains("open");
  sidebar.classList.toggle("open", !isOpen);
  overlay.classList.toggle("hidden", isOpen);
}

/* ── FILTER ──────────────────────────────────────────────────────────────── */
function setFilter(filter) {
  activeFilter = filter;
  document.querySelectorAll(".filter-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.filter === filter);
  });
  renderOrders();
}

// Ödenen siparişler gün gün listelenir; null = bugünü takip et (gece yarısı kendiliğinden ilerler)
let ordersDate = null;

function currentOrdersDate() { return ordersDate || todayLocal(); }

function setOrdersDate(date) {
  if (!date) return;
  ordersDate = date === todayLocal() ? null : date;
  loadOrders();
}

function shiftOrdersDate(days) {
  const d = new Date(currentOrdersDate() + "T12:00:00");
  d.setDate(d.getDate() + days);
  setOrdersDate(d.toLocaleDateString("sv"));
}

/* ── API HELPERS ─────────────────────────────────────────────────────────── */
async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  return res.json();
}

/* ── MENU ────────────────────────────────────────────────────────────────── */
async function loadMenu() {
  menuItems = await api("/api/menu");
  renderMenuTable();
  populateStockMenuLink();
}

function renderMenuTable() {
  const tbody = document.getElementById("menu-tbody");
  if (!menuItems.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:#aaa;padding:40px">Henüz ürün yok</td></tr>`;
    return;
  }
  tbody.innerHTML = menuItems.map(item => {
    const cost   = item.cost || 0;
    const profit = item.price - cost;
    const margin = cost > 0 ? (profit / item.price * 100) : null;
    return `
    <tr>
      <td>${esc(item.name)}</td>
      <td>${esc(item.category)}</td>
      <td>₺${item.price.toFixed(2)}</td>
      <td>${cost > 0 ? `₺${cost.toFixed(2)}` : `<span class="muted">—</span>`}</td>
      <td>${cost > 0 ? `₺${profit.toFixed(2)}` : `<span class="muted">—</span>`}</td>
      <td>${margin !== null ? `<span class="${margin < 30 ? 'margin-low' : 'margin-ok'}">%${margin.toFixed(0)}</span>` : `<span class="muted">—</span>`}</td>
      <td>
        <button class="btn sm" onclick="openRecipeModal(${item.id}, '${esc(item.name).replace(/'/g, "\\'")}', ${item.price})">Reçete</button>
        <button class="btn sm" onclick='openMenuModal(${JSON.stringify(item)})'>Düzenle</button>
        <button class="btn sm danger" onclick="deleteMenuItem(${item.id})">Sil</button>
      </td>
    </tr>
  `;
  }).join("");
}

function openMenuModal(item = null) {
  document.getElementById("menu-modal-title").textContent = item ? "Ürün Düzenle" : "Ürün Ekle";
  document.getElementById("menu-edit-id").value    = item ? item.id   : "";
  document.getElementById("menu-name").value       = item ? item.name : "";
  document.getElementById("menu-category").value   = item ? item.category : "";
  document.getElementById("menu-price").value      = item ? item.price : "";
  showModal("menu-modal");
}

function closeMenuModal() { hideModal("menu-modal"); }

async function saveMenuItem() {
  const id   = document.getElementById("menu-edit-id").value;
  const body = {
    name:     document.getElementById("menu-name").value.trim(),
    category: document.getElementById("menu-category").value.trim() || "Genel",
    price:    parseFloat(document.getElementById("menu-price").value),
  };
  if (!body.name || !body.price) return alert("Ürün adı ve fiyat zorunludur.");
  if (id) {
    await api(`/api/menu/${id}`, { method: "PUT", body: JSON.stringify(body) });
  } else {
    await api("/api/menu", { method: "POST", body: JSON.stringify(body) });
  }
  closeMenuModal();
  loadMenu();
}

async function deleteMenuItem(id) {
  if (!confirm("Bu ürünü silmek istiyor musunuz?")) return;
  await api(`/api/menu/${id}`, { method: "DELETE" });
  loadMenu();
}

/* ── MALZEMELER ──────────────────────────────────────────────────────────── */
async function loadIngredients() {
  ingredients = await api("/api/ingredients");
  renderIngredientsTable();
}

function renderIngredientsTable() {
  const tbody = document.getElementById("ingredients-tbody");
  if (!tbody) return;
  if (!ingredients.length) {
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;color:#aaa;padding:40px">Henüz malzeme yok</td></tr>`;
    return;
  }
  tbody.innerHTML = ingredients.map(ing => `
    <tr>
      <td>${esc(ing.name)}</td>
      <td>${esc(ing.unit)}</td>
      <td>₺${ing.unit_cost.toFixed(2)}</td>
      <td>
        <button class="btn sm" onclick='openIngredientModal(${JSON.stringify(ing)})'>Düzenle</button>
        <button class="btn sm danger" onclick="deleteIngredient(${ing.id})">Sil</button>
      </td>
    </tr>
  `).join("");
}

function openIngredientModal(ing = null) {
  document.getElementById("ingredient-modal-title").textContent = ing ? "Malzeme Düzenle" : "Malzeme Ekle";
  document.getElementById("ingredient-edit-id").value  = ing ? ing.id : "";
  document.getElementById("ingredient-name").value      = ing ? ing.name : "";
  document.getElementById("ingredient-unit").value      = ing ? ing.unit : "kg";
  document.getElementById("ingredient-unit-cost").value = ing ? ing.unit_cost : "";
  showModal("ingredient-modal");
}

function closeIngredientModal() { hideModal("ingredient-modal"); }

async function saveIngredient() {
  const id   = document.getElementById("ingredient-edit-id").value;
  const body = {
    name:      document.getElementById("ingredient-name").value.trim(),
    unit:      document.getElementById("ingredient-unit").value,
    unit_cost: parseFloat(document.getElementById("ingredient-unit-cost").value),
  };
  if (!body.name || isNaN(body.unit_cost) || body.unit_cost < 0) return alert("Malzeme adı ve birim fiyat zorunludur.");
  if (id) {
    await api(`/api/ingredients/${id}`, { method: "PUT", body: JSON.stringify(body) });
  } else {
    await api("/api/ingredients", { method: "POST", body: JSON.stringify(body) });
  }
  closeIngredientModal();
  loadIngredients();
}

async function deleteIngredient(id) {
  if (!confirm("Bu malzemeyi silmek istiyor musunuz? Kullanıldığı reçetelerden de kaldırılacak.")) return;
  await api(`/api/ingredients/${id}`, { method: "DELETE" });
  loadIngredients();
}

/* ── ÜRÜN REÇETESİ ───────────────────────────────────────────────────────── */
async function openRecipeModal(menuItemId, itemName, itemPrice) {
  if (!ingredients.length) await loadIngredients();
  document.getElementById("recipe-modal-title").textContent = `Reçete — ${itemName}`;
  document.getElementById("recipe-menu-item-id").value = menuItemId;
  document.getElementById("recipe-menu-item-id").dataset.price = itemPrice;
  document.getElementById("recipe-lines").innerHTML = "";

  if (!ingredients.length) {
    alert("Önce Malzemeler sekmesinden en az bir malzeme eklemelisin.");
    return;
  }

  const recipe = await api(`/api/menu/${menuItemId}/recipe`);
  if (recipe.items.length) {
    recipe.items.forEach(line => addRecipeLine(line.ingredient_id, line.quantity));
  } else {
    addRecipeLine();
  }
  recalcRecipeTotal();
  showModal("recipe-modal");
}

function closeRecipeModal() { hideModal("recipe-modal"); }

function addRecipeLine(ingredientId = null, quantity = null) {
  const wrap = document.getElementById("recipe-lines");
  const row = document.createElement("div");
  row.className = "recipe-line";
  const options = ingredients.map(ing =>
    `<option value="${ing.id}" ${ing.id === ingredientId ? "selected" : ""}>${esc(ing.name)} (₺${ing.unit_cost.toFixed(2)}/${esc(ing.unit)})</option>`
  ).join("");
  row.innerHTML = `
    <select class="recipe-line-ingredient" onchange="recalcRecipeTotal()">${options}</select>
    <input class="recipe-line-qty" type="number" min="0" step="0.001" placeholder="miktar" value="${quantity !== null ? quantity : ""}" oninput="recalcRecipeTotal()" />
    <button class="btn sm danger" onclick="this.parentElement.remove(); recalcRecipeTotal()">Sil</button>
  `;
  wrap.appendChild(row);
}

function recalcRecipeTotal() {
  let total = 0;
  document.querySelectorAll("#recipe-lines .recipe-line").forEach(row => {
    const ingId = parseInt(row.querySelector(".recipe-line-ingredient").value, 10);
    const qty   = parseFloat(row.querySelector(".recipe-line-qty").value) || 0;
    const ing   = ingredients.find(i => i.id === ingId);
    if (ing) total += ing.unit_cost * qty;
  });
  document.getElementById("recipe-total-cost").textContent = `₺${total.toFixed(2)}`;
}

async function saveRecipe() {
  const menuItemId = document.getElementById("recipe-menu-item-id").value;
  const items = [];
  document.querySelectorAll("#recipe-lines .recipe-line").forEach(row => {
    const ingredient_id = parseInt(row.querySelector(".recipe-line-ingredient").value, 10);
    const quantity      = parseFloat(row.querySelector(".recipe-line-qty").value) || 0;
    if (ingredient_id && quantity > 0) items.push({ ingredient_id, quantity });
  });
  await api(`/api/menu/${menuItemId}/recipe`, { method: "PUT", body: JSON.stringify({ items }) });
  closeRecipeModal();
  loadMenu();
}

/* ── GİDERLER ────────────────────────────────────────────────────────────── */
async function loadExpenses() {
  expenses = await api("/api/expenses");
  renderExpensesTable();
}

function renderExpensesTable() {
  const tbody = document.getElementById("expenses-tbody");
  const badge = document.getElementById("expense-total-badge");
  if (!tbody) return;
  if (!expenses.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:#aaa;padding:40px">Henüz gider kaydı yok</td></tr>`;
    if (badge) badge.textContent = "";
    return;
  }
  const total = expenses.reduce((sum, e) => sum + e.amount, 0);
  if (badge) badge.textContent = `Toplam: ₺${total.toLocaleString("tr-TR")}`;
  tbody.innerHTML = expenses.map(e => `
    <tr>
      <td>${new Date(e.expense_date + "T00:00:00").toLocaleDateString("tr-TR")}</td>
      <td>${esc(e.vendor || "—")}</td>
      <td>${esc(e.category)}</td>
      <td>${esc(e.description || "—")}</td>
      <td>₺${e.amount.toLocaleString("tr-TR")}</td>
      <td>${e.receipt_image
          ? `<a href="/static/uploads/expenses/${encodeURIComponent(e.receipt_image)}" target="_blank" class="receipt-link">📎 Görüntüle</a>`
          : `<span class="muted">—</span>`}</td>
      <td><button class="btn sm danger" onclick="deleteExpense(${e.id})">Sil</button></td>
    </tr>
  `).join("");
}

async function addExpense() {
  const body = {
    expense_date: document.getElementById("expense-date").value || todayLocal(),
    vendor:       document.getElementById("expense-vendor").value.trim(),
    category:     document.getElementById("expense-category").value,
    description:  document.getElementById("expense-description").value.trim(),
    amount:       parseFloat(document.getElementById("expense-amount").value),
  };
  if (!body.amount || body.amount <= 0) return alert("Tutar zorunludur.");
  const created = await api("/api/expenses", { method: "POST", body: JSON.stringify(body) });

  const fileInput = document.getElementById("expense-receipt");
  if (fileInput.files.length) {
    const fd = new FormData();
    fd.append("file", fileInput.files[0]);
    const res = await fetch(`/api/expenses/${created.id}/receipt`, { method: "POST", body: fd });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(`Gider kaydedildi ama fatura yüklenemedi: ${err.error || "bilinmeyen hata"}`);
    }
  }

  document.getElementById("expense-vendor").value = "";
  document.getElementById("expense-description").value = "";
  document.getElementById("expense-amount").value = "";
  fileInput.value = "";
  loadExpenses();
}

async function deleteExpense(id) {
  if (!confirm("Bu gider kaydını silmek istiyor musunuz?")) return;
  await api(`/api/expenses/${id}`, { method: "DELETE" });
  loadExpenses();
}

/* ── ORDERS ──────────────────────────────────────────────────────────────── */
async function loadOrders() {
  orders = await api(`/api/orders?date=${currentOrdersDate()}`);
  renderOrders();
  renderGardenMap();
  renderLowStockBanner();
}

/* ── GARDEN MAP ──────────────────────────────────────────────────────────── */
function renderGardenMap() {
  const map = document.getElementById("garden-map");
  if (!map) return;
  const tableOrders = activeTableMap();
  map.innerHTML = GARDEN_LAYOUT.map(section => `
    <div class="garden-section">
      <div class="garden-section-title">${section.section}</div>
      ${section.tables.map(table => {
        const order     = tableOrders[table];
        const cls       = order ? "table-aktif" : "table-empty";
        const totalText = order ? `₺${order.total.toLocaleString("tr-TR")}` : "boş";
        return `
          <div class="table-wrap">
            <div class="chairs chairs-top"><span></span><span></span></div>
            <button class="table-btn ${cls}" data-table="${esc(table)}" onclick="tableClick(this.dataset.table)">
              <span class="table-name">${esc(table)}</span>
              <span class="table-total">${totalText}</span>
            </button>
            <div class="chairs chairs-bottom"><span></span><span></span></div>
          </div>`;
      }).join("")}
    </div>
  `).join("");
}

function activeTableMap() {
  const map = {};
  orders.forEach(o => {
    if (o.status === "Aktif") {
      if (!map[o.table_number] || o.id > map[o.table_number].id) {
        map[o.table_number] = o;
      }
    }
  });
  return map;
}

function tableClick(tableName) {
  const order = activeTableMap()[tableName];
  if (order) openTableModal(order);
  else openNewOrderModal(tableName);
}

function openTableModal(order) {
  document.getElementById("table-modal-title").textContent = `Masa: ${order.table_number}`;
  const time    = new Date(order.created_at + "Z").toLocaleString("tr-TR");
  const isPaid  = order.status !== "Aktif";
  const isIkram = order.status === "İkram";

  document.getElementById("table-modal-content").innerHTML = `
    <div class="table-detail-meta">
      <span class="order-time">${time}</span>
      <span class="status-badge ${isIkram ? "badge-ikram" : isPaid ? "badge-odendi" : "badge-aktif"}">${esc(order.status)}</span>
    </div>
    ${order.waiter ? `<div class="order-waiter-row">👤 ${esc(order.waiter)}</div>` : ""}
    ${timingHtml(order)}
    ${order.notes ? `<div class="order-notes">📝 ${esc(order.notes)}</div>` : ""}
    <ul class="order-items-list">
      ${order.items.map(i => `<li><span class="item-qty">${i.quantity}×</span> ${esc(i.item_name)} <span class="item-price">₺${(i.item_price * i.quantity).toLocaleString("tr-TR")}</span></li>`).join("")}
    </ul>
    <div class="order-total-row">Toplam: ₺${order.total.toLocaleString("tr-TR")}</div>
    ${!isPaid ? `
    <div class="table-status-actions">
      <button class="btn odendi-btn full-width" onclick="closeTableModal(); openPaymentModal(${order.id})">✓ Ödendi olarak işaretle</button>
    </div>` : isIkram
      ? `<div class="paid-method-tag">🎁 İkram — ücret alınmadı${order.ikram_note ? ` (${esc(order.ikram_note)})` : ""}</div>`
      : `<div class="paid-method-tag">${paymentLabel(order.payment_method)} ile ödendi</div>`}
  `;

  document.getElementById("table-modal-delete-btn").onclick = () => tableModalDelete(order.id);
  showModal("table-modal");
}

function closeTableModal() { hideModal("table-modal"); }

async function tableModalDelete(orderId) {
  if (!confirm("Bu siparişi silmek istiyor musunuz?")) return;
  await api(`/api/orders/${orderId}`, { method: "DELETE" });
  closeTableModal();
  loadOrders();
  loadStock();
}

/* ── TOPLAM GİZLEME (göz ikonu) ─────────────────────────────────────────── */
// Açılan kartlar 5 saniyelik yenilemede tekrar kapanmasın diye burada tutuluyor
const revealedTotals = new Set();

const EYE_OPEN   = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>`;
const EYE_CLOSED = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9.9 4.24A9.1 9.1 0 0 1 12 4c6.5 0 10 7 10 7a18.5 18.5 0 0 1-2.16 3.19"/><path d="M6.61 6.61A18.4 18.4 0 0 0 2 12s3.5 7 10 7a9.7 9.7 0 0 0 5.39-1.61"/><path d="M14.12 14.12a3 3 0 1 1-4.24-4.24"/><path d="m2 2 20 20"/></svg>`;

function maskedTotalHtml(order) {
  const shown = revealedTotals.has(order.id);
  return `
    <div class="order-total-row masked-total">
      <span>Toplam</span>
      <span class="total-value ${shown ? "" : "is-masked"}">${shown ? `₺${order.total.toLocaleString("tr-TR")}` : "₺ ••••"}</span>
      <button class="eye-btn" onclick="toggleTotal(${order.id})"
              title="${shown ? "Tutarı gizle" : "Tutarı göster"}" aria-label="${shown ? "Tutarı gizle" : "Tutarı göster"}">
        ${shown ? EYE_CLOSED : EYE_OPEN}
      </button>
    </div>`;
}

function toggleTotal(orderId) {
  if (revealedTotals.has(orderId)) revealedTotals.delete(orderId);
  else revealedTotals.add(orderId);
  renderOrders();
}

function renderOrders() {
  const list     = document.getElementById("orders-list");
  const filtered = activeFilter === "all"
    ? orders
    : orders.filter(o => o.status === activeFilter || (activeFilter === "Ödendi" && o.status === "İkram"));

  // Tarih seçici yalnızca ödenenler/tümü görünümünde; seçilen günün tahsilat özeti
  const showDate = activeFilter !== "Aktif";
  document.getElementById("orders-date-bar").classList.toggle("hidden", !showDate);
  if (showDate) {
    const dateInput = document.getElementById("orders-date");
    if (document.activeElement !== dateInput) dateInput.value = currentOrdersDate();
    const paid  = orders.filter(o => o.status === "Ödendi");
    const sum   = list => list.reduce((s, o) => s + (o.total || 0), 0);
    const nakit = sum(paid.filter(o => o.payment_method === "Nakit"));
    const kart  = sum(paid.filter(o => o.payment_method === "Kredi Kartı"));
    const fmt   = n => "₺" + n.toLocaleString("tr-TR");
    const other = sum(paid) - nakit - kart;
    const ikram = orders.filter(o => o.status === "İkram");
    document.getElementById("orders-today-btn").classList.toggle("is-today", !ordersDate);
    document.getElementById("orders-day-summary").innerHTML = `
      <span class="sum-chip"><b>${paid.length}</b> ödenen sipariş</span>
      <span class="sum-chip total">Toplam <b>${fmt(sum(paid))}</b></span>
      <span class="sum-chip"><span class="dot nakit"></span>Nakit <b>${fmt(nakit)}</b></span>
      <span class="sum-chip"><span class="dot kart"></span>Kart <b>${fmt(kart)}</b></span>
      ${other > 0 ? `<span class="sum-chip">Diğer <b>${fmt(other)}</b></span>` : ""}
      ${ikram.length ? `<span class="sum-chip">🎁 İkram <b>${ikram.length}</b> · ${fmt(sum(ikram))}</span>` : ""}`;
  }

  if (!filtered.length) {
    list.innerHTML = `<div class="empty-state">Gösterilecek sipariş yok</div>`;
    return;
  }

  list.innerHTML = filtered.map(order => {
    const isPaid  = order.status !== "Aktif";
    const isIkram = order.status === "İkram";
    const time   = new Date(order.created_at + "Z").toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
    return `
      <div class="order-card ${isPaid ? "paid" : "active"} ${isIkram ? "ikram" : ""}">
        <div class="order-card-header">
          <div class="order-table-badge">${esc(order.table_number)}</div>
          <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
            ${order.waiter ? `<span class="waiter-chip">${esc(order.waiter)}</span>` : ""}
            <span class="order-time-chip">${time}</span>
          </div>
        </div>
        <div class="order-card-body">
          ${order.notes ? `<div class="order-notes">📝 ${esc(order.notes)}</div>` : ""}
          <ul class="order-items-list">
            ${order.items.map(i => `<li><span class="item-qty">${i.quantity}×</span> ${esc(i.item_name)} <span class="item-price">₺${(i.item_price * i.quantity).toLocaleString("tr-TR")}</span></li>`).join("")}
          </ul>
          ${maskedTotalHtml(order)}
          ${timingHtml(order)}
          <div class="order-actions">
            ${!isPaid
              ? `<button class="btn odendi-btn" onclick="openPaymentModal(${order.id})">✓ Ödendi</button>`
              : isIkram
              ? `<span class="ikram-label">🎁 İkram — ücret alınmadı${order.ikram_note ? `<small>${esc(order.ikram_note)}</small>` : ""}</span>`
              : `<span class="paid-label">${paymentLabel(order.payment_method)}</span>
                 <button class="btn sm" onclick="openEditPaymentModal(${order.id})">Ödemeyi Düzenle</button>`
            }
          </div>
          <div class="order-actions-secondary">
            <button class="btn sec-btn" onclick="window.open('/adisyon/${order.id}','_blank')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
              Adisyon
            </button>
            ${!isPaid ? `
            <button class="btn sec-btn" onclick="openEditOrderModal(${order.id})">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
              Düzenle
            </button>
            <button class="btn sec-btn" onclick="openTableChangeModal(${order.id},'${esc(order.table_number)}')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 7H3"/><path d="m15 1 6 6-6 6"/><path d="M3 17h18"/><path d="m9 11-6 6 6 6"/></svg>
              Masa
            </button>` : ""}
            <button class="btn sec-btn danger" onclick="deleteOrder(${order.id})">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>
              Sil
            </button>
          </div>
        </div>
      </div>
    `;
  }).join("");
}

function openTableChangeModal(orderId, currentTable) {
  document.getElementById("table-change-order-id").value = orderId;
  document.getElementById("table-change-current").textContent = currentTable;
  document.getElementById("table-change-select").value = "";
  showModal("table-change-modal");
}

async function confirmTableChange() {
  const orderId   = document.getElementById("table-change-order-id").value;
  const newTable  = document.getElementById("table-change-select").value;
  if (!newTable) return alert("Lütfen yeni masa seçin.");
  await api(`/api/orders/${orderId}/table`, { method: "PUT", body: JSON.stringify({ table_number: newTable }) });
  hideModal("table-change-modal");
  loadOrders();
}

async function deleteOrder(id) {
  if (!confirm("Bu siparişi silmek istiyor musunuz?")) return;
  await api(`/api/orders/${id}`, { method: "DELETE" });
  loadOrders();
  loadStock();
}

/* ── PAYMENT ─────────────────────────────────────────────────────────────── */
function openPaymentModal(orderId) {
  pendingPaymentOrderId = orderId;
  const order = orders.find(o => o.id === orderId);
  pendingPaymentTotal = order ? order.total : 0;
  document.getElementById("split-payment-form").classList.add("hidden");
  document.getElementById("payment-options").classList.remove("hidden");
  document.getElementById("split-total-display").textContent = `₺${pendingPaymentTotal.toLocaleString("tr-TR")}`;
  document.getElementById("split-cash").value = "";
  document.getElementById("split-card").value = "";
  document.getElementById("discount-input").value = "";
  hideIkramForm();
  document.getElementById("payment-final-total").textContent = `₺${pendingPaymentTotal.toLocaleString("tr-TR")}`;
  // Bu masada yarım kalmış bir bölme varsa kaldığı yerden devam et
  split = loadSplit(orderId);
  splitSelected = new Set();
  setSplitMode(split.payments.length > 0);
  showModal("payment-modal");
}

/* ── HESAP / HESABI BÖLME ─────────────────────────────────────────────────── */
// Kişiler ürün ürün söyleyip ayrı ayrı öder: seçilen ürünler tahsil edilir, kilitlenir;
// hepsi ödenince masa kapanır ve nakit/kart toplamları "karma" ödeme olarak yazılır.
let splitMode     = false;
let split         = { payments: [], paid: {} };   // paid: { birimAnahtarı: kişiNo }
let splitSelected = new Set();

const tlFmt = n => "₺" + (Math.round(n * 100) / 100).toLocaleString("tr-TR");

function loadSplit(orderId) {
  // Kayıt, siparişin açılış zamanıyla eşleşmiyorsa eski/başka bir siparişe aittir — yok say
  const order = orders.find(o => o.id === orderId);
  try {
    const saved = JSON.parse(localStorage.getItem(`split-${orderId}`) || "null");
    if (saved && Array.isArray(saved.payments) && order && saved.createdAt === order.created_at) return saved;
  } catch (e) {}
  return { payments: [], paid: {}, createdAt: order ? order.created_at : null };
}

function saveSplit() {
  try {
    if (split.payments.length) localStorage.setItem(`split-${pendingPaymentOrderId}`, JSON.stringify(split));
    else localStorage.removeItem(`split-${pendingPaymentOrderId}`);
  } catch (e) {}
}

// 3× Cola → 3 ayrı satır; her biri ayrı kişiye ait olabilsin
function splitUnits(order) {
  const units = [];
  order.items.forEach(i => {
    for (let n = 0; n < i.quantity; n++) {
      units.push({ key: `${i.id}-${n}`, name: i.item_name, price: i.item_price });
    }
  });
  return units;
}

function setSplitMode(on) {
  splitMode = on;
  splitSelected = new Set();
  // Bölerken indirim ve normal ödeme seçenekleri gizlenir
  document.querySelector("#payment-modal .discount-row").classList.toggle("hidden", on);
  document.getElementById("payment-options").classList.toggle("hidden", on);
  document.getElementById("split-payment-form").classList.add("hidden");
  document.getElementById("split-pay-actions").classList.toggle("hidden", !on);
  document.getElementById("payment-subtitle").textContent = on
    ? "Kişinin yediklerini seç, sonra ödemesini al"
    : "Ödeme nasıl yapıldı?";
  renderPaymentBill();
}

function toggleSplitUnit(key) {
  if (split.paid[key]) return;
  splitSelected.has(key) ? splitSelected.delete(key) : splitSelected.add(key);
  renderPaymentBill();
}

function renderPaymentBill() {
  const order = orders.find(o => o.id === pendingPaymentOrderId);
  const el = document.getElementById("payment-bill");
  if (!order) { el.innerHTML = ""; return; }
  const time = new Date(order.created_at + "Z").toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
  const meta = `
    <div class="bill-meta">
      <span class="bill-table">${esc(order.table_number)}</span>
      <span class="bill-meta-right">
        <span>${order.waiter ? esc(order.waiter) + " · " : ""}${time}</span>
        ${splitMode
          ? (split.payments.length ? "" : `<button class="btn sm" onclick="setSplitMode(false)">Bölmeden Öde</button>`)
          : `<button class="btn sm" onclick="setSplitMode(true)">Hesabı Böl</button>`}
      </span>
    </div>`;

  if (!splitMode) {
    el.innerHTML = meta + `
      <div class="bill-items">
        ${order.items.map(i => `
          <div class="bill-row">
            <span class="bill-qty">${i.quantity}×</span>
            <span class="bill-name">${esc(i.item_name)}${i.quantity > 1 ? `<small>${tlFmt(i.item_price)}</small>` : ""}</span>
            <span class="bill-amt">${tlFmt(i.item_price * i.quantity)}</span>
          </div>`).join("")}
      </div>
      <div class="bill-total"><span>Toplam</span><strong>${tlFmt(order.total)}</strong></div>`;
    return;
  }

  const units = splitUnits(order);
  const payment = no => split.payments.find(p => p.no === no);
  const selectedTotal = units.filter(u => splitSelected.has(u.key)).reduce((s, u) => s + u.price, 0);
  const remaining = units.filter(u => !split.paid[u.key]).reduce((s, u) => s + u.price, 0);
  const nextNo = split.payments.length + 1;

  el.innerHTML = meta + `
    <div class="bill-items split">
      ${units.map(u => {
        const payer = split.paid[u.key];
        const sel = splitSelected.has(u.key);
        return `
          <div class="bill-row split-row ${payer ? "is-paid" : ""} ${sel ? "is-selected" : ""}"
               ${payer ? "" : `onclick="toggleSplitUnit('${u.key}')"`}>
            <span class="tick">${sel || payer ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>` : ""}</span>
            <span class="bill-name">${esc(u.name)}${payer ? `<small>${payer}. kişi · ${esc(payment(payer)?.method || "")}</small>` : ""}</span>
            <span class="bill-amt">${tlFmt(u.price)}</span>
          </div>`;
      }).join("")}
    </div>
    <div class="split-summary">
      <div class="split-selected">
        <span>${nextNo}. kişi · seçilen ${splitSelected.size} ürün</span>
        <strong>${tlFmt(selectedTotal)}</strong>
      </div>
      <div class="split-remaining">
        <span>Kalan</span><span>${tlFmt(remaining)}</span>
      </div>
      ${split.payments.length ? `
        <div class="split-payments">
          ${split.payments.map(p => `<span>${p.no}. kişi: ${tlFmt(p.amount)} ${esc(p.method)}</span>`).join("")}
          <button class="link-btn" onclick="undoLastSplitPayment()">Son ödemeyi geri al</button>
        </div>` : ""}
    </div>`;

  const none = splitSelected.size === 0;
  document.getElementById("split-pay-cash").disabled = none;
  document.getElementById("split-pay-card").disabled = none;
}

async function paySelected(method) {
  const order = orders.find(o => o.id === pendingPaymentOrderId);
  if (!order || !splitSelected.size) return;
  const units = splitUnits(order);
  const no = split.payments.length + 1;
  const amount = units.filter(u => splitSelected.has(u.key)).reduce((s, u) => s + u.price, 0);
  split.payments.push({ no, amount, method });
  splitSelected.forEach(k => { split.paid[k] = no; });
  splitSelected = new Set();
  saveSplit();

  // Herkes ödediyse masayı kapat
  if (units.every(u => split.paid[u.key])) {
    const cash = split.payments.filter(p => p.method === "Nakit").reduce((s, p) => s + p.amount, 0);
    const card = split.payments.filter(p => p.method !== "Nakit").reduce((s, p) => s + p.amount, 0);
    const finalMethod = !card ? "Nakit" : !cash ? "Kredi Kartı"
      : `Nakit: ₺${cash.toLocaleString("tr-TR")} / Kart: ₺${card.toLocaleString("tr-TR")}`;
    await api(`/api/orders/${pendingPaymentOrderId}/status`, {
      method: "PUT",
      body: JSON.stringify({ status: "Ödendi", payment_method: finalMethod, discount: 0 }),
    });
    try { localStorage.removeItem(`split-${pendingPaymentOrderId}`); } catch (e) {}
    closePaymentModal();
    loadOrders();
    return;
  }
  renderPaymentBill();
}

function undoLastSplitPayment() {
  const last = split.payments.pop();
  if (!last) return;
  Object.keys(split.paid).forEach(k => { if (split.paid[k] === last.no) delete split.paid[k]; });
  saveSplit();
  renderPaymentBill();
}

function updatePaymentTotal() {
  const discount = parseFloat(document.getElementById("discount-input").value) || 0;
  const final = Math.max(0, pendingPaymentTotal - discount);
  document.getElementById("payment-final-total").textContent = `₺${final.toLocaleString("tr-TR")}`;
}

function showSplitPayment() {
  document.getElementById("payment-options").classList.add("hidden");
  document.getElementById("split-payment-form").classList.remove("hidden");
}

function hideSplitPayment() {
  document.getElementById("split-payment-form").classList.add("hidden");
  document.getElementById("payment-options").classList.remove("hidden");
}

function updateSplitCard() {
  const cash = parseFloat(document.getElementById("split-cash").value) || 0;
  document.getElementById("split-card").value = Math.max(0, pendingPaymentTotal - cash).toFixed(2);
}

function updateSplitCash() {
  const card = parseFloat(document.getElementById("split-card").value) || 0;
  document.getElementById("split-cash").value = Math.max(0, pendingPaymentTotal - card).toFixed(2);
}

async function confirmPayment(method) {
  if (!pendingPaymentOrderId) return;
  const discount = parseFloat(document.getElementById("discount-input").value) || 0;
  await api(`/api/orders/${pendingPaymentOrderId}/status`, {
    method: "PUT",
    body: JSON.stringify({ status: "Ödendi", payment_method: method, discount }),
  });
  pendingPaymentOrderId = null;
  closePaymentModal();
  loadOrders();
}

/* ── İKRAM (işletme sahibinin misafiri — ücret alınmaz) ── */
function showIkramForm() {
  document.getElementById("ikram-note").value = "";
  document.getElementById("payment-options").classList.add("hidden");
  document.querySelector("#payment-modal .discount-row").classList.add("hidden");
  document.getElementById("payment-subtitle").classList.add("hidden");
  document.getElementById("ikram-form").classList.remove("hidden");
  document.getElementById("ikram-note").focus();
}

function hideIkramForm() {
  document.getElementById("ikram-form").classList.add("hidden");
  document.getElementById("payment-options").classList.remove("hidden");
  document.querySelector("#payment-modal .discount-row").classList.remove("hidden");
  document.getElementById("payment-subtitle").classList.remove("hidden");
}

async function confirmIkram() {
  if (!pendingPaymentOrderId) return;
  const ikram_note = document.getElementById("ikram-note").value.trim();
  const res = await api(`/api/orders/${pendingPaymentOrderId}/status`, {
    method: "PUT",
    body: JSON.stringify({ status: "İkram", ikram_note }),
  });
  if (res && res.error) return alert(res.error);
  try { localStorage.removeItem(`split-${pendingPaymentOrderId}`); } catch (e) {}
  pendingPaymentOrderId = null;
  closePaymentModal();
  loadOrders();
}

async function confirmSplitPayment() {
  const cash = parseFloat(document.getElementById("split-cash").value) || 0;
  const card = parseFloat(document.getElementById("split-card").value) || 0;
  if (cash < 0 || card < 0) return alert("Geçersiz tutar.");
  const discount = parseFloat(document.getElementById("discount-input").value) || 0;
  const method = `Nakit: ₺${cash.toLocaleString("tr-TR")} / Kart: ₺${card.toLocaleString("tr-TR")}`;
  await api(`/api/orders/${pendingPaymentOrderId}/status`, {
    method: "PUT",
    body: JSON.stringify({ status: "Ödendi", payment_method: method, discount }),
  });
  pendingPaymentOrderId = null;
  pendingPaymentTotal   = 0;
  closePaymentModal();
  loadOrders();
}

/* ── AÇIK ADİSYONU DÜZENLEME (ürün ekle / çıkar) ─────────────────────────── */
// Değişiklikler pencerede toplanır, "Kaydet"te tek seferde işlenir (fişler bir kez basılsın)
let editOrderId    = null;
let editExisting   = [];   // { id, name, price, qty, newQty }
let editAdditions  = {};   // menu_item_id → { menu_item_id, name, price, quantity }

function openEditOrderModal(orderId) {
  const order = orders.find(o => o.id === orderId);
  if (!order) return;
  editOrderId = orderId;
  editExisting = order.items.map(i => ({ id: i.id, name: i.item_name, price: i.item_price, qty: i.quantity, newQty: i.quantity }));
  editAdditions = {};
  document.getElementById("edit-order-title").textContent = `Adisyonu Düzenle · ${order.table_number}`;
  document.getElementById("edit-order-search").value = "";
  document.getElementById("edit-order-msg").textContent = "";
  renderEditOrder();
  renderEditOrderPick();
  showModal("edit-order-modal");
}

function editQty(id, delta) {
  const it = editExisting.find(i => i.id === id);
  if (it) it.newQty = Math.max(0, it.newQty + delta);
  renderEditOrder();
}

function editAddQty(menuId, delta) {
  const a = editAdditions[menuId];
  if (!a) return;
  a.quantity += delta;
  if (a.quantity <= 0) delete editAdditions[menuId];
  renderEditOrder();
}

function editPick(menuId) {
  const m = menuItems.find(x => x.id === menuId);
  if (!m) return;
  if (!editAdditions[menuId]) editAdditions[menuId] = { menu_item_id: m.id, name: m.name, price: m.price, quantity: 0 };
  editAdditions[menuId].quantity += 1;
  renderEditOrder();
}

function renderEditOrder() {
  const stepper = (onMinus, onPlus, qty) => `
    <span class="edit-stepper">
      <button onclick="${onMinus}" aria-label="Azalt">−</button>
      <span class="num">${qty}</span>
      <button onclick="${onPlus}" aria-label="Arttır">+</button>
    </span>`;
  const rows = editExisting.map(i => `
    <div class="edit-row ${i.newQty === 0 ? "is-removed" : ""} ${i.newQty !== i.qty ? "is-changed" : ""}">
      <span class="edit-name">${esc(i.name)}${i.newQty === 0 ? "<small>çıkarılacak</small>" : i.newQty !== i.qty ? `<small>${i.qty} → ${i.newQty}</small>` : ""}</span>
      ${stepper(`editQty(${i.id},-1)`, `editQty(${i.id},1)`, i.newQty)}
      <span class="edit-amt">₺${(i.price * i.newQty).toLocaleString("tr-TR")}</span>
    </div>`).concat(Object.values(editAdditions).map(a => `
    <div class="edit-row is-new">
      <span class="edit-name">${esc(a.name)}<small>yeni eklenecek</small></span>
      ${stepper(`editAddQty(${a.menu_item_id},-1)`, `editAddQty(${a.menu_item_id},1)`, a.quantity)}
      <span class="edit-amt">₺${(a.price * a.quantity).toLocaleString("tr-TR")}</span>
    </div>`));
  document.getElementById("edit-order-items").innerHTML = rows.join("") || `<div class="empty-state" style="padding:20px">Adisyonda ürün yok</div>`;
  const total = editExisting.reduce((s, i) => s + i.price * i.newQty, 0)
              + Object.values(editAdditions).reduce((s, a) => s + a.price * a.quantity, 0);
  document.getElementById("edit-order-total").textContent = `₺${total.toLocaleString("tr-TR")}`;
}

function renderEditOrderPick() {
  const q = document.getElementById("edit-order-search").value.trim().toLocaleLowerCase("tr-TR");
  const list = menuItems.filter(m => !q || m.name.toLocaleLowerCase("tr-TR").includes(q) || (m.category || "").toLocaleLowerCase("tr-TR").includes(q));
  document.getElementById("edit-order-pick").innerHTML = list.map(m => `
    <div class="pick-item" onclick="editPick(${m.id})">
      <span>${esc(m.name)}</span>
      <span class="pick-item-price">₺${m.price.toLocaleString("tr-TR")} <b class="pick-plus">+</b></span>
    </div>`).join("") || `<div class="pick-item" style="cursor:default;color:var(--ink-3)">Ürün bulunamadı</div>`;
}

async function saveEditOrder() {
  const msg = document.getElementById("edit-order-msg");
  const changed = editExisting.filter(i => i.newQty !== i.qty);
  const additions = Object.values(editAdditions).filter(a => a.quantity > 0);
  if (!changed.length && !additions.length) { closeEditOrderModal(); return; }
  if (editExisting.every(i => i.newQty === 0) && !additions.length) {
    msg.textContent = "Adisyonda en az bir ürün kalmalı. Tamamen iptal için siparişi silin.";
    return;
  }
  for (const i of changed) {
    const res = await api(`/api/orders/${editOrderId}/items/${i.id}`, { method: "PUT", body: JSON.stringify({ quantity: i.newQty }) });
    if (res.error) { msg.textContent = res.error; return; }
  }
  if (additions.length) {
    const res = await api(`/api/orders/${editOrderId}/items`, { method: "POST", body: JSON.stringify({ items: additions, notes: "" }) });
    if (res.error) { msg.textContent = res.error; return; }
  }
  closeEditOrderModal();
  loadOrders();
}

function closeEditOrderModal() {
  editOrderId = null;
  hideModal("edit-order-modal");
}

/* ── ÖDENMİŞ SİPARİŞİN ÖDEME YÖNTEMİNİ DÜZELTME ─────────────────────────── */
let editPaymentOrderId = null;

function openEditPaymentModal(orderId) {
  const order = orders.find(o => o.id === orderId);
  if (!order) return;
  editPaymentOrderId = orderId;
  document.getElementById("edit-pay-info").innerHTML =
    `<b>${esc(order.table_number)}</b> · ₺${order.total.toLocaleString("tr-TR")} · şu an: <b>${esc(order.payment_method || "—")}</b>`;
  document.getElementById("edit-pay-karma").classList.add("hidden");
  document.getElementById("edit-pay-options").classList.remove("hidden");
  document.getElementById("edit-pay-cash").value = "";
  document.getElementById("edit-pay-card").value = "";
  document.getElementById("edit-pay-msg").textContent = "";
  showModal("edit-payment-modal");
}

function showEditKarma() {
  document.getElementById("edit-pay-options").classList.add("hidden");
  document.getElementById("edit-pay-karma").classList.remove("hidden");
}

function editKarmaFill(changed) {
  const order = orders.find(o => o.id === editPaymentOrderId);
  if (!order) return;
  const cash = document.getElementById("edit-pay-cash");
  const card = document.getElementById("edit-pay-card");
  if (changed === "cash") card.value = Math.max(0, order.total - (parseFloat(cash.value) || 0));
  else cash.value = Math.max(0, order.total - (parseFloat(card.value) || 0));
}

async function saveEditPayment(method) {
  if (method === "Karma") {
    const cash = parseFloat(document.getElementById("edit-pay-cash").value) || 0;
    const card = parseFloat(document.getElementById("edit-pay-card").value) || 0;
    method = `Nakit: ₺${cash.toLocaleString("tr-TR")} / Kart: ₺${card.toLocaleString("tr-TR")}`;
  }
  const res = await api(`/api/orders/${editPaymentOrderId}/payment`, {
    method: "PUT",
    body: JSON.stringify({ payment_method: method }),
  });
  if (res.error) { document.getElementById("edit-pay-msg").textContent = res.error; return; }
  closeEditPaymentModal();
  loadOrders();
}

function closeEditPaymentModal() {
  editPaymentOrderId = null;
  hideModal("edit-payment-modal");
}

function closePaymentModal() {
  pendingPaymentOrderId = null;
  hideModal("payment-modal");
}

/* ── NEW ORDER MODAL ─────────────────────────────────────────────────────── */
function openNewOrderModal(tableName = "") {
  selectedItems = {};
  document.getElementById("order-table").value    = tableName;
  document.getElementById("order-waiter").value   = "";
  document.getElementById("order-notes").value    = "";
  document.getElementById("menu-search").value    = "";
  document.getElementById("order-bungalov").value = "";
  renderMenuPickList(menuItems);
  renderSelectedItems();
  populateBungalovOrderSelect();
  showModal("order-modal");
}

function populateBungalovOrderSelect() {
  const sel  = document.getElementById("order-bungalov");
  const row  = document.getElementById("bungalov-order-row");
  const open = bungalovData.filter(b => b.account);
  row.style.display = open.length ? "flex" : "none";
  sel.innerHTML = `<option value="">— Hesaba ekleme —</option>` +
    open.map(b => `<option value="${b.no}">${BUNGALOV_NAMES[b.no]} — ${esc(b.account.guest_name)}</option>`).join("");
}

function closeOrderModal() { hideModal("order-modal"); }

function filterMenuSearch() {
  const q = document.getElementById("menu-search").value.toLowerCase();
  renderMenuPickList(menuItems.filter(i =>
    i.name.toLowerCase().includes(q) || i.category.toLowerCase().includes(q)
  ));
}

function renderMenuPickList(items) {
  const list = document.getElementById("menu-pick-list");
  if (!items.length) {
    list.innerHTML = `<div style="padding:12px;text-align:center;color:#aaa">Ürün bulunamadı</div>`;
    return;
  }
  list.innerHTML = items.map(item => `
    <div class="pick-item" onclick="addToOrder(${item.id}, '${esc(item.name)}', ${item.price})">
      <span>${esc(item.name)} <small style="color:#aaa">${esc(item.category)}</small></span>
      <span class="pick-item-price">₺${item.price.toFixed(2)}</span>
    </div>
  `).join("");
}

function addToOrder(id, name, price) {
  if (selectedItems[id]) selectedItems[id].quantity++;
  else selectedItems[id] = { name, price, quantity: 1 };
  renderSelectedItems();
}

function changeQty(id, delta) {
  if (!selectedItems[id]) return;
  selectedItems[id].quantity += delta;
  if (selectedItems[id].quantity <= 0) delete selectedItems[id];
  renderSelectedItems();
}

function setQty(id, val) {
  const qty = parseInt(val);
  if (!selectedItems[id]) return;
  if (qty <= 0) delete selectedItems[id];
  else selectedItems[id].quantity = qty;
  renderSelectedItems();
}

function renderSelectedItems() {
  const container = document.getElementById("selected-items");
  const entries   = Object.entries(selectedItems);
  document.getElementById("selected-items-wrap").style.display = entries.length ? "block" : "none";

  container.innerHTML = entries.map(([id, item]) => `
    <div class="selected-item-row">
      <span class="selected-item-name">${esc(item.name)}</span>
      <button class="btn sm" onclick="changeQty(${id}, -1)">−</button>
      <input class="selected-item-qty" type="number" min="1" value="${item.quantity}"
        onchange="setQty(${id}, this.value)" />
      <button class="btn sm" onclick="changeQty(${id}, 1)">+</button>
      <span class="selected-item-subtotal">₺${(item.price * item.quantity).toFixed(2)}</span>
    </div>
  `).join("");

  const total = entries.reduce((sum, [, item]) => sum + item.price * item.quantity, 0);
  document.getElementById("order-total").textContent = `₺${total.toFixed(2)}`;
}

async function submitOrder() {
  const table       = document.getElementById("order-table").value.trim();
  const waiter      = document.getElementById("order-waiter").value;
  const notes       = document.getElementById("order-notes").value.trim();
  const bungalov_no = document.getElementById("order-bungalov").value || null;
  const entries = Object.entries(selectedItems);

  if (!table)         return alert("Masa numarası giriniz.");
  if (!entries.length) return alert("En az bir ürün seçiniz.");

  const items = entries.map(([id, item]) => ({
    menu_item_id: parseInt(id),
    name:         item.name,
    price:        item.price,
    quantity:     item.quantity,
  }));

  await api("/api/orders", {
    method: "POST",
    body: JSON.stringify({ table_number: table, notes, waiter, bungalov_no, items }),
  });

  closeOrderModal();
  loadOrders();
  loadStock();
  loadBungalov();
}

/* ── STOCK ───────────────────────────────────────────────────────────────── */
async function loadStock() {
  stockItems = await api("/api/stock");
  renderStockTable();
  renderStockAlerts();
  renderLowStockBanner();
}

function renderStockTable() {
  const tbody = document.getElementById("stock-tbody");
  if (!stockItems.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:#aaa;padding:40px">Henüz stok kalemi yok</td></tr>`;
    return;
  }
  tbody.innerHTML = stockItems.map(item => {
    const isLow    = item.min_quantity > 0 && item.quantity <= item.min_quantity;
    const qtyClass = isLow ? "stock-qty-low" : "stock-qty-ok";
    const linked   = menuItems.find(m => m.id === item.menu_item_id);
    return `
      <tr>
        <td>${esc(item.name)} ${isLow ? `<span class="low-badge">⚠ Azaldı</span>` : ""}</td>
        <td class="${qtyClass}">${fmtQty(item.quantity)}</td>
        <td>${esc(item.unit)}</td>
        <td>${item.min_quantity > 0 ? fmtQty(item.min_quantity) : "—"}</td>
        <td>${linked ? esc(linked.name) : `<span style="color:#aaa">—</span>`}</td>
        <td>
          <button class="btn sm" onclick="openRestockModal(${item.id})">+ Ekle</button>
          <button class="btn sm" onclick='openStockModal(${JSON.stringify(item)})'>Düzenle</button>
          <button class="btn sm danger" onclick="deleteStockItem(${item.id})">Sil</button>
        </td>
      </tr>
    `;
  }).join("");
}

function renderStockAlerts() {
  const section = document.getElementById("stock-alerts-section");
  if (!section) return;
  const low = stockItems.filter(s => s.min_quantity > 0 && s.quantity <= s.min_quantity);
  if (!low.length) { section.innerHTML = ""; return; }
  section.innerHTML = `
    <div class="alert-box">
      <strong>⚠ Stok Uyarısı</strong>
      <ul>
        ${low.map(s => `<li>${esc(s.name)}: <strong>${fmtQty(s.quantity)} ${esc(s.unit)}</strong> kaldı (min: ${fmtQty(s.min_quantity)})</li>`).join("")}
      </ul>
    </div>
  `;
}

function renderLowStockBanner() {
  const banner = document.getElementById("low-stock-banner");
  if (!banner) return;
  const low = stockItems.filter(s => s.min_quantity > 0 && s.quantity <= s.min_quantity);
  if (!low.length) { banner.classList.add("hidden"); return; }
  banner.classList.remove("hidden");
  banner.innerHTML = `⚠ Stok uyarısı: ${low.map(s => `<strong>${esc(s.name)}</strong>`).join(", ")} — <a href="#" onclick="switchTab('stock');return false">Stoğa git</a>`;
}

function populateStockMenuLink() {
  const sel = document.getElementById("stock-menu-link");
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML = `<option value="">-- Bağlı değil --</option>` +
    menuItems.map(m => `<option value="${m.id}">${esc(m.name)}</option>`).join("");
  sel.value = current;
}

function openStockModal(item = null) {
  document.getElementById("stock-modal-title").textContent = item ? "Stok Kalemi Düzenle" : "Stok Kalemi Ekle";
  document.getElementById("stock-edit-id").value = item ? item.id : "";
  document.getElementById("stock-name").value    = item ? item.name : "";
  document.getElementById("stock-qty").value     = item ? item.quantity : "";
  document.getElementById("stock-unit").value    = item ? item.unit : "adet";
  document.getElementById("stock-min").value     = item ? item.min_quantity : "";
  populateStockMenuLink();
  document.getElementById("stock-menu-link").value = item && item.menu_item_id ? item.menu_item_id : "";
  showModal("stock-modal");
}

function closeStockModal() { hideModal("stock-modal"); }

async function saveStockItem() {
  const id   = document.getElementById("stock-edit-id").value;
  const body = {
    name:         document.getElementById("stock-name").value.trim(),
    quantity:     parseFloat(document.getElementById("stock-qty").value) || 0,
    unit:         document.getElementById("stock-unit").value.trim() || "adet",
    min_quantity: parseFloat(document.getElementById("stock-min").value) || 0,
    menu_item_id: document.getElementById("stock-menu-link").value || null,
  };
  if (!body.name) return alert("Ürün adı zorunludur.");
  if (id) {
    await api(`/api/stock/${id}`, { method: "PUT", body: JSON.stringify(body) });
  } else {
    await api("/api/stock", { method: "POST", body: JSON.stringify(body) });
  }
  closeStockModal();
  loadStock();
}

async function deleteStockItem(id) {
  if (!confirm("Bu stok kalemini silmek istiyor musunuz?")) return;
  await api(`/api/stock/${id}`, { method: "DELETE" });
  loadStock();
}

function openRestockModal(id) {
  pendingRestockId = id;
  const item = stockItems.find(s => s.id === id);
  document.getElementById("restock-title").textContent   = `Stok Ekle — ${item.name}`;
  document.getElementById("restock-current").textContent = `Mevcut: ${fmtQty(item.quantity)} ${item.unit}`;
  document.getElementById("restock-amount").value        = "";
  showModal("restock-modal");
}

function closeRestockModal() {
  pendingRestockId = null;
  hideModal("restock-modal");
}

async function confirmRestock() {
  const amount = parseFloat(document.getElementById("restock-amount").value);
  if (!amount || amount <= 0) return alert("Geçerli bir miktar giriniz.");
  await api(`/api/stock/${pendingRestockId}/add`, {
    method: "POST",
    body: JSON.stringify({ amount }),
  });
  closeRestockModal();
  loadStock();
}

/* ── BUNGALOV ────────────────────────────────────────────────────────────── */
async function loadBungalov() {
  bungalovData = await api("/api/bungalov");
  renderBungalov();
}

function renderBungalov() {
  const grid = document.getElementById("bungalov-grid");
  if (!grid) return;
  grid.innerHTML = bungalovData.map(b => {
    const a = b.account;
    if (a) {
      const checkin = new Date(a.checkin_date + "T00:00:00").toLocaleDateString("tr-TR");
      return `
        <div class="bungalov-card bungalov-open">
          <div class="bungalov-no">${BUNGALOV_NAMES[b.no]}</div>
          <span class="bungalov-badge open">Açık Hesap</span>
          <div class="bungalov-guest">👤 ${esc(a.guest_name)}</div>
          <div class="bungalov-meta">📅 Giriş: ${checkin}</div>
          <div class="bungalov-total">₺${(a.total || 0).toLocaleString("tr-TR")}</div>
          <div class="bungalov-charge-count">${a.charges.length} kalem masraf</div>
          <button class="btn primary full-width" style="margin-top:12px" onclick="openBungalovModal(${a.id})">Hesabı Görüntüle</button>
        </div>`;
    } else {
      return `
        <div class="bungalov-card bungalov-empty">
          <div class="bungalov-no">${BUNGALOV_NAMES[b.no]}</div>
          <span class="bungalov-badge empty">Boş</span>
          <div class="bungalov-empty-text">Misafir yok</div>
          <button class="btn full-width" style="margin-top:12px" onclick="openBungalovOpenModal(${b.no})">+ Hesap Aç</button>
        </div>`;
    }
  }).join("");
}

function openBungalovOpenModal(no) {
  activeBungalovNo = no;
  document.getElementById("bungalov-open-title").textContent = `Hesap Aç — ${BUNGALOV_NAMES[no]}`;
  document.getElementById("bungalov-guest-name").value = "";
  document.getElementById("bungalov-checkin").value    = todayLocal();
  document.getElementById("bungalov-open-notes").value = "";
  showModal("bungalov-open-modal");
}

function closeBungalovOpenModal() { hideModal("bungalov-open-modal"); }

async function confirmOpenAccount() {
  const guestName   = document.getElementById("bungalov-guest-name").value.trim();
  const checkinDate = document.getElementById("bungalov-checkin").value;
  const notes       = document.getElementById("bungalov-open-notes").value.trim();
  if (!guestName || !checkinDate) return alert("Misafir adı ve giriş tarihi zorunludur.");
  const res = await api(`/api/bungalov/${activeBungalovNo}/open`, {
    method: "POST",
    body: JSON.stringify({ guest_name: guestName, checkin_date: checkinDate, notes }),
  });
  if (res.error) return alert(res.error);
  closeBungalovOpenModal();
  await loadBungalov();
  // Doğrudan hesabı aç
  const b = bungalovData.find(x => x.no === activeBungalovNo);
  if (b && b.account) openBungalovModal(b.account.id);
}

async function openBungalovModal(accountId) {
  activeBungalovAccId = accountId;
  const data = await api(`/api/bungalov/account/${accountId}`);
  document.getElementById("bungalov-modal-title").textContent = `${BUNGALOV_NAMES[data.bungalov_no]} — ${data.guest_name}`;
  renderBungalovAccount(data);
  showModal("bungalov-modal");
}

function closeBungalovModal() { hideModal("bungalov-modal"); }

function renderBungalovAccount(data) {
  const checkin  = new Date(data.checkin_date + "T00:00:00").toLocaleDateString("tr-TR");
  const total    = (data.total || 0).toLocaleString("tr-TR");
  const isClosed = data.status === "Kapandı";

  document.getElementById("bungalov-modal-content").innerHTML = `
    <div class="bungalov-detail-meta">
      <span>📅 Giriş: <strong>${checkin}</strong></span>
      <span class="bungalov-badge ${isClosed ? "closed" : "open"}">${isClosed ? "Kapandı" : "Açık"}</span>
    </div>
    ${data.notes ? `<div class="order-notes" style="margin-bottom:10px">📝 ${esc(data.notes)}</div>` : ""}

    <table class="bungalov-charges-table">
      <thead><tr><th>Tarih</th><th>Açıklama</th><th>Tutar</th>${!isClosed ? "<th></th>" : ""}</tr></thead>
      <tbody>
        ${data.charges.length ? data.charges.map(c => {
          const dt = new Date(c.created_at + "Z").toLocaleDateString("tr-TR");
          return `<tr>
            <td style="color:var(--ink-3);font-size:0.82rem">${dt}</td>
            <td>${esc(c.description)}</td>
            <td style="font-weight:600">₺${c.amount.toLocaleString("tr-TR")}</td>
            ${!isClosed ? `<td><button class="btn sm danger" onclick="deleteCharge(${c.id})">Sil</button></td>` : ""}
          </tr>`;
        }).join("") : `<tr><td colspan="4" style="text-align:center;color:#aaa;padding:16px">Henüz masraf yok</td></tr>`}
      </tbody>
    </table>

    <div class="bungalov-charges-total">Toplam: <strong>₺${total}</strong></div>

    ${!isClosed ? `
    <div style="display:flex;gap:10px;margin-top:16px">
      <button class="btn full-width" onclick="openBungalovMenuModal(${data.id})">+ Menüden Ekle</button>
      <button class="btn full-width" onclick="openBungalovChargeModal(${data.id})">+ Masraf Ekle</button>
      <button class="btn odendi-btn full-width" onclick="openBungalovCheckoutModal(${data.id}, ${data.total || 0})">Çıkış & Ödeme</button>
    </div>` : `
    <div class="paid-method-tag" style="margin-top:14px">
      ${paymentLabel(data.payment_method)} ile ödendi
      ${data.checkout_date ? ` — Çıkış: ${new Date(data.checkout_date + "T00:00:00").toLocaleDateString("tr-TR")}` : ""}
    </div>`}
  `;
}

function openBungalovChargeModal(accountId) {
  activeBungalovAccId = accountId;
  document.getElementById("charge-desc").value   = "";
  document.getElementById("charge-amount").value = "";
  showModal("bungalov-charge-modal");
}

function closeBungalovChargeModal() { hideModal("bungalov-charge-modal"); }

async function confirmAddCharge() {
  const description = document.getElementById("charge-desc").value.trim();
  const amount      = parseFloat(document.getElementById("charge-amount").value);
  if (!description || !amount || amount <= 0) return alert("Açıklama ve geçerli tutar giriniz.");
  await api(`/api/bungalov/account/${activeBungalovAccId}/charge`, {
    method: "POST",
    body: JSON.stringify({ description, amount }),
  });
  closeBungalovChargeModal();
  openBungalovModal(activeBungalovAccId);
  loadBungalov();
}

async function deleteCharge(chargeId) {
  if (!confirm("Bu masrafı silmek istiyor musunuz?")) return;
  await api(`/api/bungalov/charge/${chargeId}`, { method: "DELETE" });
  openBungalovModal(activeBungalovAccId);
  loadBungalov();
}

/* ── BUNGALOV HESABINA MENÜDEN ÜRÜN ─────────────────────────────────────── */
let bungalovCart = {};   // menu_item_id → { menu_item_id, name, price, quantity }

function openBungalovMenuModal(accountId) {
  activeBungalovAccId = accountId;
  bungalovCart = {};
  document.getElementById("bmenu-search").value = "";
  document.getElementById("bmenu-msg").textContent = "";
  renderBungalovCart();
  renderBungalovMenuPick();
  showModal("bungalov-menu-modal");
}

function closeBungalovMenuModal() { hideModal("bungalov-menu-modal"); }

function bungalovPick(menuId) {
  const m = menuItems.find(x => x.id === menuId);
  if (!m) return;
  if (!bungalovCart[menuId]) bungalovCart[menuId] = { menu_item_id: m.id, name: m.name, price: m.price, quantity: 0 };
  bungalovCart[menuId].quantity += 1;
  renderBungalovCart();
}

function bungalovCartQty(menuId, delta) {
  const c = bungalovCart[menuId];
  if (!c) return;
  c.quantity += delta;
  if (c.quantity <= 0) delete bungalovCart[menuId];
  renderBungalovCart();
}

function renderBungalovCart() {
  const lines = Object.values(bungalovCart);
  document.getElementById("bmenu-cart").innerHTML = lines.length ? lines.map(c => `
    <div class="edit-row is-new">
      <span class="edit-name">${esc(c.name)}</span>
      <span class="edit-stepper">
        <button onclick="bungalovCartQty(${c.menu_item_id},-1)" aria-label="Azalt">−</button>
        <span class="num">${c.quantity}</span>
        <button onclick="bungalovCartQty(${c.menu_item_id},1)" aria-label="Arttır">+</button>
      </span>
      <span class="edit-amt">₺${(c.price * c.quantity).toLocaleString("tr-TR")}</span>
    </div>`).join("") : `<div class="bmenu-empty">Aşağıdan ürün seçin</div>`;
  const total = lines.reduce((s, c) => s + c.price * c.quantity, 0);
  document.getElementById("bmenu-total").textContent = `₺${total.toLocaleString("tr-TR")}`;
}

function renderBungalovMenuPick() {
  const q = document.getElementById("bmenu-search").value.trim().toLocaleLowerCase("tr-TR");
  const list = menuItems.filter(m => !q || m.name.toLocaleLowerCase("tr-TR").includes(q) || (m.category || "").toLocaleLowerCase("tr-TR").includes(q));
  document.getElementById("bmenu-pick").innerHTML = list.map(m => `
    <div class="pick-item" onclick="bungalovPick(${m.id})">
      <span>${esc(m.name)}</span>
      <span class="pick-item-price">₺${m.price.toLocaleString("tr-TR")} <b class="pick-plus">+</b></span>
    </div>`).join("") || `<div class="pick-item" style="cursor:default;color:var(--ink-3)">Ürün bulunamadı</div>`;
}

async function confirmBungalovMenuItems() {
  const items = Object.values(bungalovCart).map(c => ({ menu_item_id: c.menu_item_id, quantity: c.quantity }));
  const msg = document.getElementById("bmenu-msg");
  if (!items.length) { msg.textContent = "En az bir ürün seçin"; return; }
  const res = await api(`/api/bungalov/account/${activeBungalovAccId}/menu-items`, { method: "POST", body: JSON.stringify({ items }) });
  if (res.error) { msg.textContent = res.error; return; }
  closeBungalovMenuModal();
  openBungalovModal(activeBungalovAccId);
  loadBungalov();
}

function openBungalovCheckoutModal(accountId, total) {
  pendingCheckoutAccId = accountId;
  document.getElementById("bungalov-checkout-total").textContent = `Toplam tutar: ₺${total.toLocaleString("tr-TR")}`;
  document.getElementById("bungalov-checkout-date").value        = todayLocal();
  document.getElementById("bungalov-checkout-payment").value     = "Nakit";
  document.getElementById("bungalov-checkout-nakit").value       = "";
  toggleCheckoutKarma();
  showModal("bungalov-checkout-modal");
}

function toggleCheckoutKarma() {
  const karma = document.getElementById("bungalov-checkout-payment").value === "Karma";
  document.getElementById("bungalov-checkout-karma-row").classList.toggle("hidden", !karma);
}

function closeBungalovCheckoutModal() { hideModal("bungalov-checkout-modal"); }

async function confirmCheckout() {
  const payment_method = document.getElementById("bungalov-checkout-payment").value;
  const checkout_date  = document.getElementById("bungalov-checkout-date").value;
  const nakit_amount   = document.getElementById("bungalov-checkout-nakit").value;
  if (!checkout_date) return alert("Çıkış tarihi giriniz.");
  if (payment_method === "Karma" && nakit_amount === "") return alert("Nakit tutarını giriniz.");
  const res = await api(`/api/bungalov/account/${pendingCheckoutAccId}/checkout`, {
    method: "PUT",
    body: JSON.stringify({ payment_method, checkout_date, nakit_amount }),
  });
  if (res && res.error) return alert(res.error);
  closeBungalovCheckoutModal();
  closeBungalovModal();
  loadBungalov();
}

async function loadBungalovHistory() {
  const data = await api("/api/bungalov/history");
  const container = document.getElementById("bungalov-history");
  if (!data.length) {
    container.innerHTML = `<div class="empty-state">Geçmiş hesap yok</div>`;
    return;
  }
  container.innerHTML = `
    <div class="menu-table-wrap">
      <table>
        <thead>
          <tr><th>Bungalov</th><th>Misafir</th><th>Giriş</th><th>Çıkış</th><th>Toplam</th><th>Ödeme</th></tr>
        </thead>
        <tbody>
          ${data.map(a => `
            <tr>
              <td>${BUNGALOV_NAMES[a.bungalov_no] || `Bungalov ${a.bungalov_no}`}</td>
              <td>${esc(a.guest_name)}</td>
              <td>${a.checkin_date ? new Date(a.checkin_date + "T00:00:00").toLocaleDateString("tr-TR") : "—"}</td>
              <td>${a.checkout_date ? new Date(a.checkout_date + "T00:00:00").toLocaleDateString("tr-TR") : "—"}</td>
              <td style="font-weight:700">₺${(a.total || 0).toLocaleString("tr-TR")}</td>
              <td>${paymentLabel(a.payment_method)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

/* ── WAITERS ─────────────────────────────────────────────────────────────── */
async function loadWaiters() {
  const waiters = await api("/api/waiters");
  const container = document.getElementById("waiters-list");
  container.innerHTML = waiters.map(w => `
    <div class="waiter-card">
      <div class="waiter-name">${esc(w.name)}</div>
      <div class="waiter-pin-row">
        <input type="password" id="pin-${w.id}" maxlength="4" placeholder="••••"
               class="pin-edit-input" />
        <button class="btn primary" onclick="savePin(${w.id})">PIN Güncelle</button>
      </div>
    </div>
  `).join("");
}

async function savePin(waiterId) {
  const input = document.getElementById(`pin-${waiterId}`);
  const pin   = input.value.trim();
  if (!/^\d{4}$/.test(pin)) return alert("PIN 4 haneli rakam olmalı.");
  await api(`/api/waiters/${waiterId}/pin`, {
    method: "PUT",
    body: JSON.stringify({ pin }),
  });
  input.value = "";
  input.placeholder = "Güncellendi ✓";
  setTimeout(() => { input.placeholder = "••••"; }, 2000);
}

/* ── MODAL HELPERS ───────────────────────────────────────────────────────── */
function showModal(id) {
  document.getElementById(id).classList.remove("hidden");
  document.getElementById("overlay").classList.remove("hidden");
}

function hideModal(id) {
  document.getElementById(id).classList.add("hidden");
  document.getElementById("overlay").classList.add("hidden");
}

function closeAll() {
  document.querySelectorAll(".modal").forEach(m => m.classList.add("hidden"));
  document.getElementById("overlay").classList.add("hidden");
  pendingPaymentOrderId = null;
}

/* ── UTIL ────────────────────────────────────────────────────────────────── */
function fmtTime(str) {
  if (!str) return null;
  return new Date(str + "Z").toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
}

function fmtDuration(startStr, endStr) {
  const start = new Date(startStr + "Z");
  const end   = endStr ? new Date(endStr + "Z") : new Date();
  const mins  = Math.round((end - start) / 60000);
  if (mins < 60) return `${mins} dk`;
  return `${Math.floor(mins / 60)} sa ${mins % 60} dk`;
}

function timingHtml(order) {
  const open  = fmtTime(order.created_at);
  const close = fmtTime(order.closed_at);
  const dur   = fmtDuration(order.created_at, order.closed_at);
  if (close) {
    return `<div class="order-timing">🕐 ${open} → ${close} &nbsp;·&nbsp; ⏱ ${dur}</div>`;
  }
  return `<div class="order-timing">🕐 ${open} &nbsp;·&nbsp; ⏱ ${dur}</div>`;
}

function paymentLabel(method) {
  if (!method) return "Ödendi";
  if (method === "Nakit") return "💵 Nakit";
  if (method === "Kredi Kartı") return "💳 Kredi Kartı";
  return `🔀 ${method}`;
}

function fmtQty(n) {
  return Number.isInteger(n) ? String(n) : parseFloat(n).toLocaleString("tr-TR");
}

function todayLocal() {
  return new Date().toLocaleDateString("sv");
}

function esc(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/* ── FİŞ YAZICILARI ─────────────────────────────────────────────────────── */
async function loadPrinterSettings() {
  const s = await api("/api/settings/printers");
  document.getElementById("printer-enabled").checked  = !!s.enabled;
  document.getElementById("printer-mutfak-ip").value  = s.mutfak_ip || "";
  document.getElementById("printer-pizza-ip").value   = s.pizza_ip  || "";
  document.getElementById("printer-agent-token").value = s.agent_token || "";
  document.getElementById("printer-status-msg").textContent = "";
}

async function savePrinterSettings() {
  const body = {
    enabled:   document.getElementById("printer-enabled").checked,
    mutfak_ip: document.getElementById("printer-mutfak-ip").value.trim(),
    pizza_ip:  document.getElementById("printer-pizza-ip").value.trim(),
  };
  await api("/api/settings/printers", { method: "PUT", body: JSON.stringify(body) });
  const msg = document.getElementById("printer-status-msg");
  msg.textContent = "✓ Kaydedildi";
  msg.className = "printer-status-msg ok";
}

async function testPrinter(station) {
  const msg = document.getElementById("printer-status-msg");
  msg.textContent = "Kuyruğa ekleniyor...";
  msg.className = "printer-status-msg";
  const res = await api("/api/settings/printers/test", { method: "POST", body: JSON.stringify({ station }) });
  if (res.ok) {
    msg.textContent = "✓ Test fişi kuyruğa eklendi — dükkândaki print-agent çalışıyorsa birazdan basılacak";
    msg.className = "printer-status-msg ok";
  } else {
    msg.textContent = `⚠ Hata: ${res.error || "bilinmeyen hata"}`;
    msg.className = "printer-status-msg err";
  }
}

function copyAgentToken() {
  const input = document.getElementById("printer-agent-token");
  input.select();
  navigator.clipboard?.writeText(input.value);
  const msg = document.getElementById("printer-status-msg");
  msg.textContent = "✓ Token kopyalandı";
  msg.className = "printer-status-msg ok";
}

/* ── Z RAPORU HESAPLARI ────────────────────────────────────────────────────── */
function ownerMsg(text, ok) {
  const msg = document.getElementById("owner-status-msg");
  msg.textContent = text;
  msg.className = "printer-status-msg " + (ok ? "ok" : "err");
}

async function loadOwners() {
  const owners = await api("/api/owners");
  document.getElementById("owner-url").textContent = `${location.protocol}//${location.host}/z-raporu`;
  const list = document.getElementById("owners-list");
  if (!owners.length) {
    list.innerHTML = `<p class="page-sub" style="margin-top:14px">Henüz hesap yok. Yukarıdan ilk Z Raporu hesabını oluştur.</p>`;
    return;
  }
  list.innerHTML = owners.map(o => `
    <div class="owner-row">
      <div class="owner-name">${esc(o.display_name || o.username)}<small>@${esc(o.username)}</small></div>
      <input type="text" id="owner-name-${o.id}" value="${esc(o.display_name || "")}" placeholder="Ad" autocomplete="off" />
      <input type="password" id="owner-pass-${o.id}" placeholder="Yeni şifre (isteğe bağlı)" autocomplete="new-password" />
      <button class="btn" onclick="changeOwnerPass(${o.id})">Kaydet</button>
      <button class="btn danger" onclick="deleteOwner(${o.id}, this)">Sil</button>
    </div>`).join("");
}

async function addOwner() {
  const display_name = document.getElementById("owner-new-name").value.trim();
  const username = document.getElementById("owner-new-user").value.trim();
  const password = document.getElementById("owner-new-pass").value;
  const res = await api("/api/owners", { method: "POST", body: JSON.stringify({ username, password, display_name }) });
  if (res.error) return ownerMsg(res.error, false);
  document.getElementById("owner-new-name").value = "";
  document.getElementById("owner-new-user").value = "";
  document.getElementById("owner-new-pass").value = "";
  ownerMsg(`"${username}" hesabı oluşturuldu ✓`, true);
  loadOwners();
}

async function changeOwnerPass(id) {
  const input = document.getElementById(`owner-pass-${id}`);
  const display_name = document.getElementById(`owner-name-${id}`).value.trim();
  const res = await api(`/api/owners/${id}`, { method: "PUT", body: JSON.stringify({ password: input.value, display_name }) });
  if (res.error) return ownerMsg(res.error, false);
  const passChanged = !!input.value;
  input.value = "";
  ownerMsg(passChanged ? "Ad ve şifre güncellendi ✓" : "Kaydedildi ✓", true);
  loadOwners();
}

async function deleteOwner(id, btn) {
  // Tarayıcı onay penceresi yerine iki adımlı buton: ilk tık onay ister
  if (btn.dataset.confirm !== "1") {
    btn.dataset.confirm = "1";
    btn.textContent = "Emin misin?";
    setTimeout(() => { btn.dataset.confirm = ""; btn.textContent = "Sil"; }, 3000);
    return;
  }
  await api(`/api/owners/${id}`, { method: "DELETE" });
  ownerMsg("Hesap silindi", true);
  loadOwners();
}

/* ── KONAKLAMA ÖDEMELERİ ─────────────────────────────────────────────────── */
async function loadLodgingPayments() {
  const dateInput = document.getElementById("lodging-date");
  if (!dateInput.value) dateInput.value = todayLocal();
  const data = await api(`/api/lodging-payments?date=${dateInput.value}`);

  const unitSel = document.getElementById("lodging-unit");
  if (!unitSel.options.length) {
    unitSel.innerHTML = `<option value="">Seç</option>` + data.units.map(u => `<option>${esc(u)}</option>`).join("");
  }

  const pays = data.payments;
  const sumOf = m => pays.filter(p => p.payment_method === m).reduce((s, p) => s + p.amount, 0);
  const nakit = sumOf("Nakit"), kart = sumOf("Kredi Kartı"), havale = sumOf("Havale");
  document.getElementById("lodging-totals").textContent = pays.length
    ? `Nakit ₺${nakit.toLocaleString("tr-TR")} · Kart ₺${kart.toLocaleString("tr-TR")} · Havale ₺${havale.toLocaleString("tr-TR")} · Toplam ₺${(nakit + kart + havale).toLocaleString("tr-TR")}`
    : "";

  const tbody = document.getElementById("lodging-tbody");
  if (!pays.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--ink-3);padding:32px">Bu gün tahsilat yok</td></tr>`;
    return;
  }
  tbody.innerHTML = pays.map(p => `
    <tr>
      <td>${new Date(p.created_at + "Z").toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })}</td>
      <td><strong>${esc(p.unit)}</strong></td>
      <td>${esc(p.guest_name || "—")}</td>
      <td style="color:var(--ink-2)">${esc(p.notes || "")}</td>
      <td>${lodgingChip(p.payment_method)}</td>
      <td><strong>₺${p.amount.toLocaleString("tr-TR")}</strong></td>
      <td style="text-align:right"><button class="btn sm danger" onclick="deleteLodgingPayment(${p.id}, this)">Sil</button></td>
    </tr>`).join("");
}

function lodgingChip(method) {
  const cls = { "Nakit": "nakit", "Kredi Kartı": "kart", "Havale": "havale" }[method] || "kart";
  const label = { "Nakit": "Nakit", "Kredi Kartı": "Kart", "Havale": "Havale" }[method] || method;
  return `<span class="pay-chip ${cls}">${label}</span>`;
}

async function addLodgingPayment(method) {
  const msg = document.getElementById("lodging-msg");
  const body = {
    unit:           document.getElementById("lodging-unit").value,
    guest_name:     document.getElementById("lodging-guest").value.trim(),
    amount:         parseFloat(document.getElementById("lodging-amount").value) || 0,
    notes:          document.getElementById("lodging-notes").value.trim(),
    payment_method: method,
  };
  const res = await api("/api/lodging-payments", { method: "POST", body: JSON.stringify(body) });
  if (res.error) { msg.className = "printer-status-msg err"; msg.textContent = res.error; return; }
  msg.className = "printer-status-msg ok";
  const how = { "Nakit": "nakit", "Kredi Kartı": "kartla", "Havale": "havale ile" }[method];
  msg.textContent = `${body.unit}: ₺${body.amount.toLocaleString("tr-TR")} ${how} alındı olarak kaydedildi ✓`;
  ["lodging-guest", "lodging-amount", "lodging-notes"].forEach(id => { document.getElementById(id).value = ""; });
  document.getElementById("lodging-unit").value = "";
  document.getElementById("lodging-date").value = todayLocal();
  loadLodgingPayments();
}

async function deleteLodgingPayment(id, btn) {
  // Tarayıcı onay penceresi yerine iki adımlı buton
  if (btn.dataset.confirm !== "1") {
    btn.dataset.confirm = "1";
    btn.textContent = "Emin misin?";
    setTimeout(() => { btn.dataset.confirm = ""; btn.textContent = "Sil"; }, 3000);
    return;
  }
  await api(`/api/lodging-payments/${id}`, { method: "DELETE" });
  loadLodgingPayments();
}

/* ── KASA DEVRİ ──────────────────────────────────────────────────────────── */
let cashFloats = [];

async function loadCashFloats() {
  const dateInput = document.getElementById("float-date");
  if (!dateInput.value) dateInput.value = todayLocal();
  cashFloats = await api("/api/cash-floats");
  fillCashFloatForm();
  const tbody = document.getElementById("float-tbody");
  if (!cashFloats.length) {
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;color:var(--ink-3);padding:32px">Henüz kayıt yok</td></tr>`;
    return;
  }
  tbody.innerHTML = cashFloats.map(f => `
    <tr>
      <td>${new Date(f.float_date + "T00:00").toLocaleDateString("tr-TR", { day: "numeric", month: "long", weekday: "long" })}</td>
      <td><strong>₺${f.amount.toLocaleString("tr-TR")}</strong></td>
      <td style="color:var(--ink-2)">${esc(f.notes || "")}</td>
      <td style="text-align:right">
        <button class="btn sm" onclick="editCashFloat('${f.float_date}')">Düzenle</button>
        <button class="btn sm danger" onclick="deleteCashFloat('${f.float_date}', this)">Sil</button>
      </td>
    </tr>`).join("");
}

// Seçili tarihte kayıt varsa formu onunla doldur (üzerine yazılır)
function fillCashFloatForm() {
  const date = document.getElementById("float-date").value;
  const f = cashFloats.find(x => x.float_date === date);
  document.getElementById("float-amount").value = f ? f.amount : "";
  document.getElementById("float-notes").value = f ? (f.notes || "") : "";
}

function editCashFloat(date) {
  document.getElementById("float-date").value = date;
  fillCashFloatForm();
  document.getElementById("float-amount").focus();
}

async function saveCashFloat() {
  const msg = document.getElementById("float-msg");
  const body = {
    date:   document.getElementById("float-date").value,
    amount: document.getElementById("float-amount").value,
    notes:  document.getElementById("float-notes").value.trim(),
  };
  const res = await api("/api/cash-floats", { method: "PUT", body: JSON.stringify(body) });
  if (res.error) { msg.className = "printer-status-msg err"; msg.textContent = res.error; return; }
  msg.className = "printer-status-msg ok";
  msg.textContent = `Kasada bırakılan ₺${parseFloat(body.amount).toLocaleString("tr-TR")} kaydedildi ✓`;
  loadCashFloats();
}

async function deleteCashFloat(date, btn) {
  if (btn.dataset.confirm !== "1") {
    btn.dataset.confirm = "1";
    btn.textContent = "Emin misin?";
    setTimeout(() => { btn.dataset.confirm = ""; btn.textContent = "Sil"; }, 3000);
    return;
  }
  await api(`/api/cash-floats/${date}`, { method: "DELETE" });
  loadCashFloats();
}
