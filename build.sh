#!/usr/bin/env bash
# exit on error
set -o errexit

echo "=========================================================="
echo "🎹 AI-STEAM Studio: Render Production Build Starting..."
echo "=========================================================="

# 1. pip & 빌드 도구 최신화
python -m pip install --upgrade pip setuptools wheel

# 2. 필수 의존성 설치
pip install -r requirements.txt

# 3. Linux CPU 클라우드 환경용 onnxruntime CPU 바이너리 강제 보장
pip install --force-reinstall --no-deps onnxruntime

# 4. 캐시 디렉터리 준비
mkdir -p omr_cache

echo "=========================================================="
echo "✅ AI-STEAM Studio: Render Production Build Finished!"
echo "=========================================================="
