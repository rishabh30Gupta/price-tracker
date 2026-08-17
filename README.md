# 📈 Price Tracker

Track Amazon & Flipkart product prices and get **Telegram alerts** when prices drop.  
Manage products from the **Chrome Extension** or **Telegram Bot** — both are fully synced.

---

## Architecture

```
Chrome Extension  ←──────→  FastAPI Backend (Railway)  ←──────→  Telegram Bot
                                       ↑
                              GitHub Actions (every 6h)
                              triggers /check endpoint
```

---

## Setup Guide

### 1. Create Telegram Bot

1. Open Telegram → search **@BotFather**
2. Send `/newbot` and follow prompts
3. Copy the **bot token**
4. Start your bot and send `/start`
5. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your **chat_id**

---

### 2. Deploy Backend to Railway

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Select the repo, set **Root Directory** to `backend`
4. Add environment variables:
   ```
   TELEGRAM_TOKEN=your_bot_token_here
   DB_PATH=tracker.db
   ```
5. Railway will auto-deploy. Copy the public URL (e.g. `https://price-tracker-xyz.railway.app`)

> **Note:** Railway's free tier uses an ephemeral filesystem. For persistent storage, add a Railway Volume mounted at `/app` and set `DB_PATH=/app/tracker.db`.

---

### 3. Run Telegram Bot (as a separate Railway service)

In the same Railway project, add a second service:
- Root Directory: `backend`
- Start command: `python bot.py`
- Same environment variables as above, plus:
  ```
  API_BASE=https://your-api-url.railway.app
  ```

---

### 4. Set Up GitHub Actions (Price Checks every 6h)

Add these secrets to your GitHub repo (`Settings → Secrets → Actions`):

| Secret | Value |
|--------|-------|
| `TELEGRAM_TOKEN` | Your bot token |
| `API_BASE` | Your Railway backend URL |

The workflow in `.github/workflows/price-check.yml` will automatically run every 6 hours and ping your backend's `/check` endpoint.

---

### 5. Install Firefox Extension

1. Open Firefox → navigate to `about:debugging#/runtime/this-firefox`
2. Click **Load Temporary Add-on**
3. Select any file inside the `extension/` folder (e.g. `manifest.json`)
4. Click the extension icon → enter your:
   - **Telegram Chat ID** (from step 1)
   - **Backend URL** (from step 2)

> For permanent install, package it: `zip -r price-tracker.zip extension/` and submit to [addons.mozilla.org](https://addons.mozilla.org), or use it as a temporary add-on for personal use.

---

## Usage

### Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message + help |
| `/track <url>` | Start tracking a product |
| `/list` | View all tracked products |
| `/remove <id>` | Stop tracking a product |

### Chrome Extension

- **Track tab**: Paste a URL (auto-fills on Amazon/Flipkart pages) → click **Track Price**
- **My Products tab**: See all tracked products, remove any with 🗑
- On Amazon/Flipkart product pages, a **📈 Track Price** button is injected automatically

---

## Supported Sites

| Site | Support Level |
|------|--------------|
| Amazon India (amazon.in) | ✅ Full |
| Amazon US (amazon.com) | ✅ Full |
| Flipkart | ✅ Full |
| Other e-commerce sites | ⚡ Best-effort |

---

## Project Structure

```
price-tracker/
├── backend/
│   ├── main.py          # FastAPI REST API
│   ├── scraper.py       # Amazon + Flipkart price scraper
│   ├── checker.py       # Price check + Telegram alert logic
│   ├── bot.py           # Telegram bot
│   ├── requirements.txt
│   └── railway.toml
├── extension/
│   ├── manifest.json
│   ├── popup.html
│   ├── popup.css
│   ├── popup.js
│   ├── background.js
│   ├── content.js
│   └── icons/
└── .github/
    └── workflows/
        └── price-check.yml
```
