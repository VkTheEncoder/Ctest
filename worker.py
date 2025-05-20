import os
import logging
import cv2
import pytesseract
import numpy as np
from telegram import Bot
from rq import Worker
from utils.queue_manager import get_redis_conn, SUBTITLE_DIR
from utils.subtitle_detection import extract_subtitle_regions
from utils.ocr import perform_ocr_with_preprocessing
from utils.language_filter import filter_english_text
from dotenv import load_dotenv

# Load env
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

redis_conn = get_redis_conn()

def format_timestamp(seconds: float) -> str:
    ms = int((seconds - int(seconds)) * 1000)
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def generate_srt(subs, path):
    with open(path, 'w', encoding='utf-8') as f:
        for i, (text, ts, *_ ) in enumerate(subs, start=1):
            start = ts
            end = ts + 2.0
            f.write(f"{i}\n")
            f.write(f"{format_timestamp(start)} --> {format_timestamp(end)}\n")
            f.write(f"{text}\n\n")

def extract_frames(video_path: str, interval: float = 1.0):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    if fps <= 0 or frame_count <= 0:
        raise RuntimeError("Failed to read FPS or frame count from video.")

    duration = frame_count / fps
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

def process_video_task(file_id, user_id, chat_id, message_id, bot_token, **kwargs):
    worker_bot = Bot(token=bot_token)

    # 1) Download the video inside the worker
    os.makedirs('downloads', exist_ok=True)
    video_path = os.path.join('downloads', f"{user_id}_{file_id}.mp4")
    tg_file = worker_bot.get_file(file_id)
    tg_file.download(custom_path=video_path)

    try:
        worker_bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                                     text="📊 10% - Extracting frames…")
        frames = extract_frames(video_path)

        worker_bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                                     text="📊 40% - Detecting subtitle regions…")
        regions = extract_subtitle_regions(frames)

        worker_bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                                     text="📊 60% - Performing OCR…")
        texts = perform_ocr_with_preprocessing(regions)

        worker_bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                                     text="📊 80% - Filtering languages…")
        english_subs = filter_english_text(texts)

        worker_bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                                     text="📊 90% - Generating SRT…")
        os.makedirs(SUBTITLE_DIR, exist_ok=True)
        srt_path = os.path.join(SUBTITLE_DIR, f"{user_id}.srt")
        generate_srt(english_subs, srt_path)

        worker_bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                                     text="✅ Processing complete! Sending subtitles…")
        with open(srt_path, 'rb') as f:
            worker_bot.send_document(chat_id=chat_id,
                                     document=f,
                                     filename="subtitles.srt")

    except Exception as e:
        logger.error(f"Worker error: {e}", exc_info=True)
        worker_bot.send_message(chat_id=chat_id,
                                text=f"❌ Error during processing: {e}")

    finally:
        # cleanup
        if os.path.exists(video_path):
            os.remove(video_path)
        if os.path.exists(srt_path):
            os.remove(srt_path)

if __name__ == '__main__':
    # Start the RQ worker
    worker = Worker(['subtitle_extraction'], connection=redis_conn)
    worker.work()
