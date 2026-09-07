# 📈 Price Tracker

Tracks Amazon & Flipkart product prices every 5 minutes via GitHub Actions.
Sends Telegram alerts when price drops or increases.

---

## How it works

```
Every 5 minutes
      ↓
GitHub Actions runs tracker.py
      ↓
Playwright headless Chromium opens each URL in urls.txt
      ↓
Extracts selling price from live rendered page
      ↓
Compares with cached price in prices.json
      ↓
Price dropped?   → 📉 Telegram alert
Price increased? → 📈 Telegram alert
No change?       → Silent, nothing sent
      ↓
Commits updated prices.json back to repo
```

---

## Setup

### 1. GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|--------|-------|
| `TELEGRAM_TOKEN` | Your bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |

### 2. Add products to track

Edit `urls.txt` — one URL per line:

```
https://www.flipkart.com/apple-iphone-16-white-128-gb/p/itm7c0281cd247be
https://www.amazon.in/dp/B0XXXXXXXXX
```

Lines starting with `#` are ignored.

### 3. Trigger manually (first run)

Go to **Actions → Price Tracker → Run workflow** to test it immediately.
After that it runs automatically every 5 minutes.

---

## Files

| File | Purpose |
|------|---------|
| `tracker.py` | Main script — scrapes, compares, alerts |
| `urls.txt` | List of product URLs to track |
| `prices.json` | Auto-updated price cache (do not edit manually) |
| `.github/workflows/price-check.yml` | GitHub Actions cron workflow |

---

## Adding / removing products

- **Add**: append URL to `urls.txt`, commit and push
- **Remove**: delete the URL from `urls.txt` and its entry from `prices.json`, commit and push

---

## Supported sites

| Site | Support |
|------|---------|
| Flipkart | ✅ Full |
| Amazon India | ✅ Full |
| Other sites | ⚡ Best-effort |
