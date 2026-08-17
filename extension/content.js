// content.js — runs on Amazon/Flipkart pages (Firefox MV2)
// Injects a "Track Price" button on product pages

(function () {
  const api = typeof browser !== "undefined" ? browser : chrome;

  const isProductPage = () => {
    const url = window.location.href;
    if (url.includes("amazon.") && (url.includes("/dp/") || url.includes("/gp/product/"))) return true;
    if (url.includes("flipkart.com") && url.includes("/p/")) return true;
    return false;
  };

  if (!isProductPage()) return;

  function injectTrackButton() {
    if (document.getElementById("pt-track-btn")) return;

    const btn = document.createElement("button");
    btn.id = "pt-track-btn";
    btn.textContent = "📈 Track Price";
    btn.style.cssText = `
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 16px;
      background: linear-gradient(135deg, #4361ee, #7209b7);
      color: #fff;
      border: none;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      margin-top: 8px;
      font-family: inherit;
      box-shadow: 0 2px 8px rgba(67,97,238,0.3);
    `;

    // Clicking stores the current URL and opens the popup
    btn.addEventListener("click", () => {
      api.storage.local.set({ pendingUrl: window.location.href }, () => {
        api.browserAction.openPopup().catch(() => {
          // openPopup requires user gesture in Firefox; as fallback show a notification
          btn.textContent = "✅ Open extension to track!";
          setTimeout(() => { btn.textContent = "📈 Track Price"; }, 3000);
        });
      });
    });

    const targets = [
      document.getElementById("addToCart_feature_div"),   // Amazon
      document.getElementById("buyNow_feature_div"),       // Amazon alt
      document.querySelector("div._3pLy-c"),               // Flipkart
      document.querySelector("div.CEmiEU"),                // Flipkart alt
    ];

    for (const target of targets) {
      if (target) {
        target.insertAdjacentElement("afterend", btn);
        return;
      }
    }

    // Fallback: append near the page top if no known anchor found
    const fallback = document.querySelector("#centerCol") || document.querySelector(".DOjaWF");
    if (fallback) fallback.prepend(btn);
  }

  if (document.readyState === "complete") {
    injectTrackButton();
  } else {
    window.addEventListener("load", injectTrackButton);
  }
})();
