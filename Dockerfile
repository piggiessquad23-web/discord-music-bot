FROM python:3.11-slim

# System tools, FFmpeg, opus audio library leh Node.js (YouTube JS token atan) dah vek rawh
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus-dev \
    nodejs \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies install hmasakna
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# File dang zawng zawng (bot.py, cookies.txt, etc.) copy rawh
COPY . .

# Bot run-na
CMD ["python", "bot.py"]
