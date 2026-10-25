#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

echo "=========================================================="
echo "🎹 AI-STEAM Studio: Cloud Production Build Starting..."
echo "=========================================================="

# 1. pip & build tools update (avoid cache to minimize memory)
python -m pip install --no-cache-dir --upgrade pip setuptools wheel

# 2. Install dependencies
pip install --no-cache-dir -r requirements.txt

# 3. Ensure lightweight CPU onnxruntime binary (prevent GPU driver mismatch & reduce memory footprint)
pip uninstall -y onnxruntime-gpu || true
pip install --no-cache-dir --force-reinstall --no-deps onnxruntime

# 4. Pre-download deep learning ONNX checkpoints into container
echo "[STEP] Pre-downloading oemer ONNX checkpoints..."
python download_models.py

# 5. Prepare cache directory
mkdir -p omr_cache

echo "=========================================================="
echo "✅ AI-STEAM Studio: Production Build Finished Successfully!"
echo "=========================================================="
