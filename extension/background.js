// background.js — Firefox MV2
browser.runtime.onInstalled.addListener((details) => {
  if (details.reason === "install") {
    browser.browserAction.openPopup().catch(() => {});
  }
});
