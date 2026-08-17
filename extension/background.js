// background.js — Background script for Price Tracker (Firefox MV2)
const api = typeof browser !== "undefined" ? browser : chrome;

api.runtime.onInstalled.addListener((details) => {
  if (details.reason === "install") {
    // Open popup on first install — Firefox supports this via browserAction
    api.browserAction.openPopup().catch(() => {});
  }
});
