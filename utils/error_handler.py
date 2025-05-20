import traceback
import logging
from functools import wraps
from telegram import Update
from telegram.ext import CallbackContext
from dotenv import load_dotenv
import os

load_dotenv()
ADMIN_ID = int(os.getenv('ADMIN_USER_ID', '0'))
logger = logging.getLogger(__name__)


def handle_errors(func):
    @wraps(func)
    def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        try:
            return func(update, context, *args, **kwargs)
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Error in {func.__name__}: {e}\n{tb}")
            msg = "Sorry, something went wrong."
            if update.effective_message:
                update.effective_message.reply_text(msg)
            if 'critical' in str(e).lower():
                context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"Critical error: {e}\nUser: {update.effective_user.id}"
                )
    return wrapper
