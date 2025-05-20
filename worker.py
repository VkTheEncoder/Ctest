import os
import cv2
import pytesseract
import numpy as np
from telegram import Bot
from rq import Worker
from rq import Queue
from redis import Redis
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
REDIS_URL = os.getenv('REDIS_URL')
SUBTITLE_DIR = os.getenv('SUBTITLE_DIR', 'subtitles')

# Initialize Redis & RQ
redis_conn = Redis.from_url(REDIS_URL)
queue = Queue('subtitle_extraction', connection=redis_conn)

# Tesseract OCR config: whitelist letters, numbers, basic punctuation
TESSERACT_CONFIG = r"--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,?!"

# Ensure output directory exists
os.makedirs('downloads', exist_ok=True)
os.makedirs(SUBTITLE_DIR, exist_ok=True)


def extract_frames(video_path: str, interval: float = 1.0):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    duration = total_frames / fps if fps > 0 else 0

    frames = []
    t = 0.0
    while t < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ret, frame = cap.read()
        if not ret:
            break
        frames.append((frame, t))
        t += interval

    cap.release()
    return frames


def ocr_bottom(frame: np.ndarray) -> str:
    h, w = frame.shape[:2]
    roi = frame[int(h*0.8):h, 0:w]  # bottom 20%
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    text = pytesseract.image_to_string(th, config=TESSERACT_CONFIG)
    return text.strip()


def format_timestamp(seconds: float) -> str:
    total_ms = max(0, int(seconds * 1000))
    ms = total_ms % 1000
    s = (total_ms // 1000) % 60
    m = (total_ms // 60000) % 60
    h = total_ms // 3600000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def write_srt(cues: list[tuple[str, float]], out_path: str):
    with open(out_path, 'w', encoding='utf-8') as f:
        for i, (txt, start) in enumerate(cues, start=1):
            if i < len(cues):
                end = max(start + 0.05, cues[i][1] - 0.05)
            else:
                end = start + 2.0
            f.write(f"{i}\n")
            f.write(f"{format_timestamp(start)} --> {format_timestamp(end)}\n")
            f.write(txt + "\n\n")


def process_video_task(file_id, user_id, chat_id, message_id, bot_token, **kwargs):
    bot = Bot(token=bot_token)
    # Download video
    video_path = f"downloads/{user_id}_{file_id}.mp4"
    tgfile = bot.get_file(file_id)
    tgfile.download(custom_path=video_path)

    try:
        frames = extract_frames(video_path)
        cues = []
        last = None
        for frame, ts in frames:
            text = ocr_bottom(frame)
            if text and text != last:
                cues.append((text, ts))
                last = text

        srt_path = os.path.join(SUBTITLE_DIR, f"{user_id}.srt")
        write_srt(cues, srt_path)

        bot.send_document(chat_id=chat_id,
                          document=open(srt_path, 'rb'),
                          filename="extracted_subtitles.srt",
                          caption="Here are your subtitles.")
    finally:
        # Cleanup
        if os.path.exists(video_path):
            os.remove(video_path)
        if 'srt_path' in locals() and os.path.exists(srt_path):
            os.remove(srt_path)


if __name__ == '__main__':
    worker = Worker(['subtitle_extraction'], connection=redis_conn)
    worker.work()
