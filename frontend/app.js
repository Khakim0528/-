"use strict";

const CURRENCY = "$";
const UNITS = { kg: "кг", l: "л", pcs: "шт", pack: "уп" };
const STATUS = {
  pending_payment: "Ожидает оплаты", paid: "Оплачен", processing: "Собирается",
  delivering: "В доставке", completed: "Выполнен", cancelled: "Отменён",
};
// mirrors ALLOWED_TRANSITIONS in app/routers/admin.py
const NEXT = {
  pending_payment: ["cancelled"], paid: ["processing", "cancelled"],
  processing: ["delivering", "cancelled"], delivering: ["completed", "cancelled"],
  completed: [], cancelled: [],
};
const EMOJI = [
  [/яблок/i, "🍎"], [/банан/i, "🍌"], [/помидор|томат/i, "🍅"], [/картоф/i, "🥔"],
  [/молок|кефир/i, "🥛"], [/сыр/i, "🧀"], [/йогурт/i, "🥣"], [/багет/i, "🥖"], [/хлеб/i, "🍞"],
  [/кур/i, "🍗"], [/лосос|рыб/i, "🐟"], [/вод/i, "💧"], [/сок/i, "🧃"],
  [/овощ|фрукт/i, "🥬"], [/молоч/i, "🥛"], [/выпечк/i, "🥐"], [/мяс/i, "🥩"], [/напит/i, "🥤"],
];

const $ = (sel, el = document) => el.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (v) => `${Number(v).toFixed(2)} ${CURRENCY}`;
const unit = (u) => UNITS[u] || u;
const fmtDate = (s) => new Date(s).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });

const state = {
  token: localStorage.getItem("token"),
  user: null,
  cart: { items: [], total: "0" },
  categories: [],
  products: [],
  total: 0,
  filters: { q: "", category: null, sort: "name", page: 1 },
  adminTab: "stats",
};

/* ---------- helpers ---------- */
function emojiFor(product) {
  const cat = state.categories.find((c) => c.id === product.category_id);
  const hay = `${product.name} ${cat ? cat.name : ""}`;
  const hit = EMOJI.find(([re]) => re.test(hay));
  return hit ? hit[1] : "🛒";
}

function thumb(product) {
  return product.image_url
    ? `<img src="${esc(product.image_url)}" alt="" loading="lazy">`
    : emojiFor(product);
}

function formatError(data, status) {
  const d = data && data.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => e.msg).join("; ");
  return `Ошибка ${status}`;
}

async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let payload;
  if (form) payload = new URLSearchParams(form);
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await fetch(path, { method, headers, body: payload });
  if (res.status === 401 && state.token) logout(false);
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(formatError(data, res.status));
  return data;
}

let toastTimer;
function toast(msg, isErr = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = `toast show${isErr ? " err" : ""}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.className = "toast"), 2800);
}

async function guard(fn) {
  try { return await fn(); } catch (e) { toast(e.message, true); }
}

/* ---------- auth ---------- */
async function loadUser() {
  if (!state.token) return;
  try {
    state.user = await api("/users/me");
    state.cart = await api("/cart");
  } catch { /* token invalid: api() already logged out */ }
}

function logout(navigate = true) {
  state.token = null; state.user = null; state.cart = { items: [], total: "0" };
  localStorage.removeItem("token");
  renderChrome();
  if (navigate) { toast("Вы вышли"); location.hash = "#/"; }
  route();
}

function openAuth() {
  const dlg = $("#authDlg");
  setAuthMode("login");
  $("#authError").textContent = "";
  dlg.showModal();
}

function setAuthMode(mode) {
  const form = $("#authForm");
  form.classList.toggle("is-register", mode === "register");
  form.dataset.mode = mode;
  document.querySelectorAll("[data-auth-tab]").forEach((t) => t.classList.toggle("active", t.dataset.authTab === mode));
  $("#authSubmit").textContent = mode === "register" ? "Создать аккаунт" : "Войти";
  form.password.autocomplete = mode === "register" ? "new-password" : "current-password";
}

async function login(email, password) {
  const t = await api("/auth/login", { method: "POST", form: { username: email, password } });
  state.token = t.access_token;
  localStorage.setItem("token", state.token);
  await loadUser();
}

$("#authForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const err = $("#authError");
  err.textContent = "";
  try {
    if (f.dataset.mode === "register") {
      await api("/auth/register", { method: "POST", body: { email: f.email.value, password: f.password.value, full_name: f.full_name.value } });
    }
    await login(f.email.value, f.password.value);
    $("#authDlg").close();
    f.reset();
    renderChrome();
    route();
    toast(`Добро пожаловать, ${state.user.full_name || state.user.email}!`);
  } catch (ex) { err.textContent = ex.message; }
});

/* ---------- chrome (header, cart) ---------- */
function renderChrome() {
  $("#accountBtn").textContent = state.user ? `${state.user.full_name || state.user.email.split("@")[0]} · Выйти` : "Войти";
  document.querySelector('[data-nav="orders"]').hidden = !state.user;
  document.querySelector('[data-nav="admin"]').hidden = !(state.user && state.user.role === "admin");
  const count = state.cart.items.reduce((n, i) => n + i.quantity, 0);
  $("#cartCount").textContent = count;
  renderCart();
}

function renderCart() {
  const body = $("#cartBody"), foot = $("#cartFoot");
  if (!state.user) {
    body.innerHTML = `<div class="empty">Войдите, чтобы пользоваться корзиной</div>`;
    foot.innerHTML = `<button class="btn primary" data-action="account">Войти</button>`;
    return;
  }
  if (!state.cart.items.length) {
    body.innerHTML = `<div class="empty">Корзина пуста</div>`;
    foot.innerHTML = "";
    return;
  }
  body.innerHTML = state.cart.items.map(({ product: p, quantity, line_total }) => `
    <div class="line">
      <div class="em">${emojiFor(p)}</div>
      <div class="info"><b>${esc(p.name)}</b><span class="muted">${money(p.price)} / ${unit(p.unit)}</span></div>
      <div class="qty">
        <button data-action="qty" data-id="${p.id}" data-q="${quantity - 1}" aria-label="Меньше">−</button>
        <span>${quantity}</span>
        <button data-action="qty" data-id="${p.id}" data-q="${quantity + 1}" aria-label="Больше">+</button>
      </div>
      <b>${money(line_total)}</b>
    </div>`).join("");
  foot.innerHTML = `
    <div class="total"><span>Итого</span><span>${money(state.cart.total)}</span></div>
    <button class="btn primary" data-action="checkout">Оформить заказ</button>`;
}

const toggleCart = (open) => {
  $("#drawer").classList.toggle("open", open);
  $("#overlay").classList.toggle("open", open);
};

async function addToCart(id) {
  if (!state.user) return openAuth();
  await guard(async () => {
    state.cart = await api("/cart/items", { method: "POST", body: { product_id: id, quantity: 1 } });
    renderChrome();
    toast("Добавлено в корзину");
  });
}

async function setQty(id, q) {
  await guard(async () => {
    state.cart = q < 1
      ? await api(`/cart/items/${id}`, { method: "DELETE" })
      : await api(`/cart/items/${id}`, { method: "PATCH", body: { quantity: q } });
    renderChrome();
  });
}

function openCheckout() {
  const f = $("#checkoutForm");
  f.phone.value = f.phone.value || (state.user && state.user.phone) || "";
  $("#checkoutError").textContent = "";
  $("#checkoutDlg").showModal();
}

$("#checkoutForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  try {
    const order = await api("/orders", { method: "POST", body: { address: f.address.value, phone: f.phone.value, comment: f.comment.value || null } });
    $("#checkoutDlg").close();
    f.reset();
    state.cart = { items: [], total: "0" };
    toggleCart(false);
    renderChrome();
    toast(`Заказ №${order.id} создан. Осталось оплатить.`);
    location.hash = "#/orders";
  } catch (ex) { $("#checkoutError").textContent = ex.message; }
});

/* ---------- catalog ---------- */
function renderCatalog() {
  $("#view").innerHTML = `
    <section class="hero"><h1>Свежие продукты с доставкой</h1><p>Выбирайте, добавляйте в корзину — мы привезём.</p></section>
    <div class="toolbar">
      <div class="chips" id="chips"></div>
      <select id="sort" aria-label="Сортировка">
        <option value="name">По названию</option>
        <option value="price_asc">Сначала дешёвые</option>
        <option value="price_desc">Сначала дорогие</option>
        <option value="newest">Новинки</option>
      </select>
    </div>
    <div class="grid" id="grid"></div>
    <div class="more" id="more"></div>`;
  $("#sort").value = state.filters.sort;
  renderChips();
  loadProducts(true);
}

function renderChips() {
  const top = state.categories.filter((c) => c.parent_id === null);
  const chip = (id, name) => `<button class="chip${state.filters.category === id ? " active" : ""}" data-action="category" data-id="${id ?? ""}">${esc(name)}</button>`;
  $("#chips").innerHTML = chip(null, "Все") + top.map((c) => chip(c.id, c.name)).join("");
}

async function loadProducts(reset) {
  const f = state.filters;
  if (reset) f.page = 1;
  const params = new URLSearchParams({ sort: f.sort, page: f.page, size: 12 });
  if (f.q) params.set("q", f.q);
  if (f.category) params.set("category_id", f.category);
  await guard(async () => {
    const data = await api(`/products?${params}`);
    state.products = reset ? data.items : state.products.concat(data.items);
    state.total = data.total;
    renderGrid();
  });
}

function renderGrid() {
  const grid = $("#grid");
  if (!grid) return;
  grid.innerHTML = state.products.length ? state.products.map((p) => `
    <article class="card">
      <div class="thumb">${thumb(p)}</div>
      <div class="card-body">
        <h3>${esc(p.name)}</h3>
        <span class="muted">${esc(p.description) || (p.stock > 0 ? `В наличии: ${p.stock}` : "")}</span>
        <div class="price">${money(p.price)} <small>/ ${unit(p.unit)}</small></div>
        <button class="btn primary" data-action="add" data-id="${p.id}" ${p.stock < 1 ? "disabled" : ""}>${p.stock < 1 ? "Нет в наличии" : "В корзину"}</button>
      </div>
    </article>`).join("") : `<div class="empty" style="grid-column:1/-1">Ничего не найдено</div>`;
  $("#more").innerHTML = state.products.length < state.total
    ? `<button class="btn ghost" data-action="more">Показать ещё</button>` : "";
}

/* ---------- orders ---------- */
async function renderOrders() {
  if (!state.user) { location.hash = "#/"; return openAuth(); }
  $("#view").innerHTML = `<h1 class="page-title">Мои заказы</h1><div class="stack" id="orders">Загрузка…</div>`;
  await guard(async () => {
    const orders = await api("/orders");
    $("#orders").innerHTML = orders.length ? orders.map((o) => `
      <div class="panel">
        <div class="panel-head">
          <div><b>Заказ №${o.id}</b> <span class="muted">· ${fmtDate(o.created_at)}</span></div>
          <span class="status ${o.status}">${STATUS[o.status]}</span>
        </div>
        <ul class="items">${o.items.map((i) => `<li>${esc(i.product_name)} × ${i.quantity} — ${money(i.unit_price * i.quantity)}</li>`).join("")}</ul>
        <div class="muted">${esc(o.address)}</div>
        <div class="panel-head" style="margin:10px 0 0"><b>${money(o.total)}</b>
          ${o.status === "pending_payment" ? `<div class="actions" style="margin:0">
            <button class="btn primary small" data-action="pay" data-id="${o.id}">Оплатить (демо)</button>
            <button class="btn danger small" data-action="cancel-order" data-id="${o.id}">Отменить</button></div>` : ""}
        </div>
      </div>`).join("") : `<div class="empty">Заказов пока нет</div>`;
  });
}

async function payOrder(id) {
  await guard(async () => {
    await api(`/orders/${id}/pay`, { method: "POST", body: { payment_token: "tok_demo" } });
    toast("Оплата прошла (демо-режим)");
    renderOrders();
  });
}

async function cancelOrder(id) {
  if (!confirm("Отменить заказ?")) return;
  await guard(async () => {
    await api(`/orders/${id}/cancel`, { method: "POST" });
    toast("Заказ отменён");
    renderOrders();
  });
}

/* ---------- admin ---------- */
async function renderAdmin() {
  if (!state.user || state.user.role !== "admin") { location.hash = "#/"; return; }
  const tabs = [["stats", "Статистика"], ["orders", "Заказы"], ["products", "Товары"], ["users", "Клиенты"]];
  $("#view").innerHTML = `
    <h1 class="page-title">Админ-панель</h1>
    <div class="toolbar"><div class="chips">${tabs.map(([k, n]) => `<button class="chip${state.adminTab === k ? " active" : ""}" data-action="admin-tab" data-tab="${k}">${n}</button>`).join("")}</div></div>
    <div id="adminBody">Загрузка…</div>`;
  await guard(async () => {
    const body = $("#adminBody");
    if (state.adminTab === "stats") {
      const s = await api("/admin/stats");
      const byStatus = Object.entries(s.orders_by_status).map(([k, n]) => `<li>${STATUS[k]}: ${n}</li>`).join("");
      body.innerHTML = `
        <div class="stats">
          <div class="panel stat"><span class="muted">Выручка</span><b>${money(s.revenue)}</b></div>
          <div class="panel stat"><span class="muted">Заказов</span><b>${s.orders}</b></div>
          <div class="panel stat"><span class="muted">Товаров</span><b>${s.products}</b></div>
          <div class="panel stat"><span class="muted">Пользователей</span><b>${s.users}</b></div>
        </div>
        <div class="panel"><b>Заказы по статусам</b><ul class="items">${byStatus || "<li>Пока нет заказов</li>"}</ul></div>`;
    } else if (state.adminTab === "orders") {
      const orders = await api("/admin/orders?limit=200");
      body.innerHTML = `<div class="panel table-wrap"><table>
        <tr><th>№</th><th>Дата</th><th>Клиент</th><th>Состав</th><th>Сумма</th><th>Статус</th></tr>
        ${orders.map((o) => `<tr>
          <td>${o.id}</td><td>${fmtDate(o.created_at)}</td>
          <td>${esc(o.phone)}<br><span class="muted">${esc(o.address)}</span></td>
          <td>${o.items.map((i) => `${esc(i.product_name)} ×${i.quantity}`).join(", ")}</td>
          <td>${money(o.total)}</td>
          <td><select data-action="order-status" data-id="${o.id}">
            <option value="${o.status}" selected>${STATUS[o.status]}</option>
            ${NEXT[o.status].map((s) => `<option value="${s}">${STATUS[s]}</option>`).join("")}
          </select></td></tr>`).join("") || `<tr><td colspan="6" class="muted">Заказов нет</td></tr>`}
      </table></div>`;
    } else if (state.adminTab === "products") {
      const products = await api("/admin/products?limit=200");
      state.adminProducts = products;
      body.innerHTML = `
        <div class="actions" style="margin:0 0 14px"><button class="btn primary" data-action="product-new">+ Добавить товар</button></div>
        <div class="panel table-wrap"><table>
          <tr><th>Товар</th><th>Цена</th><th>Остаток</th><th>Статус</th><th></th></tr>
          ${products.map((p) => `<tr>
            <td>${emojiFor(p)} ${esc(p.name)}</td><td>${money(p.price)} / ${unit(p.unit)}</td><td>${p.stock}</td>
            <td>${p.is_active ? "Виден" : '<span class="muted">Скрыт</span>'}</td>
            <td><button class="btn ghost small" data-action="product-edit" data-id="${p.id}">Изменить</button></td></tr>`).join("")}
        </table></div>`;
    } else {
      const users = await api("/admin/users?limit=200");
      body.innerHTML = `<div class="panel table-wrap"><table>
        <tr><th>Клиент</th><th>Email</th><th>Телефон</th><th>Регистрация</th><th>Роль</th><th>Заказов</th><th>Статус</th><th></th></tr>
        ${users.map((u) => `<tr>
          <td>${esc(u.full_name) || '<span class="muted">—</span>'}</td>
          <td>${esc(u.email)}</td>
          <td>${esc(u.phone) || '<span class="muted">—</span>'}</td>
          <td>${fmtDate(u.created_at)}</td>
          <td>${u.role === "admin" ? '<span class="status">Админ</span>' : "Клиент"}</td>
          <td>${u.orders_count}</td>
          <td>${u.is_active ? "Активен" : '<span class="status cancelled">Заблокирован</span>'}</td>
          <td>${u.id === state.user.id ? "" : `<button class="btn ${u.is_active ? "danger" : "ghost"} small" data-action="user-status" data-id="${u.id}" data-active="${!u.is_active}">${u.is_active ? "Заблокировать" : "Разблокировать"}</button>`}</td>
        </tr>`).join("") || `<tr><td colspan="8" class="muted">Пока никто не зарегистрировался</td></tr>`}
      </table></div>`;
    }
  });
}

async function setUserStatus(id, isActive) {
  if (!isActive && !confirm("Заблокировать клиента? Он не сможет войти, но история заказов сохранится.")) return;
  await guard(async () => {
    await api(`/admin/users/${id}/status`, { method: "PATCH", body: { is_active: isActive } });
    toast(isActive ? "Клиент разблокирован" : "Клиент заблокирован");
    renderAdmin();
  });
}

function openProductDialog(product) {
  const f = $("#productForm");
  f.dataset.id = product ? product.id : "";
  $("#productTitle").textContent = product ? "Изменить товар" : "Новый товар";
  f.category_id.innerHTML = `<option value="">Без категории</option>` +
    state.categories.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
  f.name.value = product?.name ?? "";
  f.description.value = product?.description ?? "";
  f.price.value = product?.price ?? "";
  f.stock.value = product?.stock ?? 0;
  f.unit.value = product?.unit ?? "pcs";
  f.category_id.value = product?.category_id ?? "";
  f.image_url.value = product?.image_url ?? "";
  f.is_active.checked = product ? product.is_active : true;
  $("#productError").textContent = "";
  $("#productDlg").showModal();
}

$("#productForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const body = {
    name: f.name.value, description: f.description.value, price: f.price.value,
    stock: Number(f.stock.value), unit: f.unit.value,
    category_id: f.category_id.value ? Number(f.category_id.value) : null,
    image_url: f.image_url.value || null, is_active: f.is_active.checked,
  };
  try {
    const id = f.dataset.id;
    await api(id ? `/admin/products/${id}` : "/admin/products", { method: id ? "PATCH" : "POST", body });
    $("#productDlg").close();
    toast("Сохранено");
    renderAdmin();
  } catch (ex) { $("#productError").textContent = ex.message; }
});

/* ---------- routing & events ---------- */
function route() {
  const page = location.hash.replace(/^#\/?/, "") || "catalog";
  document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.nav === page));
  if (page === "orders") renderOrders();
  else if (page === "admin") renderAdmin();
  else renderCatalog();
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);

let searchTimer;
$("#search").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.filters.q = e.target.value.trim();
    if (location.hash && location.hash !== "#/") location.hash = "#/";
    else loadProducts(true);
  }, 300);
});

document.addEventListener("change", (e) => {
  const el = e.target;
  if (el.id === "sort") { state.filters.sort = el.value; loadProducts(true); }
  if (el.dataset.action === "order-status") {
    guard(async () => {
      await api(`/admin/orders/${el.dataset.id}/status`, { method: "PATCH", body: { status: el.value } });
      toast("Статус обновлён");
      renderAdmin();
    });
  }
});

document.addEventListener("click", (e) => {
  const tab = e.target.closest("[data-auth-tab]");
  if (tab) return setAuthMode(tab.dataset.authTab);
  const el = e.target.closest("[data-action]");
  if (!el || el.tagName === "SELECT") return;
  const id = Number(el.dataset.id);
  switch (el.dataset.action) {
    case "open-cart": toggleCart(true); break;
    case "close-cart": toggleCart(false); break;
    case "close-dialog": el.closest("dialog").close(); break;
    case "account": if (state.user) logout(); else { toggleCart(false); openAuth(); } break;
    case "add": addToCart(id); break;
    case "qty": setQty(id, Number(el.dataset.q)); break;
    case "checkout": openCheckout(); break;
    case "category": state.filters.category = el.dataset.id ? id : null; renderChips(); loadProducts(true); break;
    case "more": state.filters.page++; loadProducts(false); break;
    case "pay": payOrder(id); break;
    case "cancel-order": cancelOrder(id); break;
    case "admin-tab": state.adminTab = el.dataset.tab; renderAdmin(); break;
    case "product-new": openProductDialog(null); break;
    case "product-edit": openProductDialog(state.adminProducts.find((p) => p.id === id)); break;
    case "user-status": setUserStatus(id, el.dataset.active === "true"); break;
  }
});

(async function init() {
  await guard(async () => { state.categories = await api("/categories"); });
  await loadUser();
  renderChrome();
  route();
})();
