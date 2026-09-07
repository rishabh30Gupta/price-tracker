#!/usr/bin/env python3
"""
Price Tracker
-------------
Reads URLs from urls.txt, scrapes prices using Playwright headless Chromium,
compares with cached prices in prices.json, and sends Telegram alerts on changes.

Usage:
    python tracker.py

Environment variables:
    TELEGRAM_TOKEN   — bot token from @BotFather
    TELEGRAM_CHAT_ID — your chat ID
"""

import json
import os
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# --- Config ---
URLS_FILE        = Path(__file__).parent / "urls.txt"
PRICES_FILE      = Path(__file__).parent / "prices.json"
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "897964528")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Block these resource types to load pages faster
BLOCK_TYPES = {"image", "media", "font", "stylesheet"}

# JS: find leaf element with largest font size containing ₹ value ≥ 1000
PRICE_JS = (
    "() => {"
    "  var re = /^[\\u20b9$][0-9,]+$/;"
    "  var best = null, bestSize = 0;"
    "  document.querySelectorAll('*').forEach(function(el) {"
    "    var t = el.textContent.trim();"
    "    if (re.test(t) && el.children.length === 0) {"
    "      var val = parseFloat(t.replace(/[^0-9]/g, ''));"
    "      if (val < 1000) return;"
    "      var fs = parseFloat(window.getComputedStyle(el).fontSize) || 0;"
    "      if (fs > bestSize) { bestSize = fs; best = val; }"
    "    }"
    "  });"
    "  return best;"
    "}"
)


# --- Helpers ---
def load_urls() -> list[str]:
    if not URLS_FILE.exists():
        logger.error(f"{URLS_FILE} not found")
        return []
    urls = []
    for line in URLS_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def load_prices() -> dict:
    if not PRICES_FILE.exists():
        return {}
    try:
        return json.loads(PRICES_FILE.read_text())
    except Exception:
        return {}


def save_prices(prices: dict):
    PRICES_FILE.write_text(json.dumps(prices, indent=2))


def send_telegram(message: str):
    if not TELEGRAM_TOKEN:
        logger.warning("TELEGRAM_TOKEN not set — skipping notification")
        return
    import urllib.request
    data = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                logger.info(f"Telegram notification sent to {TELEGRAM_CHAT_ID}")
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")


# --- Scraper (single browser instance for all URLs) ---
def scrape_all(urls: list[str]) -> dict[str, dict | None]:
    from playwright.sync_api import sync_playwright

    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-background-networking",
            ],
        )
        for url in urls:
            logger.info(f"Scraping: {url}")
            result = None
            for attempt in range(1, 3):  # 2 retries
                try:
                    result = _scrape_page(browser, url)
                    if result:
                        break
                    logger.warning(f"Attempt {attempt}/2 — no price found")
                except Exception as e:
                    logger.warning(f"Attempt {attempt}/2 failed: {e}")
            results[url] = result
        browser.close()
    return results


def _scrape_page(browser, url: str) -> dict | None:
    page = browser.new_page(
        user_agent=UA,
        viewport={"width": 1280, "height": 800},
    )
    try:
        # Block heavy resources — images, fonts, stylesheets, media
        page.route("**/*", lambda route: (
            route.abort() if route.request.resource_type in BLOCK_TYPES
            else route.continue_()
        ))

        # Use "commit" — fires as soon as the server responds (faster than domcontentloaded)
        page.goto(url, wait_until="commit", timeout=60000)

        # Wait for price element (up to 20s) — much more reliable than fixed sleep
        if "flipkart.com" in url:
            try:
                page.wait_for_selector("div.Nx9bqj, div._30jeq3, div.CEmiEU", timeout=20000)
            except Exception:
                pass
        elif "amazon." in url:
            try:
                page.wait_for_selector(
                    "span.a-price-whole, #priceblock_ourprice, #corePriceDisplay_desktop_feature_div",
                    timeout=20000
                )
            except Exception:
                pass

        final_url = page.url

        # Title
        title = None
        if "flipkart.com" in final_url:
            for sel in ["span.VU-ZEz", "span.B_NuCI", "h1"]:
                el = page.query_selector(sel)
                if el:
                    title = el.text_content().strip()
                    break
        elif "amazon." in final_url:
            el = page.query_selector("span#productTitle")
            if el:
                title = el.text_content().strip()
        title = title or page.title().split("|")[0].strip()

        # Price
        price = page.evaluate(PRICE_JS)

        if not price:
            logger.warning(f"No price found for {url}")
            return None

        site = (
            "flipkart" if "flipkart.com" in final_url
            else "amazon" if "amazon." in final_url
            else "other"
        )
        return {"title": title, "price": float(price), "site": site}

    finally:
        page.close()


# --- Main ---
def main():
    urls = load_urls()
    if not urls:
        logger.info("No URLs to check. Add some to urls.txt")
        return

    prices = load_prices()
    logger.info(f"Checking {len(urls)} product(s)...")

    results = scrape_all(urls)

    for url, data in results.items():
        if not data:
            logger.warning(f"Skipping {url} — could not scrape")
            continue

        new_price = data["price"]
        title     = data["title"]
        site      = data["site"]
        emoji     = {"flipkart": "🛍️", "amazon": "🛒"}.get(site, "🏪")

        logger.info(f"  {title[:60]} → ₹{new_price:,.0f}")

        if url not in prices:
            prices[url] = new_price
            msg = (
                f"{emoji} <b>Now Tracking!</b>\n\n"
                f"<b>{title}</b>\n\n"
                f"💰 Current Price: <b>₹{new_price:,.0f}</b>\n\n"
                f"🔗 <a href=\"{url}\">View Product</a>"
            )
            send_telegram(msg)
            logger.info(f"  → First check, saved ₹{new_price:,.0f}")

        else:
            old_price = prices[url]

            if new_price < old_price:
                diff = old_price - new_price
                pct  = (diff / old_price) * 100
                msg = (
                    f"{emoji} <b>Price Drop! 🎉</b>\n\n"
                    f"<b>{title}</b>\n\n"
                    f"💰 Was: <s>₹{old_price:,.0f}</s>\n"
                    f"🔥 Now: <b>₹{new_price:,.0f}</b>\n"
                    f"📉 You save: ₹{diff:,.0f} ({pct:.1f}% off)\n\n"
                    f"🔗 <a href=\"{url}\">Buy Now</a>"
                )
                send_telegram(msg)
                prices[url] = new_price
                logger.info(f"  → DROP ₹{old_price:,.0f} → ₹{new_price:,.0f}")

            elif new_price > old_price:
                diff = new_price - old_price
                pct  = (diff / old_price) * 100
                msg = (
                    f"{emoji} <b>Price Increased! 📈</b>\n\n"
                    f"<b>{title}</b>\n\n"
                    f"💰 Was: ₹{old_price:,.0f}\n"
                    f"📈 Now: <b>₹{new_price:,.0f}</b>\n"
                    f"⚠️ Increased by: ₹{diff:,.0f} (+{pct:.1f}%)\n\n"
                    f"🔗 <a href=\"{url}\">View Product</a>"
                )
                send_telegram(msg)
                prices[url] = new_price
                logger.info(f"  → INCREASE ₹{old_price:,.0f} → ₹{new_price:,.0f}")

            else:
                logger.info(f"  → No change: ₹{new_price:,.0f}")

    save_prices(prices)
    logger.info("Done. Prices saved to prices.json")


if __name__ == "__main__":
    main()
