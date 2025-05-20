import os
import logging
import cv2
import pytesseract
import numpy as np
from telegram import Bot
from telegram.error import BadRequest
from rq import Worker
from dotenv import load_dotenv
from utils.queue_manager import get_redis_conn, SUBTITLE_DIR

# ── Init ────────────────────────────────────────────────────────────────────────
load_dotenv()
TOKEN      = os.getenv("BOT_TOKEN")
redis_conn = get_redis_conn()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Helpers ────────────────────────────────────────────────────────────────────
def format_ts(sec: float) -> str:
    ms = int((sec - int(sec)) * 1000)
    h, rem = divmod(int(sec), 3600)
    m, s   = divmod(rem, 60)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def write_srt(cues, path):
    with open(path, "w", encoding="utf-8") as f:
        for i, (txt, start) in enumerate(cues, 1):
            if i < len(cues):
                end = max(start + 0.1, cues[i][1] - 0.05)
            else:
                end = start + 2.0
            f.write(f"{i}\n")
            f.write(f"{format_ts(start)} --> {format_ts(end)}\n")
            f.write(txt + "\n\n")

def safe_edit(bot, chat_id, msg_id, text):
    try:
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text)
    except BadRequest as e:
        logger.warning(f"edit failed: {e}")

def safe_send(bot, chat_id, path):
    try:
        with open(path,"rb") as doc:
            bot.send_document(chat_id, doc, filename="subtitles.srt")
    except BadRequest as e:
        logger.warning(f"send failed: {e}")

def ocr_simple(frame):
    """Crop bottom 25%, threshold, invert if needed, OCR."""
    h, w = frame.shape[:2]
    roi  = frame[int(h*0.75):, :]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    # Adaptive thresholding
    th = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 15, 3
    )
    # If text is white on dark bg, invert
    if np.mean(th) < 127:
        th = cv2.bitwise_not(th)
    # OCR without whitelist
    return pytesseract.image_to_string(th, lang='eng').strip()

def extract_frames(path, interval=0.5):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or (fps*1)
    duration = total / fps
    t = 0.0
    while t < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, t*1000)
        ret, frame = cap.read()
        if not ret:
            break
        yield frame, t
        t += interval
    cap.release()

# ── The RQ Task ────────────────────────────────────────────────────────────────
def process_video_task(file_id, user_id, chat_id, message_id, bot_token, **_):
    bot = Bot(token=bot_token)
    os.makedirs("downloads", exist_ok=True)
    os.makedirs(SUBTITLE_DIR, exist_ok=True)
    vp = f"downloads/{user_id}_{file_id}.mp4"
    sp = f"{SUBTITLE_DIR}/{user_id}.srt"

    # Download the video
    tg = bot.get_file(file_id)
    tg.download(custom_path=vp)

    try:
        safe_edit(bot, chat_id, message_id, "⏳ Extracting subtitles…")
        cues, last = [], None
        for frame, ts in extract_frames(vp):
            text = ocr_simple(frame)
            if text and text != last:
                cues.append((text, ts))
                last = text

        write_srt(cues, sp)

        safe_edit(bot, chat_id, message_id, "✅ Sending subtitles…")
        safe_send(bot, chat_id, sp)

    except Exception as e:
        logger.error("Error in processing", exc_info=True)
        try:
            bot.send_message(chat_id, f"❌ Error: {e}")
        except:
            pass
    finally:
        if os.path.exists(vp): os.remove(vp)
        if os.path.exists(sp): os.remove(sp)

if __name__ == "__main__":
    Worker(["subtitle_extraction"], connection=redis_conn).work()
