import os
import logging
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext
from dotenv import load_dotenv
from utils.error_handler import handle_errors
from utils.queue_manager import get_redis_conn, get_queue

# ── LoadEnv & Logging ─────────────────────────────────────────────────────────
load_dotenv()
TOKEN       = os.getenv("BOT_TOKEN")
ADMIN_ID    = int(os.getenv("ADMIN_USER_ID", "0"))
REDIS_URL   = os.getenv("REDIS_URL")

if not TOKEN or not REDIS_URL:
    raise RuntimeError("BOT_TOKEN and REDIS_URL must be set in environment")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Telegram Bot & Dispatcher ─────────────────────────────────────────────────
bot = Bot(token=TOKEN)
dp  = Dispatcher(bot, None, use_context=True)

# Redis queue
redis_conn  = get_redis_conn()
video_queue = get_queue()

# ── Command & Message Handlers ────────────────────────────────────────────────
def start(update: Update, context: CallbackContext):
    update.message.reply_text("👋 Send me a video and I'll extract hardsub subtitles for you.")

def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Commands:\n"
        "/start – show welcome\n"
        "/help  – show this message\n"
        "/status <jobID> – check status\n"
        "/cancel <jobID> – cancel processing"
    )

@handle_errors
def handle_video(update: Update, context: CallbackContext):
    video = update.message.video or update.message.document
    if not video:
        return update.message.reply_text("Please send a video file.")

    # Acknowledge receipt
    msg = update.message.reply_text("✅ Received. Queuing for processing…")

    file_id    = video.file_id
    user_id    = update.effective_user.id
    chat_id    = update.effective_chat.id
    message_id = msg.message_id

    # Enqueue job
    job = video_queue.enqueue(
        "worker.process_video_task",
        file_id=file_id,
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
        bot_token=TOKEN,
        job_timeout=3600
    )

    # Store for /status
    redis_conn.set(f"job_id:{user_id}_{file_id}", job.id)

    # Edit acknowledgment to include job ID
    msg.edit_text(f"🎫 Job queued: `{job.id[:8]}`\nUse `/status {job.id[:8]}` to check.")

def status_command(update: Update, context: CallbackContext):
    args = context.args
    if not args:
        return update.message.reply_text("Usage: /status <jobID>")
    prefix = args[0]
    user_id = update.effective_user.id

    keys = redis_conn.keys(f"job_id:{user_id}_*")
    matches = []
    for key in keys:
        full = redis_conn.get(key).decode()
        if full.startswith(prefix):
            matches.append(full)

    if not matches:
        return update.message.reply_text(f"No jobs found starting with `{prefix}`.")

    texts = []
    from rq.job import Job
    from utils.queue_manager import redis_conn as rq_conn
    for jid in matches:
        job = Job.fetch(jid, connection=rq_conn)
        st = job.get_status().upper()
        texts.append(f"ID `{jid[:8]}` → {st}")

    update.message.reply_text("\n".join(texts))

def cancel_command(update: Update, context: CallbackContext):
    args = context.args
    if not args:
        return update.message.reply_text("Usage: /cancel <jobID>")
    prefix = args[0]
    user_id = update.effective_user.id

    from rq.job import Job
    from utils.queue_manager import redis_conn as rq_conn

    keys = redis_conn.keys(f"job_id:{user_id}_*")
    cancelled = False
    for key in keys:
        full = redis_conn.get(key).decode()
        if full.startswith(prefix):
            job = Job.fetch(full, connection=rq_conn)
            if job.get_status() in ("finished", "failed"):
                update.message.reply_text(f"Job `{prefix}` already completed.")
            else:
                job.cancel()
                cancelled = True
                update.message.reply_text(f"Job `{prefix}` has been cancelled.")
    if not cancelled:
        update.message.reply_text(f"No active job found with ID `{prefix}`.")

# Register handlers
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("help", help_command))
dp.add_handler(CommandHandler("status", status_command))
dp.add_handler(CommandHandler("cancel", cancel_command))
dp.add_handler(MessageHandler(Filters.video | Filters.document.video, handle_video))

# ── Flask Webhook App ─────────────────────────────────────────────────────────
app = Flask(__name__)

@app.route(f"/webhook/{TOKEN}", methods=["POST"])
def webhook_handler():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot)
    dp.process_update(update)
    return "OK"

# ── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Register webhook with Telegram
    webhook_url = f"https://ctest-production.up.railway.app/webhook/8096088012:AAEC0AQzB0TDhXZ0IBoXUsZn4k_uQDJSiDM"
    bot.set_webhook(webhook_url)
    logger.info(f"Webhook set to {webhook_url}")

    # Start Flask server
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
