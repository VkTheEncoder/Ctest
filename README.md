# subtitle-extractor-bot

A Telegram bot that extracts subtitles from videos using OCR and computer vision, with robust error handling, queuing, language filtering, and progress updates.

## Features

- Robust error handling with user-friendly messages and admin alerts  
- Redis-backed RQ queue for processing multiple videos concurrently  
- Advanced subtitle region detection & OCR preprocessing  
- Language filtering (English-only) via fastText/langdetect  
- Progress updates at key steps  
- `/status` and `/cancel` commands for job management  

## Setup

1. Clone this repository  
2. Create & activate a Python virtual environment  
3. Install dependencies: `pip install -r requirements.txt`  
4. Copy `.env.example` to `.env`, fill in your values  
5. Ensure Redis is running (`redis-server`)  
6. Start the worker: `python worker.py`  
7. Start the bot: `python bot.py`  

## Usage

- Send a video (MP4, AVI, MKV) to the bot  
- Bot replies with queue position & job ID  
- Use `/status <jobID>` to check progress  
- Use `/cancel <jobID>` to cancel processing  
