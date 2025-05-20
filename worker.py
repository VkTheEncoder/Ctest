import os
import logging
import cv2
import pytesseract
import numpy as np
from telegram import Bot
from rq import Worker
from dotenv import load_dotenv
from utils.queue_manager import get_redis_conn, SUBTITLE_DIR

# ── Environment & Logging ─────────────────────────────────────────────────────
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
redis_conn = get_redis_conn()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Tesseract Configuration ───────────────────────────────────────────────────
# Whitelist letters, numbers, and basic punctuation. PSM 7 = treat image as single text line.
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
    """Write cues [(text, start_sec), ...] to SRT with dynamic ends."""
    with open(out_path, "w", encoding="utf-8") as f:
        for i, (text, start) in enumerate(cues, start=1):
            # Determine end time
            if i < len(cues):
                # end a hair before next start
                end = max(start + 0.05, cues[i][1] - 0.05)
            else:
                end = start + 2.0
            f.write(f"{i}\n")
            f.write(f"{format_timestamp(start)} --> {format_timestamp(end)}\n")
            f.write(text + "\n\n")

def ocr_bottom(frame: np.ndarray) -> str:
    """Crop bottom 20%, preprocess, and OCR with whitelist."""
    h, w = frame.shape[:2]
    roi = frame[int(h*0.8):, :]

    # Grayscale
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    # Smooth and preserve edges
    blur = cv2.bilateralFilter(gray, 9, 75, 75)
    # Otsu threshold
    _, th1 = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Ensure black text on white bg
    th = cv2.bitwise_not(th1) if np.mean(th1) > 127 else th1
    # Close small holes in letters
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=2)

    # OCR
    text = pytesseract.image_to_string(th, config=TESSERACT_CONFIG)
    return text.strip()

def extract_frames(video_path: str, interval_s: float = 0.5):
    """Yield (frame, timestamp) every interval_s seconds."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    duration = total / fps if fps > 0 else 0
    t = 0.0
    while t < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, t*1000)
        ret, frame = cap.read()
        if not ret:
            break
        yield frame, t
        t += interval_s
    cap.release()

# ── Main Task ──────────────────────────────────────────────────────────────────
def process_video_task(file_id, user_id, chat_id, message_id, bot_token, **_):
    bot = Bot(token=bot_token)
    os.makedirs("downloads", exist_ok=True)
    os.makedirs(SUBTITLE_DIR, exist_ok=True)
    video_path = os.path.join("downloads", f"{user_id}_{file_id}.mp4")
    srt_path   = os.path.join(SUBTITLE_DIR, f"{user_id}.srt")

    # Download the file
    tgfile = bot.get_file(file_id)
    tgfile.download(custom_path=video_path)

    try:
        # OCR pass
        bot.edit_message_text(chat_id, message_id, "🔄 Extracting subtitles…")
        cues = []
        last = None
        for frame, ts in extract_frames(video_path):
            txt = ocr_bottom(frame)
            if txt and txt != last:
                cues.append((txt, ts))
                last = txt

        # Write SRT
        write_srt(cues, srt_path)

        # Send back
        bot.edit_message_text(chat_id, message_id, "✅ Sending subtitles…")
        with open(srt_path, "rb") as f:
            bot.send_document(chat_id, f, filename="subtitles.srt")

    except Exception as e:
        logger.error("Processing error", exc_info=True)
        bot.send_message(chat_id, f"❌ Error: {e}")
    finally:
        # Clean up
        if os.path.exists(video_path):
            os.remove(video_path)
        if os.path.exists(srt_path):
            os.remove(srt_path)

# ── Worker Entrypoint ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    worker = Worker(["subtitle_extraction"], connection=redis_conn)
    worker.work()
