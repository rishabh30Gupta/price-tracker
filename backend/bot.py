"""
Telegram bot for Price Tracker.
Commands:
  /start   — welcome + instructions
  /track <url> — add a product to track
  /list    — show all tracked products
  /remove <id> — stop tracking a product
  /help    — show help
"""
import os
import logging
import requests as http_requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
API_BASE = os.environ.get("API_BASE", "http://localhost:8000")


def api_add(url: str, chat_id: str):
    resp = http_requests.post(f"{API_BASE}/products", json={"url": url, "chat_id": chat_id}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def api_list(chat_id: str):
    resp = http_requests.get(f"{API_BASE}/products/{chat_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def api_remove(product_id: int, chat_id: str):
    resp = http_requests.delete(
        f"{API_BASE}/products/{product_id}",
        json={"chat_id": chat_id},
        timeout=10
    )
    resp.raise_for_status()
    return resp.json()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>Welcome to Price Tracker Bot!</b>\n\n"
        "I'll monitor Amazon & Flipkart products and alert you when prices drop.\n\n"
        "📌 <b>Commands:</b>\n"
        "/track &lt;url&gt; — Start tracking a product\n"
        "/list — View all tracked products\n"
        "/remove &lt;id&gt; — Stop tracking a product\n"
        "/help — Show this message\n\n"
        "💡 You can also manage products from the <b>browser extension</b>!",
        parse_mode="HTML"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text(
            "❌ Please provide a URL.\nUsage: /track &lt;product_url&gt;",
            parse_mode="HTML"
        )
        return

    url = context.args[0].strip()
    if not url.startswith("http"):
        await update.message.reply_text("❌ Invalid URL. Make sure it starts with http/https.")
        return

    msg = await update.message.reply_text("⏳ Fetching product details, please wait...")
    try:
        data = api_add(url, chat_id)
        site_emoji = {"amazon": "🛒", "flipkart": "🛍️"}.get(data.get("site", ""), "🏪")
        await msg.edit_text(
            f"{site_emoji} <b>Product added!</b>\n\n"
            f"📦 <b>{data['title']}</b>\n"
            f"💰 Current Price: <b>₹{data['price']:,.0f}</b>\n"
            f"🆔 Tracker ID: <code>{data['id']}</code>\n\n"
            f"I'll notify you when the price drops!",
            parse_mode="HTML"
        )
    except http_requests.HTTPError as e:
        detail = "Could not fetch product details. Make sure the URL is valid."
        try:
            detail = e.response.json().get("detail", detail)
        except Exception:
            pass
        await msg.edit_text(f"❌ {detail}")
    except Exception as e:
        logger.error(f"track error: {e}")
        await msg.edit_text("❌ Something went wrong. Try again later.")


async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    try:
        products = api_list(chat_id)
    except Exception as e:
        logger.error(f"list error: {e}")
        await update.message.reply_text("❌ Could not fetch your products. Try again later.")
        return

    if not products:
        await update.message.reply_text(
            "📭 You have no tracked products.\nUse /track &lt;url&gt; to start!",
            parse_mode="HTML"
        )
        return

    text = "📋 <b>Your Tracked Products:</b>\n\n"
    keyboard = []
    for p in products:
        site_emoji = {"amazon": "🛒", "flipkart": "🛍️"}.get(p.get("site", ""), "🏪")
        text += (
            f"{site_emoji} <b>{p['title'][:50]}{'...' if len(p['title']) > 50 else ''}</b>\n"
            f"   💰 ₹{p['current_price']:,.0f}  |  🆔 ID: <code>{p['id']}</code>\n\n"
        )
        keyboard.append([
            InlineKeyboardButton(
                f"🗑 Remove #{p['id']} — {p['title'][:25]}",
                callback_data=f"remove_{p['id']}"
            )
        ])

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def remove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Usage: /remove &lt;id&gt;", parse_mode="HTML")
        return
    try:
        product_id = int(context.args[0])
        api_remove(product_id, chat_id)
        await update.message.reply_text(f"✅ Product #{product_id} removed from tracking.")
    except ValueError:
        await update.message.reply_text("❌ Invalid ID. Use /list to see your product IDs.")
    except http_requests.HTTPError:
        await update.message.reply_text("❌ Product not found or doesn't belong to you.")
    except Exception as e:
        logger.error(f"remove error: {e}")
        await update.message.reply_text("❌ Something went wrong. Try again later.")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = str(query.from_user.id)
    data = query.data

    if data.startswith("remove_"):
        product_id = int(data.split("_")[1])
        try:
            api_remove(product_id, chat_id)
            await query.edit_message_text(f"✅ Product #{product_id} removed from tracking.")
        except Exception as e:
            logger.error(f"button remove error: {e}")
            await query.edit_message_text("❌ Could not remove product. Try again.")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("track", track))
    app.add_handler(CommandHandler("list", list_products))
    app.add_handler(CommandHandler("remove", remove_cmd))
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("Bot started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
