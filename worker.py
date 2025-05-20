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

# Load env vars
load_dotenv()

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis connection
redis_conn = get_redis_conn()

def format_timestamp(seconds: float) -> str:
    """Turn a float seconds value into 'HH:MM:SS,mmm'."""
    total_ms = max(0, int(seconds * 1000))
    ms = total_ms % 1000
    s = (total_ms // 1000) % 60
    m = (total_ms // 60000) % 60
    h = total_ms // 3600000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def generate_srt(subs: list[tuple[str, float, tuple]], path: str,
                 default_dur: float = 2.0, min_dur: float = 0.1) -> None:
    """
    Write out an SRT file where each cue starts at subs[i][1]
    and ends just before subs[i+1][1] (minus 0.05s), or default_dur.
    """
    # Sort by timestamp
    subs = sorted(subs, key=lambda x: x[1])
    with open(path, 'w', encoding='utf-8') as f:
        for idx, (text, start_ts, *_ ) in enumerate(subs, start=1):
            # Determine end timestamp
            if idx < len(subs):
                next_ts = subs[idx][1]
                dur = next_ts - start_ts - 0.05
                if dur < min_dur:
                    dur = default_dur
                end_ts = start_ts + dur
            else:
                end_ts = start_ts + default_dur

            # Write cue header
            f.write(f"{idx}\n")
            f.write(f"{format_timestamp(start_ts)} --> {format_timestamp(end_ts)}\n")

            # Clean up the OCR text, preserve line breaks
            for line in text.split("\n"):
                line = line.strip()
                if line:  # skip empty lines
                    f.write(line + "\n")
            f.write("\n")

def extract_frames(video_path: str, interval: float = 1.0):
    """Extract one frame per `interval` seconds using OpenCV only."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    if fps <= 0 or total_frames <= 0:
        raise RuntimeError("Failed to read FPS or frame count from video.")

    duration = total_frames / fps
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
    bot = Bot(token=bot_token)

    # 1) Download the video to local disk
    os.makedirs("downloads", exist_ok=True)
    video_path = os.path.join("downloads", f"{user_id}_{file_id}.mp4")
    tgfile = bot.get_file(file_id)
    tgfile.download(custom_path=video_path)

    try:
        # 2) Extract frames
        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text="📊 10% - Extracting frames…")
        frames = extract_frames(video_path)

        # 3) Detect subtitle regions
        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text="📊 40% - Detecting subtitle regions…")
        regions = extract_subtitle_regions(frames)

        # 4) Perform OCR
        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text="📊 60% - Performing OCR…")
        ocr_texts = perform_ocr_with_preprocessing(regions)

        # 5) **Keep all languages** (your Hindi lines!)
        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text="📊 70% - Filtering languages (keeping all)…")
        subs = filter_english_text(ocr_texts, english_only=False)

        # 6) Generate SRT with dynamic durations
        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text="📊 90% - Generating subtitle file…")
        os.makedirs(SUBTITLE_DIR, exist_ok=True)
        srt_path = os.path.join(SUBTITLE_DIR, f"{user_id}.srt")
        generate_srt(subs, srt_path)

        # 7) Send back to user
        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text="✅ Done! Here are your subtitles.")
        with open(srt_path, "rb") as fp:
            bot.send_document(chat_id=chat_id,
                              document=fp,
                              filename="extracted_subtitles.srt")

    except Exception as e:
        logger.error(f"Error in worker: {e}", exc_info=True)
        bot.send_message(chat_id=chat_id,
                         text=f"❌ Processing error: {e}")

    finally:
        # Cleanup files
        if os.path.exists(video_path):
            os.remove(video_path)
        if 'srt_path' in locals() and os.path.exists(srt_path):
            os.remove(srt_path)

if __name__ == "__main__":
    # Start the RQ worker on the 'subtitle_extraction' queue
    worker = Worker(["subtitle_extraction"], connection=redis_conn)
    worker.work()
