// popup.js — Price Tracker Extension (Firefox MV2)

const $ = (id) => document.getElementById(id);
let config = { chatId: "", apiBase: "" };

// --- Init ---
document.addEventListener("DOMContentLoaded", () => {
  config = getConfig(); // always has values due to DEFAULTS
  showScreen("main-screen");
  autoFillCurrentTab();
  loadProducts();
  bindEvents();
});

// --- Screen / Tab helpers ---
function showScreen(id) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.add("hidden"));
  $(id).classList.remove("hidden");
}

function showTab(name) {
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.tab === name)
  );
  document.querySelectorAll(".tab-content").forEach((c) => c.classList.add("hidden"));
  $("tab-" + name).classList.remove("hidden");
  if (name === "list") loadProducts();
}

// --- Defaults (pre-filled so you never have to type them again) ---
const DEFAULTS = {
  chatId: "897964528",
  apiBase: "https://price-tracker-production-1fe4.up.railway.app",
};

// --- Storage — uses localStorage with DEFAULTS fallback ---
function getConfig() {
  return {
    chatId: localStorage.getItem("pt_chatId") || DEFAULTS.chatId,
    apiBase: localStorage.getItem("pt_apiBase") || DEFAULTS.apiBase,
  };
}

function saveConfig(chatId, apiBase) {
  localStorage.setItem("pt_chatId", chatId);
  localStorage.setItem("pt_apiBase", apiBase);
  // Also try browser.storage but don't depend on it
  try {
    browser.storage.local.set({ chatId, apiBase });
  } catch (e) {}
}

// --- Auto-fill URL ---
async function autoFillCurrentTab() {
  try {
    const data = await browser.storage.local.get(["pendingUrl"]);
    if (data.pendingUrl) {
      $("product-url").value = data.pendingUrl;
      await browser.storage.local.remove("pendingUrl");
      showTab("track");
      return;
    }
    const tabs = await browser.tabs.query({ active: true, currentWindow: true });
    const tab = tabs && tabs[0];
    if (tab && tab.url && (tab.url.includes("amazon.") || tab.url.includes("flipkart.com"))) {
      $("product-url").value = tab.url;
    }
  } catch (e) {
    // non-critical, ignore
  }
}

// --- Bind Events ---
function bindEvents() {
  $("save-setup-btn").addEventListener("click", () => {
    const chatId = $("chat-id-input").value.trim();
    const apiBase = $("api-url-input").value.trim().replace(/\/$/, "");
    if (!chatId || !apiBase) { showToast("Please fill in both fields."); return; }
    saveConfig(chatId, apiBase);
    config = { chatId, apiBase };
    showScreen("main-screen");
    autoFillCurrentTab();
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
  if (!url.startsWith("http")) { showToast("Invalid URL."); return; }

  // Short/share URLs aren't scrapable — ask for the full product page URL
  if (url.includes("dl.flipkart.com") || url.includes("fkrt.it") ||
      url.includes("amzn.in") || url.includes("amzn.to")) {
    const card = $("track-result");
    card.innerHTML = "<div class='error-msg'>⚠️ Short/share URLs aren't supported.<br><br>Please open the product in your browser and copy the <b>full URL</b> from the address bar (it should start with <b>amazon.in/dp/</b> or <b>flipkart.com/...</b>)</div>";
    card.classList.remove("hidden");
    card.classList.add("error");
    return;
  }

  setTracking(true);
  $("track-result").classList.add("hidden");

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 40000); // 40s timeout

    const resp = await fetch(config.apiBase + "/products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url, chat_id: config.chatId }),
      signal: controller.signal,
    });
    clearTimeout(timeout);
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Failed to track.");

    const siteLabel = { amazon: "🛒 Amazon", flipkart: "🛍️ Flipkart" }[data.site] || "🏪 " + data.site;
    const card = $("track-result");
    card.innerHTML =
      "<div class='product-title'>" + escHtml(data.title) + "</div>" +
      "<div class='product-price'>₹" + Number(data.price).toLocaleString("en-IN") + "</div>" +
      "<div class='product-site'>" + siteLabel + "</div>";
    card.classList.remove("hidden", "error");
    showToast("✅ Added!");
    $("product-url").value = "";
  } catch (err) {
    const msg = err.name === "AbortError"
      ? "Request timed out. The product page took too long to load."
      : err.message;
    const card = $("track-result");
    card.innerHTML = "<div class='error-msg'>❌ " + escHtml(msg) + "</div>";
    card.classList.remove("hidden");
    card.classList.add("error");
  } finally {
    setTracking(false);
  }
}

function setTracking(on) {
  $("track-btn").disabled = on;
  $("track-btn-text").textContent = on ? "Fetching..." : "Track Price";
  $("track-spinner").classList.toggle("hidden", !on);
}

// --- Products List ---
async function loadProducts() {
  const listEl = $("products-list");
  const emptyEl = $("products-empty");
  const loadingEl = $("products-loading");

  listEl.innerHTML = "";
  emptyEl.classList.add("hidden");
  loadingEl.classList.remove("hidden");

  try {
    const resp = await fetch(config.apiBase + "/products/" + encodeURIComponent(config.chatId));
    if (!resp.ok) throw new Error("API error");
    const products = await resp.json();
    loadingEl.classList.add("hidden");

    if (!products.length) {
      emptyEl.classList.remove("hidden");
      return;
    }
    products.forEach((p) => listEl.appendChild(buildCard(p)));
  } catch (e) {
    loadingEl.classList.add("hidden");
    listEl.innerHTML = "<p style='color:#dc3545;font-size:13px;padding:8px 0'>Could not load. Check backend URL in settings.</p>";
  }
}

function buildCard(p) {
  const div = document.createElement("div");
  div.className = "product-item";
  const emoji = { amazon: "🛒", flipkart: "🛍️" }[p.site] || "🏪";
  const price = "₹" + Number(p.current_price).toLocaleString("en-IN");
  const strikethrough = (p.initial_price && p.initial_price !== p.current_price)
    ? " <span class='initial-price'>₹" + Number(p.initial_price).toLocaleString("en-IN") + "</span>"
    : "";

  div.innerHTML =
    (p.image_url ? "<img class='thumb' src='" + escHtml(p.image_url) + "' alt='' onerror=\"this.style.display='none'\" />" : "") +
    "<div class='info'>" +
      "<div class='name' title='" + escHtml(p.title) + "'>" + escHtml(p.title) + "</div>" +
      "<div class='price'>" + price + strikethrough + "</div>" +
      "<div class='meta'>" + emoji + " " + escHtml(p.site) + " &nbsp;•&nbsp; ID: " + p.id + "</div>" +
    "</div>" +
    "<button class='remove-btn' title='Remove'>🗑</button>";

  div.querySelector(".remove-btn").addEventListener("click", () => removeProduct(p.id, div));
  return div;
}

async function removeProduct(id, el) {
  el.style.opacity = "0.5";
  try {
    const resp = await fetch(config.apiBase + "/products/" + id, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: config.chatId }),
    });
    if (!resp.ok) throw new Error();
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
  let t = document.querySelector(".toast");
  if (!t) {
    t = document.createElement("div");
    t.className = "toast";
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2500);
}

function escHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
