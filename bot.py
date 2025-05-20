import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Updater, CommandHandler, MessageHandler,
    Filters, CallbackContext, CallbackQueryHandler
)
from utils.error_handler import handle_errors
from utils.queue_manager import (
    get_redis_conn, get_queue, DOWNLOAD_DIR
)

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_USER_ID', '0'))
redis_conn = get_redis_conn()
video_queue = get_queue()

# Ensure download directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Basic commands

def start(update: Update, context: CallbackContext):
    update.message.reply_text("Hi! Send me a video and I'll extract subtitles for you.")


def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "/status <jobID> - check job status\n"
        "/cancel <jobID> - cancel job"
    )

# Status command
def status_command(update: Update, context: CallbackContext):
    # ... (as in detailed implementation above)
    pass

# Cancel command
def cancel_command(update: Update, context: CallbackContext):
    # ... (as in detailed implementation above)
    pass

# Placeholder for settings & callbacks

def settings_command(update: Update, context: CallbackContext):
    update.message.reply_text("Settings are not yet implemented.")


def button_callback(update: Update, context: CallbackContext):
    pass


def text_handler(update: Update, context: CallbackContext):
    update.message.reply_text("Send me a video file to extract subtitles.")

# Video handler with error handling
@handle_errors
def handle_video(update: Update, context: CallbackContext) -> None:
    video = update.message.video or update.message.document
    if not video:
        update.message.reply_text("Please send a valid video file.")
        return

    msg = update.message.reply_text("Downloading and queueing your video...")
    file = context.bot.get_file(video.file_id)
    user_id = update.effective_user.id
    filename = f"{user_id}_{video.file_id}.mp4"
    path = os.path.join(DOWNLOAD_DIR, filename)
    file.download(path)

    job = video_queue.enqueue(
        'worker.process_video_task',
        video_path=path,
        user_id=user_id,
        chat_id=update.effective_chat.id,
        message_id=msg.message_id,
        bot_token=TOKEN,
        job_timeout=3600
    )

    # Store job ID
    redis_conn.set(f"job_id:{user_id}_{video.file_id}", job.id)

    update.message.reply_text(
        f"Your job is queued (ID: {str(job.id)[:8]})"
    )


def main():
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("status", status_command))
    dp.add_handler(CommandHandler("cancel", cancel_command))
    dp.add_handler(CommandHandler("settings", settings_command))
    dp.add_handler(CallbackQueryHandler(button_callback))
    dp.add_handler(MessageHandler(Filters.video | Filters.document.video, handle_video))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, text_handler))
    dp.add_error_handler(lambda u, c: logger.error("Global error", exc_info=True))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
