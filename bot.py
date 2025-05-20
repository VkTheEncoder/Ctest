# bot.py
import os
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters
from utils.error_handler import handle_errors
from utils.queue_manager import get_redis_conn, get_queue
from your_handlers_module import start, help_command, handle_video, status_command, cancel_command

# Load environment
from dotenv import load_dotenv
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

# Initialize bot and dispatcher
bot = Bot(token=TOKEN)
dp = Dispatcher(bot, None, use_context=True)

# Register handlers
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("help", help_command))
dp.add_handler(CommandHandler("status", status_command))
dp.add_handler(CommandHandler("cancel", cancel_command))
dp.add_handler(MessageHandler(Filters.video | Filters.document.video, handle_video))

# Flask app
app = Flask(__name__)

@app.route(f"/webhook/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dp.process_update(update)
    return "OK"

if __name__ == "__main__":
    # Set webhook on Telegram’s side
    webhook_url = f"https://ctest-production.up.railway.app/webhook/8096088012:AAEC0AQzB0TDhXZ0IBoXUsZn4k_uQDJSiDM"
    bot.set_webhook(webhook_url)
    # Start Flask
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
