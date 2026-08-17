"""
Price checker script — run by GitHub Actions every 6 hours.
Checks all tracked products and sends Telegram alerts on price drops.
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
API_BASE = os.environ.get("API_BASE", "http://localhost:8000")


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
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")


def check_prices():
    from scraper import scrape_product

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    products = conn.execute("SELECT * FROM products").fetchall()
    logger.info(f"Checking {len(products)} products...")

    for product in products:
        pid = product["id"]
        url = product["url"]
        old_price = product["current_price"]
        chat_id = product["chat_id"]
        title = product["title"]

        logger.info(f"Checking: {title} ({url})")
        data = scrape_product(url)

        if not data or data["price"] is None:
            logger.warning(f"Could not scrape product {pid}")
            continue

        new_price = data["price"]
        now = datetime.utcnow().isoformat()

        # Always record price history
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
            drop = old_price - new_price
            pct = (drop / old_price) * 100
            site_emoji = {"amazon": "🛒", "flipkart": "🛍️"}.get(data["site"], "🏪")
            msg = (
                f"{site_emoji} <b>Price Drop Alert!</b>\n\n"
                f"<b>{data['title']}</b>\n\n"
                f"💰 Old Price: <s>₹{old_price:,.0f}</s>\n"
                f"🔥 New Price: <b>₹{new_price:,.0f}</b>\n"
                f"📉 Saved: ₹{drop:,.0f} ({pct:.1f}% off)\n\n"
                f"🔗 <a href=\"{url}\">Buy Now</a>"
            )
            send_telegram(chat_id, msg)
            logger.info(f"Alert sent to {chat_id} — drop ₹{drop:,.0f} on {title}")
        else:
            logger.info(f"No drop for {title}: ₹{old_price} → ₹{new_price}")

    conn.close()
    logger.info("Price check complete.")


if __name__ == "__main__":
    check_prices()
