// content.js — Firefox MV2, runs on Amazon/Flipkart pages
(function () {
  const url = window.location.href;
  const isProduct =
    (url.includes("amazon.") && (url.includes("/dp/") || url.includes("/gp/product/"))) ||
    (url.includes("flipkart.com") && url.includes("/p/"));

  if (!isProduct) return;

  function inject() {
    if (document.getElementById("pt-track-btn")) return;

    const btn = document.createElement("button");
    btn.id = "pt-track-btn";
    btn.textContent = "📈 Track Price";
    btn.style.cssText = [
      "display:inline-flex", "align-items:center", "gap:6px",
      "padding:8px 16px", "background:linear-gradient(135deg,#4361ee,#7209b7)",
      "color:#fff", "border:none", "border-radius:8px", "font-size:13px",
      "font-weight:600", "cursor:pointer", "margin-top:8px", "font-family:inherit",
      "box-shadow:0 2px 8px rgba(67,97,238,0.3)"
    ].join(";");

    btn.addEventListener("click", () => {
      browser.storage.local.set({ pendingUrl: window.location.href });
      btn.textContent = "✅ Open extension to track!";
      setTimeout(() => { btn.textContent = "📈 Track Price"; }, 3000);
    });

    const anchors = [
      document.getElementById("addToCart_feature_div"),
      document.getElementById("buyNow_feature_div"),
      document.querySelector("div._3pLy-c"),
      document.querySelector("div.CEmiEU"),
      document.querySelector("#centerCol"),
      document.querySelector(".DOjaWF"),
    ];

    for (const el of anchors) {
      if (el) { el.insertAdjacentElement("afterend", btn); return; }
    }
  }

  if (document.readyState === "complete") inject();
  else window.addEventListener("load", inject);
})();
