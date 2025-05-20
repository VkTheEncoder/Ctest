import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Updater, CommandHandler, MessageHandler,
    Filters, CallbackContext
)
from utils.error_handler import handle_errors
from utils.queue_manager import get_redis_conn, get_queue

# Load env
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_USER_ID', '0'))
if not TOKEN:
    raise RuntimeError("❌ BOT_TOKEN not set in environment.")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis & queue
redis_conn = get_redis_conn()
video_queue = get_queue()

def start(update: Update, context: CallbackContext):
    update.message.reply_text("👋 Send me a video and I'll extract hardsub subtitles for you.")

def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "/status <jobID> – check progress\n"
        "/cancel <jobID> – cancel processing"
    )

@handle_errors
def handle_video(update: Update, context: CallbackContext):
    video = update.message.video or update.message.document
    if not video:
        return update.message.reply_text("Please send a valid video file.")

    # Ack
    msg = update.message.reply_text("✅ Video received. Queuing for processing…")

    file_id    = video.file_id
    user_id    = update.effective_user.id
    chat_id    = update.effective_chat.id
    message_id = msg.message_id

    # Enqueue job with named kwargs (no video_path)
    job = video_queue.enqueue(
        'worker.process_video_task',
        file_id=file_id,
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
        bot_token=TOKEN,
        job_timeout=3600
    )

    # Store job ID for /status
    redis_conn.set(f"job_id:{user_id}_{file_id}", job.id)

    # Edit ack to show job ID
    msg.edit_text(f"🎫 Job queued: ID `{job.id[:8]}`\nUse `/status {job.id[:8]}` to check.")

def status_command(update: Update, context: CallbackContext):
    # ... your existing implementation ...
    pass

def cancel_command(update: Update, context: CallbackContext):
    # ... your existing implementation ...
    pass

def text_handler(update: Update, context: CallbackContext):
    update.message.reply_text("Send me a video file to extract subtitles.")

def main():
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("status", status_command))
    dp.add_handler(CommandHandler("cancel", cancel_command))
    dp.add_handler(MessageHandler(Filters.video | Filters.document.video, handle_video))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, text_handler))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
