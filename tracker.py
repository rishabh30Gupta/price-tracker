#!/usr/bin/env python3
"""
Price Tracker
-------------
Reads URLs from urls.txt, fetches HTML via requests,
extracts price from embedded JSON data in the page,
compares with cached prices in prices.json,
sends Telegram alerts on price changes.
"""

import json
import os
import re
import logging
import subprocess
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


def fetch_html(url: str) -> str | None:
    """Use curl — proven to work from GitHub Actions with these exact flags."""
    try:
        result = subprocess.run(
            [
                "curl", "-s", "--compressed",
                "-L",                          # follow redirects
                "--max-time", "30",
                "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "-H", "Accept-Language: en-IN,en;q=0.9",
                "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "-H", "Referer: https://www.google.com/",
                url,
            ],
            capture_output=True,
            timeout=35,
        )
        html = result.stdout.decode("utf-8", errors="replace")
        logger.info(f"curl returned {len(html):,} chars, stderr: {result.stderr.decode()[:200]}")
        return html if len(html) > 10000 else None
    except Exception as e:
        logger.error(f"curl failed for {url}: {e}")
        return None


def extract_price(html: str, url: str) -> dict | None:
    """Extract price and title from embedded JSON in the HTML."""

    if "flipkart.com" in url:
        # Flipkart embeds product data as JSON in a <script> tag
        # Pattern: "price":67900 (the selling price appears as a standalone number)
        price = None

        # Try: {"price":NNNNN (most reliable — appears near product data)
        matches = re.findall(r'"price"\s*:\s*(\d{4,6})', html)
        if matches:
            # Filter to plausible phone/product price range (1000–200000)
            candidates = [int(x) for x in matches if 1000 <= int(x) <= 200000]
            if candidates:
                # Most frequent value = selling price (appears multiple times in JSON)
                from collections import Counter
                price = Counter(candidates).most_common(1)[0][0]

        # Fallback: finalPrice JSON
        if not price:
            m = re.search(r'"finalPrice"\s*:\s*\{"value"\s*:\s*(\d+)', html)
            if m:
                price = int(m.group(1))

        # Title: og:title meta tag
        title_m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', html)
        if not title_m:
            title_m = re.search(r'<title>(.*?)</title>', html)
        title = title_m.group(1).strip() if title_m else "Flipkart Product"
        title = re.sub(r'\s*[\|–-]\s*.*$', '', title).strip()  # remove "| Flipkart" suffix

        if not price:
            return None
        return {"title": title, "price": float(price), "site": "flipkart"}

    elif "amazon." in url:
        price = None

        # Amazon: "priceAmount":NNNNN or "price":"1,23,456"
        m = re.search(r'"priceAmount"\s*:\s*([\d.]+)', html)
        if m:
            price = float(m.group(1))

        if not price:
            m = re.search(r'"price"\s*:\s*"([\d,]+)"', html)
            if m:
                price = float(m.group(1).replace(",", ""))

        if not price:
            # Look for ₹ in raw HTML
            matches = re.findall(r'₹\s*([\d,]+)', html)
            candidates = [int(p.replace(",", "")) for p in matches
                         if p.replace(",", "").isdigit() and 1000 <= int(p.replace(",", "")) <= 500000]
            if candidates:
                from collections import Counter
                price = Counter(candidates).most_common(1)[0][0]

        title_m = re.search(r'<meta[^>]+name=["\']title["\'][^>]+content=["\'](.*?)["\']', html)
        if not title_m:
            title_m = re.search(r'<title>(.*?)</title>', html)
        title = title_m.group(1).strip() if title_m else "Amazon Product"
        title = re.sub(r'\s*[\|–-]\s*Amazon\..*$', '', title).strip()

        if not price:
            return None
        return {"title": title, "price": float(price), "site": "amazon"}

    else:
        # Generic
        matches = re.findall(r'₹\s*([\d,]+)', html)
        candidates = sorted(set(
            int(p.replace(",", "")) for p in matches
            if p.replace(",", "").isdigit() and int(p.replace(",", "")) >= 1000
        ))
        if not candidates:
            return None
        title_m = re.search(r'<title>(.*?)</title>', html)
        title = title_m.group(1).strip() if title_m else "Product"
        return {"title": title, "price": float(candidates[0]), "site": "other"}


def scrape_price(url: str) -> dict | None:
    for attempt in range(1, 3):
        html = fetch_html(url)
        if not html:
            logger.warning(f"Attempt {attempt}/2 — fetch returned nothing")
            continue

        logger.info(f"Fetched {len(html):,} chars")

        result = extract_price(html, url)
        if result:
            return result

        logger.warning(f"Attempt {attempt}/2 — no price extracted from HTML")

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
