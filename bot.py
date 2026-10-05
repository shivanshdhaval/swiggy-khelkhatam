import os
import asyncio
import aiohttp.web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ── RENDER HEALTHCHECK SERVER (PORT BINDING) ─────────────────────────────────
async def health_check(request):
    return aiohttp.web.Response(text="Bot is ALIVE and RUNNING 24/7 (Offer Closed)")

async def start_web_server():
    app = aiohttp.web.Application()
    app.router.add_get('/', health_check)
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get('PORT', 8080))
    site = aiohttp.web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌐 HTTP Port {port} successfully bound for Render.")

# ── BOT CONFIG ───────────────────────────────────────────────────────────────
BOT_TOKEN = "8918993850:AAG-svWDI3GFH1b0cDuozIH-UHlvvgj1QWY"

# ── TELEGRAM HANDLERS ────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "✦ *SWIGGY TURBO LOOT* ✦\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "⚠️ *Update:* The Swiggy Free Cash campaign has officially ended. The API slots are closed and the offer is no longer active.\n\n"
        "Thank you for using the bot!"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "⚠️ The Swiggy Free Cash offer has ended. This bot is currently inactive."
    await update.message.reply_text(msg)

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⚠️ Offer has ended.", show_alert=True)
    await query.message.reply_text("⚠️ The Swiggy Free Cash offer has ended. This bot is currently inactive.")

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Handlers for all interactions
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_messages))

    loop.create_task(start_web_server())
    print("🤖 Swiggy Loot Bot (Closed Status) is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
