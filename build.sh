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

# 4. [핵심 수정] oemer ONNX 딥러닝 모델 가중치 사전 다운로드 및 검증
echo "📥 Pre-downloading oemer ONNX model checkpoints (unet_big, seg_net)..."
python -c "
import os
import urllib.request
import oemer.ete as ete
from oemer import MODULE_PATH

# oemer 내장 다운로드 함수 호출 시도
if hasattr(ete, 'download_checkponts'):
    print('Running ete.download_checkponts()...')
    ete.download_checkponts()
elif hasattr(ete, 'download_checkpoints'):
    print('Running ete.download_checkpoints()...')
    ete.download_checkpoints()
else:
    # 함수명이 변경되었을 경우를 대비한 직접 다운로드 폴백(Fallback) 로직
    print('Direct downloading checkpoints from GitHub Releases...')
    Release_URL = 'https://github.com/BreezeWhite/oemer/releases/download/checkpoints/'
    checkpoints = {
        'unet_big/model.onnx': '1st_model.onnx',
        'unet_big/metadata.pkl': '1st_weights.pkl',
        'seg_net/model.onnx': '2nd_model.onnx',
        'seg_net/metadata.pkl': '2nd_weights.pkl'
    }
    for local_rel_path, remote_file in checkpoints.items():
        target_path = os.path.join(MODULE_PATH, 'checkpoints', local_rel_path)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        if not os.path.exists(target_path):
            print(f'Downloading {remote_file} -> {target_path}...')
            urllib.request.urlretrieve(Release_URL + remote_file, target_path)

# 최종 파일 존재 여부 엄격 검증 (없으면 빌드 실패 처리하여 배포 중단)
unet_path = os.path.join(MODULE_PATH, 'checkpoints', 'unet_big', 'model.onnx')
seg_path = os.path.join(MODULE_PATH, 'checkpoints', 'seg_net', 'model.onnx')
assert os.path.exists(unet_path) and os.path.getsize(unet_path) > 1000000, f'Failed to verify {unet_path}'
assert os.path.exists(seg_path) and os.path.getsize(seg_path) > 1000000, f'Failed to verify {seg_path}'
print('✅ Successfully verified all ONNX models in:', os.path.join(MODULE_PATH, 'checkpoints'))
"

# 5. 캐시 디렉터리 준비
mkdir -p omr_cache

echo "=========================================================="
echo "✅ AI-STEAM Studio: Render Production Build Finished!"
echo "=========================================================="
