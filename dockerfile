# 1. Base image
FROM python:3.12-slim

# 2. Install system dependencies for OCR, video, and OpenCV
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      tesseract-ocr \
      ffmpeg \
      libgl1-mesa-glx && \
    rm -rf /var/lib/apt/lists

# 3. Set working directory
WORKDIR /app

# 4. Copy & install Python requirements
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# 5. Copy application source
COPY . .

# 6. Expose port if you’re using webhooks (optional)
# EXPOSE 8080

# 7. Default command: start both bot and worker
#    They’ll run in parallel inside one container.
CMD ["bash", "-lc", "python bot.py & python worker.py"]
