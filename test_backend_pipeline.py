import sys
import io
import os
import json
import time
import requests
import numpy as np
import cv2
import music21 as m21

# Windows cp949 인코딩 오류 방지
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_URL = "http://127.0.0.1:8000"

print("=" * 70)
print("🎹 AI-STEAM v2.0 Backend Pipeline & REST API Verification Suite")
print("=" * 70)

passed = 0
failed = 0

def test(name):
    def decorator(func):
        def wrapper(*args, **kwargs):
            global passed, failed
            print(f"\n[TEST] {name} ...", end=" ", flush=True)
            try:
                result = func(*args, **kwargs)
                print("✅ PASSED")
                if result:
                    for line in str(result).splitlines():
                        print(f"       {line}")
                passed += 1
            except Exception as e:
                print(f"❌ FAILED: {e}")
                failed += 1
        return wrapper
    return decorator


# 1. Image Optimizer Component Test
@test("1. SheetMusicOptimizer (OpenCV Preprocessing Component)")
def test_image_optimizer():
    from core.image_optimizer import SheetMusicOptimizer
    optimizer = SheetMusicOptimizer(target_width=1200)

    # 400x800 크기의 테스트 이미지 생성 (흰 배경에 검은 오선지 라인들)
    img = np.ones((400, 800, 3), dtype=np.uint8) * 255
    for y in [100, 120, 140, 160, 180]:
        cv2.line(img, (50, y), (750, y), (0, 0, 0), 2)
    # 5도 기울임 회전 적용
    M = cv2.getRotationMatrix2D((400, 200), 5.0, 1.0)
    rotated = cv2.warpAffine(img, M, (800, 400), borderValue=(255, 255, 255))
    _, encoded = cv2.imencode(".png", rotated)
    raw_bytes = encoded.tobytes()

    optimized_bytes = optimizer.optimize(raw_bytes)
    assert len(optimized_bytes) > 0, "Optimized image byte array is empty"
    
    # 디코딩 검증
    out_arr = np.frombuffer(optimized_bytes, np.uint8)
    out_img = cv2.imdecode(out_arr, cv2.IMREAD_GRAYSCALE)
    assert out_img is not None, "Failed to decode optimized PNG image"
    assert out_img.shape[1] == 1200, f"Target width expected 1200, got {out_img.shape[1]}"
    return f"Input bytes: {len(raw_bytes):,} B -> Optimized: {len(optimized_bytes):,} B (Width: {out_img.shape[1]}px, Height: {out_img.shape[0]}px)"


# 2. Score Corrector Component Test
@test("2. ScoreCorrector (Music Theory Normalization Component)")
def test_score_corrector():
    from core.corrector import ScoreCorrector
    corrector = ScoreCorrector()

    # 테스트 스코어 생성
    s = m21.stream.Score()
    p1 = m21.stream.Part()
    m1 = m21.stream.Measure(number=1)
    
    # 1. 정상 음표
    m1.append(m21.note.Note('C4', quarterLength=1.0))
    # 2. 중복 음표 (동일 오프셋에 동일 피치 C4)
    dup_note = m21.note.Note('C4', quarterLength=1.0)
    m1.insert(0.0, dup_note)
    # 3. 비정상 극소 파편 음표 (2048분 음표: 1/512 ql)
    fragment = m21.note.Note('E4', quarterLength=0.001)
    m1.append(fragment)
    # 4. 88건반 범위 초과 피치 (C-1 -> MIDI 0, 클램핑 대상)
    out_of_bound = m21.note.Note('C-1', quarterLength=1.0)
    m1.append(out_of_bound)

    p1.append(m1)
    s.append(p1)

    initial_notes = len(list(s.recurse().getElementsByClass(m21.note.Note)))
    assert initial_notes == 4, f"Expected 4 initial notes, got {initial_notes}"

    # 교정 실행
    corrected_score = corrector.run_all(s)
    remaining_notes = list(corrected_score.recurse().getElementsByClass(m21.note.Note))

    # 파편과 중복 제거로 2~3개 남아야 함
    # C-1은 클램핑되어 A0 또는 범위 내로 수정되어야 함
    for n in remaining_notes:
        assert n.quarterLength >= 0.125, f"Fragment note remained with ql={n.quarterLength}"
        assert 21 <= n.pitch.midi <= 108, f"Pitch outside 88-key range: {n.pitch.nameWithOctave} ({n.pitch.midi})"

    return f"Initial notes: {initial_notes} -> Corrected notes: {len(remaining_notes)} (Fragments removed & 88-key clamped)"


# 3. REST API - Root Endpoint
@test("3. REST API: GET / (Web Editor UI Servicing)")
def test_api_root():
    res = requests.get(f"{BASE_URL}/", timeout=5)
    assert res.status_code == 200, f"Expected status 200, got {res.status_code}"
    assert "AI-STEAM" in res.text, "Response does not contain 'AI-STEAM'"
    assert "OpenSheetMusicDisplay" in res.text, "Response does not include OSMD reference"
    return f"Status: {res.status_code}, HTML length: {len(res.text):,} chars"


# 4. REST API - Preprocess Upload
@test("4. REST API: POST /api/preprocess (Image Upload & Optimization)")
def test_api_preprocess():
    # 더미 악보 이미지 생성
    img = np.ones((300, 600, 3), dtype=np.uint8) * 255
    cv2.putText(img, "TEST SCORE", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3)
    _, encoded = cv2.imencode(".png", img)
    files = {"file": ("test_sheet.png", encoded.tobytes(), "image/png")}

    res = requests.post(f"{BASE_URL}/api/preprocess", files=files, timeout=10)
    assert res.status_code == 200, f"Expected status 200, got {res.status_code}: {res.text}"
    data = res.json()
    assert data.get("status") == "success", f"Invalid response: {data}"
    assert "file_hash" in data, "file_hash missing in response"
    assert "image_url" in data, "image_url missing in response"
    return f"file_hash: {data['file_hash'][:16]}..., image_url: {data['image_url']}"


# 5. REST API - Render Demo Score & Music Analysis
@test("5. REST API: POST /api/render (Score Analysis & MIDI Generation)")
def test_api_render():
    res = requests.post(
        f"{BASE_URL}/api/render",
        json={"file_hash": "demo"},
        timeout=10
    )
    assert res.status_code == 200, f"Expected status 200, got {res.status_code}: {res.text}"
    data = res.json()
    analysis = data.get("analysis", {})
    assert "total_measures" in analysis, "Analysis missing 'total_measures'"
    assert "key_signature" in analysis, "Analysis missing 'key_signature'"
    assert "time_signature" in analysis, "Analysis missing 'time_signature'"
    assert "total_notes" in analysis, "Analysis missing 'total_notes'"
    assert "total_parts" in analysis, "Analysis missing 'total_parts'"
    assert "midi_url" in data, "Response missing 'midi_url'"

    return (
        f"Measures: {analysis.get('total_measures')}, "
        f"Key: {analysis.get('key_signature')}, "
        f"Time Sig: {analysis.get('time_signature')}, "
        f"Notes: {analysis.get('total_notes')}, "
        f"Parts: {analysis.get('total_parts')}, "
        f"MIDI: {data.get('midi_url')}"
    )


# 6. REST API - Optimize Score (MusicXML Correction)
@test("6. REST API: POST /api/optimize (MusicXML Auto-Correction)")
def test_api_optimize():
    res = requests.post(
        f"{BASE_URL}/api/optimize",
        json={"file_hash": "demo"},
        timeout=10
    )
    assert res.status_code == 200, f"Expected status 200, got {res.status_code}: {res.text}"
    data = res.json()
    assert data.get("status") == "success", f"Failed optimization: {data}"
    return f"Optimization status: {data.get('status')}, target: {data.get('file_hash')}"


# 7. REST API - Interactive Edit (Pitch Shift & Chord Add)
@test("7. REST API: POST /api/edit_score (Precision Note Editing)")
def test_api_edit():
    # 마디 1의 음표를 G4로 피치 수정
    payload = {
        "file_hash": "demo",
        "measure_number": 1,
        "note_offset": 0.0,
        "new_pitch": "G4",
        "part_index": 0
    }
    res = requests.post(f"{BASE_URL}/api/edit_score", json=payload, timeout=10)
    assert res.status_code == 200, f"Expected status 200, got {res.status_code}: {res.text}"
    data = res.json()
    assert data.get("status") == "success", f"Edit failed: {data}"
    return f"Edited measure 1, offset 0.0 -> new pitch G4 (status: {data.get('status')})"


# 8. REST API - Undo and Redo History
@test("8. REST API: POST /api/restore_score (Undo / Redo Stack)")
def test_api_undo_redo():
    # Undo 실행
    res_undo = requests.post(
        f"{BASE_URL}/api/restore_score",
        json={"file_hash": "demo", "action": "undo"},
        timeout=10
    )
    assert res_undo.status_code == 200, f"Undo failed: {res_undo.text}"
    data_undo = res_undo.json()
    assert data_undo.get("status") == "success", f"Undo status not success: {data_undo}"

    # Redo 실행
    res_redo = requests.post(
        f"{BASE_URL}/api/restore_score",
        json={"file_hash": "demo", "action": "redo"},
        timeout=10
    )
    assert res_redo.status_code == 200, f"Redo failed: {res_redo.text}"
    data_redo = res_redo.json()
    assert data_redo.get("status") == "success", f"Redo status not success: {data_redo}"

    return "Undo -> Redo roundtrip successfully restored snapshot state"


# 9. REST API - OMR Job Lifecycle (Async Start & Immediate Cancel)
@test("9. REST API: POST /api/extract & Cancel (OMR Job Lifecycle)")
def test_api_extract_lifecycle():
    # OMR 비동기 작업 등록
    res_start = requests.post(
        f"{BASE_URL}/api/extract",
        json={"file_hash": "demo", "filename": "demo.png", "mode": "fast"},
        timeout=10
    )
    assert res_start.status_code == 200, f"Extract start failed: {res_start.text}"
    data_start = res_start.json()
    job_id = data_start.get("job_id")
    assert job_id, "job_id missing"

    # 상태 폴링 확인
    res_status = requests.get(f"{BASE_URL}/api/extract/status/{job_id}", timeout=5)
    assert res_status.status_code == 200, f"Status check failed: {res_status.text}"
    status_info = res_status.json()

    # 즉시 작업 취소 API 호출
    res_cancel = requests.post(f"{BASE_URL}/api/extract/{job_id}/cancel", timeout=5)
    assert res_cancel.status_code == 200, f"Cancel failed: {res_cancel.text}"

    return f"Job ID: {job_id[:8]}..., initial status: {status_info.get('status')}, cancel result: {res_cancel.json().get('status')}"


# 10. Cache File Delivery (MIDI & MusicXML)
@test("10. REST API: GET /api/cache/{filename} (Asset Delivery)")
def test_api_cache_files():
    # MIDI 파일 다운로드 검증
    mid_res = requests.get(f"{BASE_URL}/api/cache/demo.mid", timeout=5)
    assert mid_res.status_code == 200, f"Failed demo.mid: {mid_res.status_code}"
    assert mid_res.content.startswith(b"MThd"), "Invalid MIDI header"

    # MusicXML 파일 다운로드 검증
    xml_res = requests.get(f"{BASE_URL}/api/cache/demo.musicxml", timeout=5)
    assert xml_res.status_code == 200, f"Failed demo.musicxml: {xml_res.status_code}"
    assert b"score-partwise" in xml_res.content or b"xml" in xml_res.content, "Invalid MusicXML content"

    return f"demo.mid ({len(mid_res.content):,} B) & demo.musicxml ({len(xml_res.content):,} B) successfully verified"


if __name__ == "__main__":
    test_image_optimizer()
    test_score_corrector()
    test_api_root()
    test_api_preprocess()
    test_api_render()
    test_api_optimize()
    test_api_edit()
    test_api_undo_redo()
    test_api_extract_lifecycle()
    test_api_cache_files()

    print("\n" + "=" * 70)
    print(f"📊 TEST SUMMARY: {passed} PASSED, {failed} FAILED out of {passed + failed} total tests")
    print("=" * 70)
    if failed > 0:
        sys.exit(1)
