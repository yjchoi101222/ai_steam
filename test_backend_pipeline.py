import sys
import io
import os
import json
import time
import threading
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

# 테스트용 로컬 서버 자동 기동 (미실행 시 백그라운드 스레드로 실행)
def ensure_server_running():
    try:
        res = requests.get(f"{BASE_URL}/healthz", timeout=1.0)
        if res.status_code == 200:
            return
    except Exception:
        pass

    import uvicorn
    from main import app
    print("🚀 Initializing in-process test server on port 8000...")
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="error")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(30):
        time.sleep(0.3)
        try:
            res = requests.get(f"{BASE_URL}/healthz", timeout=1.0)
            if res.status_code == 200:
                print("✅ Test server is ready and responding!")
                return
        except Exception:
            continue
    raise RuntimeError("Failed to launch in-process test server on port 8000")

ensure_server_running()

print("=" * 70)
print("🎹 AI-STEAM v2.0 Backend Pipeline & REST API Verification Suite")
print("   (Testing Without Demo Score - True OMR & Always-On Editor)")
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

    img = np.ones((400, 800, 3), dtype=np.uint8) * 255
    for y in [100, 120, 140, 160, 180]:
        cv2.line(img, (50, y), (750, y), (0, 0, 0), 2)
    M = cv2.getRotationMatrix2D((400, 200), 5.0, 1.0)
    rotated = cv2.warpAffine(img, M, (800, 400), borderValue=(255, 255, 255))
    _, encoded = cv2.imencode(".png", rotated)
    raw_bytes = encoded.tobytes()

    optimized_bytes = optimizer.optimize(raw_bytes)
    assert len(optimized_bytes) > 0, "Optimized image byte array is empty"

    out_arr = np.frombuffer(optimized_bytes, np.uint8)
    out_img = cv2.imdecode(out_arr, cv2.IMREAD_GRAYSCALE)
    assert out_img.shape[1] % 32 == 0, f"Target width expected multiple of 32, got {out_img.shape[1]}"
    assert out_img.shape[0] % 32 == 0, f"Target height expected multiple of 32, got {out_img.shape[0]}"
    return f"Input bytes: {len(raw_bytes):,} B -> Optimized: {len(optimized_bytes):,} B (Width: {out_img.shape[1]}px, Height: {out_img.shape[0]}px)"


# 2. Score Corrector Component Test
@test("2. ScoreCorrector (Music Theory Normalization Component)")
def test_score_corrector():
    from core.corrector import ScoreCorrector
    corrector = ScoreCorrector()

    s = m21.stream.Score()
    p1 = m21.stream.Part()
    m1 = m21.stream.Measure(number=1)

    m1.append(m21.note.Note('C4', quarterLength=1.0))
    dup_note = m21.note.Note('C4', quarterLength=1.0)
    m1.insert(0.0, dup_note)
    fragment = m21.note.Note('E4', quarterLength=0.001)
    m1.append(fragment)
    out_of_bound = m21.note.Note('C-1', quarterLength=1.0)
    m1.append(out_of_bound)

    p1.append(m1)
    s.append(p1)

    initial_notes = len(list(s.recurse().getElementsByClass(m21.note.Note)))
    assert initial_notes == 4, f"Expected 4 initial notes, got {initial_notes}"

    corrected_s = corrector.run_all(s)
    corrected_notes = list(corrected_s.recurse().getElementsByClass(m21.note.Note))

    for n in corrected_notes:
        assert 21 <= n.pitch.midi <= 108, f"Note {n.nameWithOctave} (MIDI {n.pitch.midi}) exceeds 88-key piano limits"
    assert len(corrected_notes) == 2, f"Expected 2 valid notes after deduplication & fragment removal, got {len(corrected_notes)}"
    return f"Initial notes: {initial_notes} -> Corrected notes: {len(corrected_notes)} (Fragments removed & 88-key clamped)"


# 3. REST API - Web Editor UI Servicing
@test("3. REST API: GET / (Web Editor UI Servicing)")
def test_api_index():
    res = requests.get(f"{BASE_URL}/", timeout=5)
    assert res.status_code == 200, f"Expected status 200, got {res.status_code}"
    assert "AI-STEAM" in res.text, "Response does not contain app brand 'AI-STEAM'"
    assert "osmd-container" in res.text, "Response missing 'osmd-container'"
    return f"Status: {res.status_code}, HTML length: {len(res.text):,} bytes"


# 4. REST API - Preprocess Image
@test("4. REST API: POST /api/preprocess (Image Upload & Optimization)")
def test_api_preprocess():
    img = np.ones((500, 800, 3), dtype=np.uint8) * 255
    for y in [100, 120, 140, 160, 180]:
        cv2.line(img, (50, y), (750, y), (0, 0, 0), 2)
    _, encoded = cv2.imencode(".png", img)
    files = {"file": ("test_sheet.png", encoded.tobytes(), "image/png")}

    res = requests.post(f"{BASE_URL}/api/preprocess", files=files, timeout=10)
    assert res.status_code == 200, f"Expected status 200, got {res.status_code}: {res.text}"
    data = res.json()
    assert data.get("status") == "success", f"Invalid response: {data}"
    assert "file_hash" in data, "file_hash missing in response"
    return f"file_hash: {data['file_hash'][:16]}..., image_url: {data['image_url']}"


# Global test score hash for subsequent tests (Dynamic score without demo file!)
DYNAMIC_SCORE_HASH = ""

# 5. REST API - Create Dynamic Blank Score (Always-On Editor)
@test("5. REST API: POST /api/score/new (Always-On Blank Score Creation)")
def test_api_create_new_score():
    global DYNAMIC_SCORE_HASH
    payload = {
        "title": "테스트 신규 악보",
        "time_signature": "4/4",
        "key_signature": "C",
        "measures_count": 4,
        "is_grand_staff": True
    }
    res = requests.post(f"{BASE_URL}/api/score/new", json=payload, timeout=10)
    assert res.status_code == 200, f"Expected status 200, got {res.status_code}: {res.text}"
    data = res.json()
    assert data.get("status") == "success", f"Failed new score creation: {data}"
    assert "file_hash" in data, "file_hash missing in new score response"
    assert "analysis" in data, "analysis missing in new score response"
    assert "midi_url" in data, "midi_url missing in new score response"
    DYNAMIC_SCORE_HASH = data["file_hash"]
    return f"Generated dynamic score hash: {DYNAMIC_SCORE_HASH}, Parts: {data['analysis'].get('total_parts')}, Measures: {data['analysis'].get('total_measures')}"


# 6. REST API - Render Score & Music Analysis
@test("6. REST API: POST /api/render (Score Analysis & MIDI Generation)")
def test_api_render():
    assert DYNAMIC_SCORE_HASH, "No dynamic score available"
    res = requests.post(
        f"{BASE_URL}/api/render",
        json={"file_hash": DYNAMIC_SCORE_HASH},
        timeout=10
    )
    assert res.status_code == 200, f"Expected status 200, got {res.status_code}: {res.text}"
    data = res.json()
    analysis = data.get("analysis", {})
    assert "total_measures" in analysis, "Analysis missing 'total_measures'"
    assert "key_signature" in analysis, "Analysis missing 'key_signature'"
    assert "time_signature" in analysis, "Analysis missing 'time_signature'"
    assert "midi_url" in data, "Response missing 'midi_url'"

    return (
        f"Measures: {analysis.get('total_measures')}, "
        f"Key: {analysis.get('key_signature')}, "
        f"Time Sig: {analysis.get('time_signature')}, "
        f"MIDI: {data.get('midi_url')}"
    )


# 7. REST API - Optimize Score (MusicXML Correction)
@test("7. REST API: POST /api/optimize (MusicXML Auto-Correction)")
def test_api_optimize():
    assert DYNAMIC_SCORE_HASH, "No dynamic score available"
    res = requests.post(
        f"{BASE_URL}/api/optimize",
        json={"file_hash": DYNAMIC_SCORE_HASH},
        timeout=10
    )
    assert res.status_code == 200, f"Expected status 200, got {res.status_code}: {res.text}"
    data = res.json()
    assert data.get("status") == "success", f"Failed optimization: {data}"
    return f"Optimization status: {data.get('status')}, target: {data.get('file_hash')}"


# 8. REST API - Interactive Edit (Pitch Shift & Chord Add)
@test("8. REST API: POST /api/edit_score (Precision Note Editing)")
def test_api_edit():
    assert DYNAMIC_SCORE_HASH, "No dynamic score available"
    payload = {
        "file_hash": DYNAMIC_SCORE_HASH,
        "measure_number": 1,
        "note_offset": 0.0,
        "new_pitch": "G4",
        "new_duration": 1.0,
        "part_index": 0
    }
    res = requests.post(f"{BASE_URL}/api/edit_score", json=payload, timeout=10)
    assert res.status_code == 200, f"Expected status 200, got {res.status_code}: {res.text}"
    data = res.json()
    assert data.get("status") == "success", f"Edit failed: {data}"
    return f"Edited measure 1, offset 0.0 -> new pitch G4 (status: {data.get('status')})"


# 9. REST API - Undo and Redo History
@test("9. REST API: POST /api/restore_score (Undo / Redo Stack)")
def test_api_undo_redo():
    assert DYNAMIC_SCORE_HASH, "No dynamic score available"
    res_undo = requests.post(
        f"{BASE_URL}/api/restore_score",
        json={"file_hash": DYNAMIC_SCORE_HASH, "action": "undo"},
        timeout=10
    )
    assert res_undo.status_code == 200, f"Undo failed: {res_undo.text}"
    data_undo = res_undo.json()
    assert data_undo.get("status") == "success", f"Undo status not success: {data_undo}"

    res_redo = requests.post(
        f"{BASE_URL}/api/restore_score",
        json={"file_hash": DYNAMIC_SCORE_HASH, "action": "redo"},
        timeout=10
    )
    assert res_redo.status_code == 200, f"Redo failed: {res_redo.text}"
    data_redo = res_redo.json()
    assert data_redo.get("status") == "success", f"Redo status not success: {data_redo}"

    return "Undo -> Redo roundtrip successfully restored snapshot state"


# 10. Cache File Delivery (MIDI & MusicXML on dynamic score)
@test("10. REST API: GET /api/cache/{filename} (Asset Delivery)")
def test_api_cache_files():
    assert DYNAMIC_SCORE_HASH, "No dynamic score available"
    mid_res = requests.get(f"{BASE_URL}/api/cache/{DYNAMIC_SCORE_HASH}.mid", timeout=5)
    assert mid_res.status_code == 200, f"Failed to get MIDI: {mid_res.status_code}"
    assert mid_res.content.startswith(b"MThd"), "Invalid MIDI header"

    xml_res = requests.get(f"{BASE_URL}/api/cache/{DYNAMIC_SCORE_HASH}.musicxml", timeout=5)
    assert xml_res.status_code == 200, f"Failed to get MusicXML: {xml_res.status_code}"
    assert b"score-partwise" in xml_res.content or b"xml" in xml_res.content, "Invalid MusicXML content"

    return f"Dynamic {DYNAMIC_SCORE_HASH}.mid ({len(mid_res.content):,} B) & {DYNAMIC_SCORE_HASH}.musicxml ({len(xml_res.content):,} B) verified"


if __name__ == "__main__":
    test_image_optimizer()
    test_score_corrector()
    test_api_index()
    test_api_preprocess()
    test_api_create_new_score()
    test_api_render()
    test_api_optimize()
    test_api_edit()
    test_api_undo_redo()
    test_api_cache_files()

    print("\n" + "=" * 70)
    print(f"📊 TEST SUMMARY: {passed} PASSED, {failed} FAILED out of {passed + failed} total tests")
    print("=" * 70)
    if failed > 0:
        sys.exit(1)
    sys.exit(0)
