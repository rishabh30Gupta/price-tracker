// popup.js — Price Tracker Extension (Firefox MV2)
// Uses `browser` API (Firefox native) with chrome fallback for compatibility

const api = typeof browser !== "undefined" ? browser : chrome;
const $ = (id) => document.getElementById(id);

let config = { chatId: "", apiBase: "" };

// --- Init ---
document.addEventListener("DOMContentLoaded", async () => {
  config = await getConfig();

  if (!config.chatId || !config.apiBase) {
    showScreen("setup-screen");
    if (config.apiBase) $("api-url-input").value = config.apiBase;
    if (config.chatId) $("chat-id-input").value = config.chatId;
  } else {
    showScreen("main-screen");
    await autoFillCurrentTab();
    loadProducts();
  }

  bindEvents();
});

function showScreen(id) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.add("hidden"));
  $(id).classList.remove("hidden");
}

function showTab(name) {
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.tab === name)
  );
  document.querySelectorAll(".tab-content").forEach((c) => c.classList.add("hidden"));
  $(`tab-${name}`).classList.remove("hidden");
  if (name === "list") loadProducts();
}

// --- Storage (Promise-based for Firefox) ---
function getConfig() {
  return new Promise((resolve) => {
    api.storage.local.get(["chatId", "apiBase"], (data) => {
      resolve({ chatId: data.chatId || "", apiBase: data.apiBase || "" });
    });
  });
}

function saveConfig(chatId, apiBase) {
  return new Promise((resolve) => {
    api.storage.local.set({ chatId, apiBase }, resolve);
  });
}

// --- Auto-fill: check pendingUrl set by content.js, else use active tab ---
async function autoFillCurrentTab() {
  return new Promise((resolve) => {
    // First check if content.js stored a pending URL (from "Track Price" button click)
    api.storage.local.get(["pendingUrl"], (data) => {
      if (data.pendingUrl) {
        $("product-url").value = data.pendingUrl;
        api.storage.local.remove("pendingUrl");
        showTab("track");
        resolve();
        return;
      }

      // Fallback: read active tab URL
      api.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        const tab = tabs && tabs[0];
        if (tab?.url && (tab.url.includes("amazon.") || tab.url.includes("flipkart.com"))) {
          $("product-url").value = tab.url;
        }
        resolve();
      });
    });
  });
}

// --- Events ---
function bindEvents() {
  $("save-setup-btn").addEventListener("click", async () => {
    const chatId = $("chat-id-input").value.trim();
    const apiBase = $("api-url-input").value.trim().replace(/\/$/, "");
    if (!chatId || !apiBase) {
      showToast("Please fill in both fields.");
      return;
    }
    await saveConfig(chatId, apiBase);
    config = { chatId, apiBase };
    showScreen("main-screen");
    await autoFillCurrentTab();
    loadProducts();
  });

  $("settings-btn").addEventListener("click", () => {
    showScreen("setup-screen");
    $("chat-id-input").value = config.chatId;
    $("api-url-input").value = config.apiBase;
  });

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => showTab(btn.dataset.tab));
  });

  $("track-btn").addEventListener("click", trackProduct);
  $("product-url").addEventListener("keydown", (e) => {
    if (e.key === "Enter") trackProduct();
  });

  $("refresh-btn").addEventListener("click", loadProducts);
}

// --- Track Product ---
async function trackProduct() {
  const url = $("product-url").value.trim();
  if (!url) { showToast("Paste a product URL first."); return; }
  if (!url.startsWith("http")) { showToast("Invalid URL — must start with http/https."); return; }

  setTracking(true);
  hideResult();

  try {
    const resp = await fetch(`${config.apiBase}/products`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, chat_id: config.chatId }),
    });

    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Failed to track product.");

    showResult({ title: data.title, price: data.price, site: data.site });
    showToast("✅ Product added!");
    $("product-url").value = "";
  } catch (err) {
    showResultError(err.message);
  } finally {
    setTracking(false);
  }
}

function setTracking(loading) {
  $("track-btn").disabled = loading;
  $("track-btn-text").textContent = loading ? "Fetching..." : "Track Price";
  $("track-spinner").classList.toggle("hidden", !loading);
}

function showResult({ title, price, site }) {
  const card = $("track-result");
  const siteLabel = { amazon: "🛒 Amazon", flipkart: "🛍️ Flipkart" }[site] || "🏪 " + site;
  card.innerHTML = `
    <div class="product-title">${escHtml(title)}</div>
    <div class="product-price">₹${Number(price).toLocaleString("en-IN")}</div>
    <div class="product-site">${siteLabel}</div>
  `;
  card.classList.remove("hidden", "error");
}

function showResultError(msg) {
  const card = $("track-result");
  card.innerHTML = `<div class="error-msg">❌ ${escHtml(msg)}</div>`;
  card.classList.remove("hidden");
  card.classList.add("error");
}

function hideResult() {
  $("track-result").classList.add("hidden");
}

// --- Load Products ---
async function loadProducts() {
  const listEl = $("products-list");
  const emptyEl = $("products-empty");
  const loadingEl = $("products-loading");

  listEl.innerHTML = "";
  emptyEl.classList.add("hidden");
  loadingEl.classList.remove("hidden");

  try {
    const resp = await fetch(
      `${config.apiBase}/products/${encodeURIComponent(config.chatId)}`
    );
    if (!resp.ok) throw new Error("API error");
    const products = await resp.json();

    loadingEl.classList.add("hidden");

    if (!products.length) {
      emptyEl.classList.remove("hidden");
      return;
    }

    products.forEach((p) => listEl.appendChild(buildProductCard(p)));
  } catch (err) {
    loadingEl.classList.add("hidden");
    listEl.innerHTML = `<p style="color:#dc3545;font-size:13px;padding:8px 0;">
      Could not load products. Check your backend URL in settings.
    </p>`;
  }
}

function buildProductCard(p) {
  const div = document.createElement("div");
  div.className = "product-item";

  const siteEmoji = { amazon: "🛒", flipkart: "🛍️" }[p.site] || "🏪";
  const priceStr = `₹${Number(p.current_price).toLocaleString("en-IN")}`;
  const initialStr = p.initial_price !== p.current_price
    ? ` <span class="initial-price">₹${Number(p.initial_price).toLocaleString("en-IN")}</span>`
    : "";

  div.innerHTML = `
    ${p.image_url
      ? `<img class="thumb" src="${escHtml(p.image_url)}" alt=""
           onerror="this.style.display='none'" />`
      : ""}
    <div class="info">
      <div class="name" title="${escHtml(p.title)}">${escHtml(p.title)}</div>
      <div class="price">${priceStr}${initialStr}</div>
      <div class="meta">${siteEmoji} ${escHtml(p.site)} &nbsp;•&nbsp; ID: ${p.id}</div>
    </div>
    <button class="remove-btn" data-id="${p.id}" title="Stop tracking">🗑</button>
  `;

  div.querySelector(".remove-btn").addEventListener("click", () =>
    removeProduct(p.id, div)
  );
  return div;
}

async function removeProduct(id, el) {
  el.style.opacity = "0.5";
  try {
    const resp = await fetch(`${config.apiBase}/products/${id}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: config.chatId }),
    });
    if (!resp.ok) throw new Error("Failed");
    el.remove();
    showToast("🗑 Removed");
    if (!$("products-list").children.length) {
      $("products-empty").classList.remove("hidden");
    }
  } catch {
    el.style.opacity = "1";
    showToast("Could not remove. Try again.");
  }
}

// --- Toast ---
function showToast(msg) {
  let toast = document.querySelector(".toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2500);
}

// --- Helpers ---
function escHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
