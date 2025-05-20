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

# ── Load env & init logging ────────────────────────────────────────────────────
load_dotenv()
TOKEN     = os.getenv("BOT_TOKEN")
redis_conn = get_redis_conn()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Tesseract config ──────────────────────────────────────────────────────────
TESSERACT_CONFIG = (
    "--oem 3 --psm 7 "
    "-c tessedit_char_whitelist="
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789"
    "?!.,:;() "
)

# ── Helpers ────────────────────────────────────────────────────────────────────
def format_timestamp(sec: float) -> str:
    total_ms = int(round(sec * 1000))
    ms = total_ms % 1000
    s = (total_ms // 1000) % 60
    m = (total_ms // 60000) % 60
    h = total_ms // 3600000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def write_srt(cues: list[tuple[str, float]], out_path: str) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        for i, (text, start) in enumerate(cues, start=1):
            if i < len(cues):
                end = max(start + 0.05, cues[i][1] - 0.05)
            else:
                end = start + 2.0
            f.write(f"{i}\n")
            f.write(f"{format_timestamp(start)} --> {format_timestamp(end)}\n")
            f.write(text + "\n\n")

def safe_edit(bot: Bot, chat_id: int, message_id: int, text: str):
    try:
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
    except BadRequest as e:
        logger.warning(f"[safe_edit] could not edit message {message_id} in chat {chat_id}: {e}")

def safe_send_document(bot: Bot, chat_id: int, path: str, filename: str = "subtitles.srt"):
    try:
        with open(path, "rb") as f:
            bot.send_document(chat_id=chat_id, document=f, filename=filename)
    except BadRequest as e:
        logger.warning(f"[safe_send_document] could not send document to chat {chat_id}: {e}")

def ocr_bottom(frame: np.ndarray) -> str:
    h, w = frame.shape[:2]
    roi = frame[int(h*0.8):, :]

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blur = cv2.bilateralFilter(gray, 9, 75, 75)
    _, th1 = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.bitwise_not(th1) if np.mean(th1) > 127 else th1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=2)

    return pytesseract.image_to_string(th, config=TESSERACT_CONFIG).strip()

def extract_frames(video_path: str, interval_s: float = 0.5):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    duration = total / fps if fps > 0 else 0
    t = 0.0
    while t < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ret, frame = cap.read()
        if not ret:
            break
        yield frame, t
        t += interval_s
    cap.release()

# ── Main processing task ───────────────────────────────────────────────────────
def process_video_task(file_id, user_id, chat_id, message_id, bot_token, **_):
    bot = Bot(token=bot_token)
    os.makedirs("downloads", exist_ok=True)
    os.makedirs(SUBTITLE_DIR, exist_ok=True)
    video_path = os.path.join("downloads", f"{user_id}_{file_id}.mp4")
    srt_path   = os.path.join(SUBTITLE_DIR, f"{user_id}.srt")

    # Download video
    tgfile = bot.get_file(file_id)
    tgfile.download(custom_path=video_path)

    try:
        safe_edit(bot, chat_id, message_id, "🔄 Extracting subtitles…")
        cues = []
        last = None
        for frame, ts in extract_frames(video_path):
            txt = ocr_bottom(frame)
            if txt and txt != last:
                cues.append((txt, ts))
                last = txt

        write_srt(cues, srt_path)

        safe_edit(bot, chat_id, message_id, "✅ Sending subtitles…")
        safe_send_document(bot, chat_id, srt_path)

    except Exception as e:
        logger.error("Processing error", exc_info=True)
        try:
            bot.send_message(chat_id, f"❌ Error: {e}")
        except BadRequest:
            logger.warning(f"Could not send error message to chat {chat_id}")
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)
        if os.path.exists(srt_path):
            os.remove(srt_path)

# ── Worker entrypoint ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    worker = Worker(["subtitle_extraction"], connection=redis_conn)
    worker.work()
