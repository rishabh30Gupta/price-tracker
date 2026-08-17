// popup.js — Price Tracker Extension (Firefox MV2)

const $ = (id) => document.getElementById(id);
let config = { chatId: "", apiBase: "" };

// --- Init ---
document.addEventListener("DOMContentLoaded", () => {
  config = getConfig();
  showScreen("main-screen");
  autoFillCurrentTab();
  loadProducts();
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
  $("tab-" + name).classList.remove("hidden");
  if (name === "list") loadProducts();
}

// --- Defaults ---
const DEFAULTS = {
  chatId: "897964528",
  apiBase: "https://price-tracker-production-1fe4.up.railway.app",
};

function getConfig() {
  return {
    chatId: localStorage.getItem("pt_chatId") || DEFAULTS.chatId,
    apiBase: localStorage.getItem("pt_apiBase") || DEFAULTS.apiBase,
  };
}

function saveConfig(chatId, apiBase) {
  localStorage.setItem("pt_chatId", chatId);
  localStorage.setItem("pt_apiBase", apiBase);
  try { browser.storage.local.set({ chatId, apiBase }); } catch(e) {}
}

// --- Auto-fill URL — only on actual product pages ---
async function autoFillCurrentTab() {
  try {
    const tabs = await browser.tabs.query({});
    const productTab = tabs.find(t => {
      if (!t.url) return false;
      const u = t.url;
      // Only actual product pages, not search/category pages
      return (u.includes("flipkart.com") && u.includes("/p/")) ||
             (u.includes("amazon.") && (u.includes("/dp/") || u.includes("/gp/product/")));
    });
    if (productTab) $("product-url").value = productTab.url;
  } catch(e) {}
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

  if (url.includes("dl.flipkart.com") || url.includes("fkrt.it") ||
      url.includes("amzn.in") || url.includes("amzn.to")) {
    showError("⚠️ Short/share URLs aren't supported. Open the product page and copy the full URL from the address bar.");
    return;
  }

  if (url.includes("flipkart.com") || url.includes("amazon.")) {
    setTracking(true);
    $("track-result").classList.add("hidden");
    try {
      const data = await scrapeInBrowser(url);
      if (data && data.price) {
        await submitToBackend(url, data);
      } else {
        showError("Could not read price. Make sure the product page is open and fully loaded.");
      }
    } catch(e) {
      showError(e.message || "Could not read price from page.");
    } finally {
      setTracking(false);
    }
    return;
  }

  await backendTrack(url);
}

// --- Scrape from live tab DOM (finds tab by URL, not active state) ---
async function scrapeInBrowser(url) {
  // Find the tab that matches the product URL
  const allTabs = await browser.tabs.query({});
  const normalizedUrl = url.split("?")[0].split("#")[0]; // strip query params
  let tab = allTabs.find(t => t.url && t.url.startsWith(normalizedUrl));

  // Fallback: find any flipkart/amazon tab
  if (!tab) {
    if (url.includes("flipkart.com")) {
      tab = allTabs.find(t => t.url && t.url.includes("flipkart.com"));
    } else if (url.includes("amazon.")) {
      tab = allTabs.find(t => t.url && t.url.includes("amazon."));
    }
  }

  if (!tab) throw new Error("Product tab not found. Make sure the product page is open in a tab.");

  const results = await browser.tabs.executeScript(tab.id, {
    code: `
      (function() {
        let price = null, title = null, image_url = null, site = "other";

        if (location.href.includes("flipkart.com")) {
          site = "flipkart";

          // Try specific selling price selectors (both classes = selling price, single class = MRP)
          const priceSelectors = [
            "div.Nx9bqj.CxhGGd",
            "div._30jeq3._16Jk6d",
            "div._30jeq3",
            "div.hl05eU div.Nx9bqj",
            "div.CEmiEU div.Nx9bqj"
          ];
          for (const sel of priceSelectors) {
            const el = document.querySelector(sel);
            if (el) {
              const val = parseFloat(el.textContent.replace(/[^\\d]/g, ""));
              if (val > 0) { price = val; break; }
            }
          }

          // Fallback: find the largest-font ₹ element on page (that's the selling price)
          if (!price) {
            let maxSize = 0;
            document.querySelectorAll("*").forEach(el => {
              if (el.children.length === 0 && el.textContent.includes("₹")) {
                const txt = el.textContent.trim();
                const m = txt.match(/^₹([\\d,]+)$/);
                if (m) {
                  const val = parseFloat(m[1].replace(/,/g, ""));
                  if (val > 1000) { // skip tiny values like ₹5 off coupons
                    const fs = parseFloat(window.getComputedStyle(el).fontSize) || 0;
                    if (fs > maxSize) { maxSize = fs; price = val; }
                  }
                }
              }
            });
          }

          const titleEl = document.querySelector("span.VU-ZEz")
                        || document.querySelector("span.B_NuCI")
                        || document.querySelector("h1");
          title = titleEl ? titleEl.textContent.trim() : document.title.split("|")[0].trim();
          const imgEl = document.querySelector("img.DByuf4") || document.querySelector("img._396cs4");
          image_url = imgEl ? imgEl.src : null;

        } else if (location.href.includes("amazon.")) {
          site = "amazon";
          const priceSelectors = [
            "span.a-price-whole",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            "#price_inside_buybox",
            ".a-price .a-offscreen"
          ];
          for (const sel of priceSelectors) {
            const el = document.querySelector(sel);
            if (el) {
              const val = parseFloat(el.textContent.replace(/[^\\d.]/g, ""));
              if (val > 0) { price = val; break; }
            }
          }
          const titleEl = document.querySelector("span#productTitle");
          title = titleEl ? titleEl.textContent.trim() : document.title;
          const imgEl = document.querySelector("img#landingImage");
          image_url = imgEl ? imgEl.src : null;
        }

        return { price, title, site, image_url };
      })()
    `
  });

  const data = results && results[0];
  if (!data || !data.price) return null;
  return { ...data, currency: "INR" };
}

async function submitToBackend(url, data) {
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
  }
}

async function backendTrack(url) {
  setTracking(true);
  $("track-result").classList.add("hidden");
  const controller = new AbortController();
  const tid = setTimeout(() => controller.abort(), 40000);
  try {
    const resp = await fetch(config.apiBase + "/products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, chat_id: config.chatId }),
      signal: controller.signal,
    });
    clearTimeout(tid);
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Failed");
    showSuccess(data);
  } catch(e) {
    showError(e.name === "AbortError" ? "Request timed out." : e.message);
  } finally {
    setTracking(false);
  }
}

function showSuccess(data) {
  const siteLabel = { amazon: "🛒 Amazon", flipkart: "🛍️ Flipkart" }[data.site] || "🏪 " + data.site;
  const dupNote = data.duplicate ? "<div style='color:#856404;font-size:11px;margin-top:4px;'>⚠️ Already tracking this product</div>" : "";
  const card = $("track-result");
  card.innerHTML =
    "<div class='product-title'>" + escHtml(data.title) + "</div>" +
    "<div class='product-price'>₹" + Number(data.price).toLocaleString("en-IN") + "</div>" +
    "<div class='product-site'>" + siteLabel + "</div>" + dupNote;
  card.classList.remove("hidden", "error");
  showToast(data.duplicate ? "⚠️ Already tracking!" : "✅ Added!");
  if (!data.duplicate) $("product-url").value = "";
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
    if (!products.length) { emptyEl.classList.remove("hidden"); return; }
    products.forEach((p) => listEl.appendChild(buildCard(p)));
  } catch(e) {
    loadingEl.classList.add("hidden");
    listEl.innerHTML = "<p style='color:#dc3545;font-size:13px;padding:8px 0'>Could not load. Check backend URL in settings.</p>";
  }
}

function buildCard(p) {
  const div = document.createElement("div");
  div.className = "product-item";
  const emoji = { amazon: "🛒", flipkart: "🛍️" }[p.site] || "🏪";
  const price = "₹" + Number(p.current_price).toLocaleString("en-IN");
  const strike = (p.initial_price && p.initial_price !== p.current_price)
    ? " <span class='initial-price'>₹" + Number(p.initial_price).toLocaleString("en-IN") + "</span>" : "";
  div.innerHTML =
    (p.image_url ? "<img class='thumb' src='" + escHtml(p.image_url) + "' alt='' onerror=\"this.style.display='none'\"/>" : "") +
    "<div class='info'>" +
      "<div class='name' title='" + escHtml(p.title) + "'>" + escHtml(p.title) + "</div>" +
      "<div class='price'>" + price + strike + "</div>" +
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
    if (!$("products-list").children.length) $("products-empty").classList.remove("hidden");
  } catch {
    el.style.opacity = "1";
    showToast("Could not remove. Try again.");
  }
}

function showToast(msg) {
  let t = document.querySelector(".toast");
  if (!t) { t = document.createElement("div"); t.className = "toast"; document.body.appendChild(t); }
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2500);
}

function escHtml(s) {
  return String(s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
