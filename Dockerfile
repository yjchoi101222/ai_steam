# AI-STEAM Interactive Sheet Music Studio
# Production Multi-Platform Dockerfile (Render, HuggingFace, Fly.io, Railway)

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=10000

# 시스템 패키지 설치 (headless OpenCV, PyMuPDF, Audio 등 호환)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# pip 최신화 및 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --force-reinstall --no-deps onnxruntime

# 프로젝트 소스 복사
COPY . .

# 캐시 디렉터리 보장
RUN mkdir -p /app/omr_cache

EXPOSE 10000

# Uvicorn 프로덕션 실행
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
