import os
import redis
from rq import Queue
from dotenv import load_dotenv

load_dotenv()
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
redis_conn = redis.Redis.from_url(redis_url)
video_queue = Queue('subtitle_extraction', connection=redis_conn)
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads')
SUBTITLE_DIR = os.getenv('SUBTITLE_DIR', 'subtitles')


def get_redis_conn():
    return redis_conn


def get_queue():
    return video_queue
