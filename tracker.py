#!/usr/bin/env python3
"""
Price Tracker
-------------
Reads URLs from urls.txt, fetches HTML via requests (fast, no browser network),
evaluates JS price extraction via Playwright on the fetched HTML,
compares with cached prices in prices.json, sends Telegram alerts on changes.
"""

import json
import os
import re
import logging
import requests
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
    "DNT": "1",
}

# JS to extract price from rendered HTML — finds largest ₹ font element
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


# --- Fetch HTML via requests (bypasses Playwright network timeout issues) ---
def fetch_html(url: str) -> tuple[str, str] | None:
    """Returns (html, final_url) or None on failure."""
    try:
        session = requests.Session()
        # Visit homepage first to get cookies (helps bypass bot checks)
        base = "https://www.flipkart.com" if "flipkart" in url else "https://www.amazon.in"
        try:
            session.get(base, headers=HEADERS, timeout=15)
        except Exception:
            pass
        resp = session.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        resp.raise_for_status()
        return resp.text, resp.url
    except Exception as e:
        logger.error(f"fetch_html failed for {url}: {e}")
        return None


# --- Parse price from HTML using Playwright's JS engine ---
def parse_price_from_html(html: str, url: str) -> dict | None:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-dev-shm-usage", "--disable-gpu"],
            )
            page = browser.new_page(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 800},
            )
            # Set content directly — no network call from browser
            page.set_content(html, timeout=30000)

            # Title
            title = None
            if "flipkart.com" in url:
                for sel in ["span.VU-ZEz", "span.B_NuCI", "h1"]:
                    el = page.query_selector(sel)
                    if el:
                        title = el.text_content().strip()
                        break
            elif "amazon." in url:
                el = page.query_selector("span#productTitle")
                if el:
                    title = el.text_content().strip()
            title = title or page.title().split("|")[0].strip()

            # Price via JS
            price = page.evaluate(PRICE_JS)
            browser.close()

            if not price:
                # Fallback: regex on raw HTML
                price = _regex_price(html, url)

            if not price:
                return None

            site = (
                "flipkart" if "flipkart.com" in url
                else "amazon" if "amazon." in url
                else "other"
            )
            return {"title": title, "price": float(price), "site": site}

    except Exception as e:
        logger.error(f"parse_price_from_html error: {e}")
        return None


def _regex_price(html: str, url: str) -> float | None:
    """Fallback price extraction using regex on raw HTML."""
    if "flipkart.com" in url:
        # Flipkart JSON: {"finalPrice":{"value":67900
        m = re.search(r'"finalPrice"\s*:\s*\{"value"\s*:\s*(\d+)', html)
        if m:
            return float(m.group(1))
    # Generic: find ₹ followed by digits
    matches = re.findall(r'₹\s*([\d,]+)', html)
    prices = sorted(set(
        float(p.replace(",", "")) for p in matches
        if float(p.replace(",", "")) >= 1000
    ))
    return prices[0] if prices else None


# --- Scrape one URL ---
def scrape_price(url: str) -> dict | None:
    for attempt in range(1, 3):
        fetched = fetch_html(url)
        if not fetched:
            logger.warning(f"Attempt {attempt}/2 — fetch failed")
            continue
        html, final_url = fetched
        logger.info(f"Fetched {len(html):,} chars from {final_url[:60]}")

        if len(html) < 5000:
            logger.warning(f"Attempt {attempt}/2 — page too small ({len(html)} chars), likely bot block")
            continue

        result = parse_price_from_html(html, final_url)
        if result:
            return result
        logger.warning(f"Attempt {attempt}/2 — no price found in HTML")

    return None


# --- Main ---
def main():
    urls = load_urls()
    if not urls:
        logger.info("No URLs to check. Add some to urls.txt")
        return

    prices = load_prices()
    logger.info(f"Checking {len(urls)} product(s)...")

    for url in urls:
        logger.info(f"Scraping: {url}")
        data = scrape_price(url)

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
