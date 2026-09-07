"""
Price checker — triggered by GitHub Actions every 6 hours via POST /check.
Uses Playwright headless browser to scrape Flipkart & Amazon.
Sends Telegram alerts on both price drops and price increases.
"""
import sqlite3
import os
import requests
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", "tracker.db")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")


def send_telegram(chat_id: str, message: str):
    if not TELEGRAM_TOKEN:
        logger.warning("TELEGRAM_TOKEN not set, skipping notification")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }, timeout=10)
        resp.raise_for_status()
        logger.info(f"Telegram notification sent to {chat_id}")
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")


def check_prices():
    from scraper import scrape_product

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    products = conn.execute("SELECT * FROM products").fetchall()
    logger.info(f"Starting price check for {len(products)} products...")

    for product in products:
        pid = product["id"]
        url = product["url"]
        old_price = product["current_price"]
        chat_id = product["chat_id"]
        title = product["title"]

        logger.info(f"[{pid}] Checking: {title[:50]}")

        data = scrape_product(url)

        if not data or data["price"] is None:
            logger.warning(f"[{pid}] Could not scrape — skipping")
            continue

        new_price = data["price"]
        now = datetime.utcnow().isoformat()
        site_emoji = {"amazon": "🛒", "flipkart": "🛍️"}.get(data["site"], "🏪")

        # Always update DB
        conn.execute(
            "INSERT INTO price_history (product_id, price) VALUES (?, ?)",
            (pid, new_price)
        )
        conn.execute(
            "UPDATE products SET current_price = ?, last_checked = ?, title = ? WHERE id = ?",
            (new_price, now, data["title"], pid)
        )
        conn.commit()

        if new_price < old_price:
            diff = old_price - new_price
            pct = (diff / old_price) * 100
            msg = (
                f"{site_emoji} <b>Price Drop Alert! 🎉</b>\n\n"
                f"<b>{data['title']}</b>\n\n"
                f"💰 Was: <s>₹{old_price:,.0f}</s>\n"
                f"🔥 Now: <b>₹{new_price:,.0f}</b>\n"
                f"📉 You save: ₹{diff:,.0f} ({pct:.1f}% off)\n\n"
                f"🔗 <a href=\"{url}\">Buy Now</a>"
            )
            send_telegram(chat_id, msg)
            logger.info(f"[{pid}] DROP ₹{old_price:,.0f} → ₹{new_price:,.0f} (-₹{diff:,.0f})")

        elif new_price > old_price:
            diff = new_price - old_price
            pct = (diff / old_price) * 100
            msg = (
                f"{site_emoji} <b>Price Increase Alert! 📈</b>\n\n"
                f"<b>{data['title']}</b>\n\n"
                f"💰 Was: ₹{old_price:,.0f}\n"
                f"📈 Now: <b>₹{new_price:,.0f}</b>\n"
                f"⚠️ Increased by: ₹{diff:,.0f} (+{pct:.1f}%)\n\n"
                f"🔗 <a href=\"{url}\">View Product</a>"
            )
            send_telegram(chat_id, msg)
            logger.info(f"[{pid}] INCREASE ₹{old_price:,.0f} → ₹{new_price:,.0f} (+₹{diff:,.0f})")

        else:
            logger.info(f"[{pid}] No change: ₹{new_price:,.0f}")

    conn.close()
    logger.info("Price check complete.")


if __name__ == "__main__":
    check_prices()
