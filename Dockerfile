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

# [핵심 수정] 도커 이미지 빌드 시점에 oemer ONNX 모델 가중치 사전 다운로드
RUN python -c "\
import os, urllib.request, oemer.ete as ete; \
from oemer import MODULE_PATH; \
ete.download_checkponts() if hasattr(ete, 'download_checkponts') else (ete.download_checkpoints() if hasattr(ete, 'download_checkpoints') else None); \
unet_path = os.path.join(MODULE_PATH, 'checkpoints', 'unet_big', 'model.onnx'); \
assert os.path.exists(unet_path), 'ONNX Model download failed!'; \
print('ONNX Models successfully baked into Docker image!')"

# 프로젝트 소스 복사
COPY . .

# 캐시 디렉터리 보장
RUN mkdir -p /app/omr_cache

EXPOSE 10000

# Uvicorn 프로덕션 실행
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
