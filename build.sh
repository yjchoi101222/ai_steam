#!/usr/bin/env bash
# exit on error
set -o errexit

echo "=========================================================="
echo "🎹 AI-STEAM Studio: Render Production Build Starting..."
echo "=========================================================="

# 1. pip & 빌드 도구 최신화 (메모리 절약을 위해 --no-cache-dir 권장)
python -m pip install --no-cache-dir --upgrade pip setuptools wheel

# 2. 필수 의존성 설치
pip install --no-cache-dir -r requirements.txt

# 3. Linux CPU 클라우드 환경용 onnxruntime CPU 바이너리 강제 보장 (GPU 패키지 충돌 방지)
pip uninstall -y onnxruntime-gpu || true
pip install --no-cache-dir --force-reinstall --no-deps onnxruntime

# 4. [핵심] oemer ONNX 딥러닝 모델 가중치 사전 다운로드 및 무결성 검증
python download_models.py

# 5. 캐시 디렉터리 준비
mkdir -p omr_cache

echo "=========================================================="
echo "✅ AI-STEAM Studio: Render Production Build Finished!"
echo "=========================================================="
