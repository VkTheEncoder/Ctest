# 1) Base image
FROM python:3.12-slim

# 2) Install system dependencies:
#    - tesseract-ocr for pytesseract OCR
#    - ffmpeg for any ffmpeg-python calls (if used)
#    - libgl1-mesa-glx for OpenCV headless support
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      tesseract-ocr \
      ffmpeg \
      libgl1-mesa-glx && \
    rm -rf /var/lib/apt/lists/*

# 3) Set working directory
WORKDIR /app

# 4) Copy & install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# 5) Copy application source
COPY . .

# 6) Ensure .env is loaded by python-dotenv (for local dev you can COPY .env here)
# ENV PYTHONUNBUFFERED=1

# 7) Start both the bot and the worker when the container launches
CMD ["bash", "-lc", "python bot.py & python worker.py"]
