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

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis connection
redis_conn = get_redis_conn()

# Telegram Bot client for worker callbacks
bot = Bot(token=os.getenv('BOT_TOKEN'))

# Ensure output directory exists
os.makedirs(SUBTITLE_DIR, exist_ok=True)


def format_timestamp(seconds: float) -> str:
    ms = int((seconds - int(seconds)) * 1000)
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def generate_srt(subtitles: list[tuple[str, float, tuple]], path: str) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        for i, (text, ts, *_ ) in enumerate(subtitles, start=1):
            start = ts
            end = ts + 2.0
            f.write(f"{i}\n")
            f.write(f"{format_timestamp(start)} --> {format_timestamp(end)}\n")
            f.write(f"{text}\n\n")


def extract_frames(video_path: str, interval: float = 1.0) -> list[tuple[np.ndarray, float]]:
    """
    Open the video with OpenCV, read its FPS & total frames,
    compute duration, and then grab one frame every `interval` seconds.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    if fps <= 0 or frame_count <= 0:
        raise RuntimeError("Failed to read FPS or frame count from video.")

    duration = frame_count / fps
    frames: list[tuple[np.ndarray, float]] = []
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


def process_video_task(video_path, user_id, chat_id, message_id, bot_token, **kwargs):
    worker_bot = Bot(token=bot_token)
    try:
        # 10%: start extracting frames
        worker_bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="📊 10% - Extracting frames..."
        )
        frames = extract_frames(video_path)

        # 40%: detect subtitle regions
        worker_bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="📊 40% - Detecting subtitle regions..."
        )
        regions = extract_subtitle_regions(frames)

        # 60%: perform OCR
        worker_bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="📊 60% - Performing OCR..."
        )
        texts = perform_ocr_with_preprocessing(regions)

        # 80%: filter languages
        worker_bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="📊 80% - Filtering languages..."
        )
        english_subs = filter_english_text(texts)

        # 90%: generate SRT
        worker_bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="📊 90% - Generating SRT..."
        )
        srt_path = os.path.join(SUBTITLE_DIR, f"{user_id}.srt")
        generate_srt(english_subs, srt_path)

        # 100%: send back to user
        worker_bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="✅ Processing complete! Sending subtitles..."
        )
        with open(srt_path, 'rb') as f:
            worker_bot.send_document(
                chat_id=chat_id,
                document=f,
                filename="subtitles.srt",
                caption="Here are your extracted subtitles!"
            )

        # Cleanup
        os.remove(video_path)
        os.remove(srt_path)

    except Exception as e:
        logger.error(f"Worker error: {e}", exc_info=True)
        worker_bot.send_message(
            chat_id=chat_id,
            text=f"❌ Error during processing: {e}"
        )


if __name__ == '__main__':
    # Start the RQ worker listening on the 'subtitle_extraction' queue
    worker = Worker(['subtitle_extraction'], connection=redis_conn)
    worker.work()
