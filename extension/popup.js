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

  // For Flipkart/Amazon — scrape price in the browser via content script
  if (url.includes("flipkart.com") || url.includes("amazon.")) {
    setTracking(true);
    $("track-result").classList.add("hidden");
    try {
      const data = await scrapeInBrowser(url);
      if (data) {
        await submitToBackend(url, data);
        return;
      }
    } catch(e) {
      // fall through to backend scrape
    } finally {
      setTracking(false);
    }
  }

  // Generic fallback: let backend scrape
  await backendTrack(url);
}

// Scrape price in the user's browser by fetching the page with browser credentials
async function scrapeInBrowser(url) {
  try {
    const resp = await fetch(url, {
      credentials: "include",
      headers: { "Accept": "text/html" },
    });
    const html = await resp.text();
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, "text/html");

    let price = null, title = null, image_url = null, site = "other";

    if (url.includes("flipkart.com")) {
      site = "flipkart";
      // Try CSS selectors
      const priceEl = doc.querySelector("div.Nx9bqj") || doc.querySelector("div._30jeq3");
      if (priceEl) price = parseFloat(priceEl.textContent.replace(/[^\d.]/g, ""));

      // Try JSON in script tags
      if (!price) {
        for (const script of doc.querySelectorAll("script")) {
          const t = script.textContent || "";
          const m = t.match(/"(?:finalPrice|sellingPrice)"\s*:\s*\{[^}]*"value"\s*:\s*(\d+)/)
                 || t.match(/"(?:finalPrice|sellingPrice)"\s*:\s*(\d+)/);
          if (m) { price = parseFloat(m[1]); break; }
        }
      }

      const titleEl = doc.querySelector("span.VU-ZEz") || doc.querySelector("span.B_NuCI") || doc.querySelector("h1");
      title = titleEl ? titleEl.textContent.trim() : "Flipkart Product";
      const imgEl = doc.querySelector("img.DByuf4") || doc.querySelector("img._396cs4");
      image_url = imgEl ? imgEl.src : null;

    } else if (url.includes("amazon.")) {
      site = "amazon";
      const priceEl = doc.querySelector("span.a-price-whole") || doc.querySelector("span.a-offscreen");
      if (priceEl) price = parseFloat(priceEl.textContent.replace(/[^\d.]/g, ""));
      const titleEl = doc.querySelector("span#productTitle");
      title = titleEl ? titleEl.textContent.trim() : "Amazon Product";
      const imgEl = doc.querySelector("img#landingImage");
      image_url = imgEl ? imgEl.src : null;
    }

    if (!price) return null;
    return { title, price, site, image_url, currency: "INR" };
  } catch(e) {
    return null;
  }
}

async function submitToBackend(url, data) {
  setTracking(true);
  $("track-result").classList.add("hidden");
  try {
    const resp = await fetch(config.apiBase + "/products/manual", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url, chat_id: config.chatId,
        title: data.title, price: data.price,
        site: data.site, image_url: data.image_url,
        currency: data.currency || "INR"
      }),
    });
    const result = await resp.json();
    if (!resp.ok) throw new Error(result.detail || "Failed");
    showSuccess(result);
  } catch(e) {
    showError(e.message);
  } finally {
    setTracking(false);
  }
}

async function backendTrack(url) {
  setTracking(true);
  $("track-result").classList.add("hidden");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 40000);
  try {
    const resp = await fetch(config.apiBase + "/products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, chat_id: config.chatId }),
      signal: controller.signal,
    });
    clearTimeout(timeout);
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Failed to track.");
    showSuccess(data);
  } catch(err) {
    const msg = err.name === "AbortError" ? "Request timed out." : err.message;
    showError(msg);
  } finally {
    setTracking(false);
  }
}

function showSuccess(data) {
  const siteLabel = { amazon: "🛒 Amazon", flipkart: "🛍️ Flipkart" }[data.site] || "🏪 " + data.site;
  const card = $("track-result");
  card.innerHTML =
    "<div class='product-title'>" + escHtml(data.title) + "</div>" +
    "<div class='product-price'>₹" + Number(data.price).toLocaleString("en-IN") + "</div>" +
    "<div class='product-site'>" + siteLabel + "</div>";
  card.classList.remove("hidden", "error");
  showToast("✅ Added!");
  $("product-url").value = "";
}

function showError(msg) {
  const card = $("track-result");
  card.innerHTML = "<div class='error-msg'>❌ " + escHtml(msg) + "</div>";
  card.classList.remove("hidden");
  card.classList.add("error");
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
