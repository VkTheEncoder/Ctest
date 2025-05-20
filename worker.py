import os
import logging
import cv2
import ffmpeg
import pytesseract
import numpy as np
from telegram import Bot
from rq import Worker, Connection
from utils.queue_manager import get_redis_conn, get_queue, SUBTITLE_DIR
from utils.subtitle_detection import extract_subtitle_regions, group_text_contours
from utils.ocr import perform_ocr_with_preprocessing
from utils.language_filter import filter_english_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

redis_conn = get_redis_conn()
queue = get_queue()
bot = Bot(token=os.getenv('BOT_TOKEN'))

os.makedirs(SUBTITLE_DIR, exist_ok=True)


def format_timestamp(seconds):
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


def extract_frames(video_path, interval=1.0):
    data = ffmpeg.probe(video_path)
    duration = float([s for s in data['streams'] if s['codec_type']=='video'][0]['duration'])
    cap = cv2.VideoCapture(video_path)
    frames = []
    t = 0
    while t < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, t*1000)
        ret, frame = cap.read()
        if not ret: break
        frames.append((frame, t))
        t += interval
    cap.release()
    return frames


def process_video_task(video_path, user_id, chat_id, message_id, bot_token, **kwargs):
    bot = Bot(token=bot_token)

    try:
        # Step 1: extract frames
        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text="📊 10% - Extracting frames...")
        frames = extract_frames(video_path)

        # Step 2: subtitle regions
        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text="📊 40% - Detecting subtitle regions...")
        regions = extract_subtitle_regions(frames)

        # Step 3: OCR
        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text="📊 60% - Performing OCR...")
        texts = perform_ocr_with_preprocessing(regions)

        # Step 4: filter
        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text="📊 80% - Filtering languages...")
        eng = filter_english_text(texts)

        # Step 5: SRT
        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text="📊 90% - Generating SRT...")
        srt_path = os.path.join(SUBTITLE_DIR, f"{user_id}.srt")
        generate_srt(eng, srt_path)

        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text="✅ Done! Sending subtitles...")
        with open(srt_path, 'rb') as f:
            bot.send_document(chat_id=chat_id, document=f,
                              filename="subtitles.srt",
                              caption="Here are your subtitles.")

        os.remove(video_path)
        os.remove(srt_path)

    except Exception as e:
        logger.error(f"Worker error: {e}", exc_info=True)
        bot.send_message(chat_id=chat_id,
                         text=f"❌ Error during processing: {e}")

if __name__ == '__main__':
    with Connection(redis_conn):
        worker = Worker(['subtitle_extraction'])
        worker.work()
