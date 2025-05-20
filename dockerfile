# 1) Base image
FROM python:3.12-slim

# 2) Install system dependencies for OCR, video, and OpenCV headless
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      tesseract-ocr \
      ffmpeg \
      libgl1-mesa-glx && \
    rm -rf /var/lib/apt/lists/*

# 3) Set your working directory
WORKDIR /app

# 4) Copy & install Python requirements
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# 5) Copy the rest of your code
COPY . .

# 6) When the container launches, start BOTH processes in parallel
#    (use "&" so the shell background‐launches them both)
CMD ["bash", "-lc", "python bot.py & python worker.py"]
