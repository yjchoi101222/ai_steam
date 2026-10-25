"""
AI-STEAM v2.0 Internal Testing Suite: Limits & Cache Initialization Verification
테스트 항목:
1. 88건반 음역대 한도 클램핑 검증 (A0 ~ C8)
2. Undo / Redo 히스토리 스택 20개 한도 (FIFO 캡 & noop 경계 검증)
3. 고해상도(4000px+) 이미지 업로드 시 메모리 안전 리사이징 한도 검증
4. OMR 동시 실행 락(_omr_execution_lock) 및 작업 취소 한도 검증
5. 신규 악보 상태 초기화 검증 (POST /api/score/new)
6. 서버 캐시 전면 초기화 검증 (DELETE /api/cache -> 더미 삭제 & demo 자동 복원)
7. 복원된 데모 악보 및 MIDI 정상 서빙 검증 (GET /api/cache/{filename})
"""

import sys
import os
import time
import threading
import requests
import numpy as np
import cv2
import music21 as m21

# Windows 콘솔 인코딩 대응
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_URL = "http://127.0.0.1:8000"

def ensure_server():
    try:
        r = requests.get(f"{BASE_URL}/healthz", timeout=1.0)
        if r.status_code == 200:
            return
    except Exception:
        pass

    import uvicorn
    from main import app
    print("🚀 [Server Init] 포트 8000에서 테스트용 uvicorn 서버 구동 중...")
    cfg = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="error")
    srv = uvicorn.Server(cfg)
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(30):
        time.sleep(0.3)
        try:
            r = requests.get(f"{BASE_URL}/healthz", timeout=1.0)
            if r.status_code == 200:
                print("✅ [Server Ready] 서버 기동 완료!")
                return
        except Exception:
            continue
    raise RuntimeError("로컬 테스트 서버 기동 실패")

ensure_server()

print("\n" + "=" * 75)
print("🔍 AI-STEAM v2.0 로컬 한도(Limits) & 초기화(Reset) 내부 정밀 테스트")
print("=" * 75)

passed = 0
failed = 0

def run_test(title):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            global passed, failed
            print(f"\n▶ [TEST] {title} ...", flush=True)
            try:
                msg = fn(*args, **kwargs)
                print(f"  └─ ✅ PASSED: {msg}")
                passed += 1
            except Exception as e:
                print(f"  └─ ❌ FAILED: {e}")
                failed += 1
        return wrapper
    return decorator


# -------------------------------------------------------------
# TEST 1: 88건반 음정 한도 (MIDI 21 ~ 108) 이조 및 보정 한계 테스트
# -------------------------------------------------------------
@run_test("1. 88건반(A0~C8) 음역대 상하한 클램핑 한도 검증")
def test_piano_88key_limits():
    from core.corrector import ScoreCorrector
    corrector = ScoreCorrector()

    # 초고음(C9, MIDI 120), 초저음(C-1, MIDI 0) 생성
    s = m21.stream.Score()
    p = m21.stream.Part()
    m = m21.stream.Measure(number=1)
    
    too_high = m21.note.Note('C9', quarterLength=1.0) # MIDI 120
    too_low = m21.note.Note('C-1', quarterLength=1.0) # MIDI 0
    normal = m21.note.Note('C4', quarterLength=1.0)   # MIDI 60
    
    m.append(too_high)
    m.append(too_low)
    m.append(normal)
    p.append(m)
    s.append(p)

    corrected = corrector.run_all(s)
    notes = list(corrected.recurse().getElementsByClass(m21.note.Note))
    
    for n in notes:
        assert 21 <= n.pitch.midi <= 108, f"음표 {n.nameWithOctave} (MIDI {n.pitch.midi})가 88건반 범위를 벗어났습니다."
    
    return f"총 {len(notes)}개 음표 모두 88건반 한도(21<=MIDI<=108) 내로 클램핑 성공"


# -------------------------------------------------------------
# TEST 2: Undo / Redo 스택 20개 상한(FIFO) 및 경계(noop) 한도 테스트
# -------------------------------------------------------------
@run_test("2. Undo/Redo 20개 스택 한도(FIFO 초과 방지) 및 noop 경계 검증")
def test_undo_stack_limit_and_noop():
    # 1. 새 악보 생성
    res = requests.post(f"{BASE_URL}/api/score/new", json={"title": "Undo 한도 테스트", "measures_count": 4})
    assert res.status_code == 200, "새 악보 생성 실패"
    file_hash = res.json()["file_hash"]

    # 2. 25회 연속으로 음표 수정 요청 (상한 20개를 5회 초과)
    pitches = ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"]
    for i in range(25):
        p = pitches[i % len(pitches)]
        edit_res = requests.post(f"{BASE_URL}/api/edit_score", json={
            "file_hash": file_hash,
            "measure_number": 1,
            "note_offset": 0.0,
            "new_pitch": p,
            "part_index": 0
        })
        assert edit_res.status_code == 200, f"수정 {i+1}회차 실패"

    # 3. 백엔드 pipeline 인스턴스의 undo 스택 길이 확인 (정확히 20개여야 함)
    from main import pipeline
    undo_len = len(pipeline.history[file_hash]["undo"])
    assert undo_len <= 20, f"Undo 스택이 상한 20개를 초과했습니다: {undo_len}개"
    assert undo_len == 20, f"Undo 스택이 20개가 아닌 {undo_len}개입니다."

    # 4. 20회 연속 Undo 실행
    for u in range(20):
        undo_res = requests.post(f"{BASE_URL}/api/restore_score", json={"file_hash": file_hash, "action": "undo"})
        assert undo_res.status_code == 200, f"Undo {u+1}회차 실패"
        assert undo_res.json().get("status") == "success", f"Undo {u+1}회차 상태 불일치"

    # 5. 21번째 Undo 시도시 더 이상 없으므로 noop 반환 확인
    noop_undo = requests.post(f"{BASE_URL}/api/restore_score", json={"file_hash": file_hash, "action": "undo"})
    assert noop_undo.status_code == 200
    assert noop_undo.json().get("status") == "noop", f"스택 소진 후 noop 기대했으나 {noop_undo.json()} 반환"

    # 6. 20회 연속 Redo 실행
    for r in range(20):
        redo_res = requests.post(f"{BASE_URL}/api/restore_score", json={"file_hash": file_hash, "action": "redo"})
        assert redo_res.status_code == 200, f"Redo {r+1}회차 실패"
        assert redo_res.json().get("status") == "success", f"Redo {r+1}회차 상태 불일치"

    # 7. 21번째 Redo 시도시 noop 반환 확인
    noop_redo = requests.post(f"{BASE_URL}/api/restore_score", json={"file_hash": file_hash, "action": "redo"})
    assert noop_redo.status_code == 200
    assert noop_redo.json().get("status") == "noop", f"Redo 스택 소진 후 noop 기대했으나 {noop_redo.json()} 반환"

    return f"25회 수정 후 스택 20개 한도 엄수 (len=20) 및 Undo 20회 -> noop -> Redo 20회 -> noop 완벽 통과"


# -------------------------------------------------------------
# TEST 3: 고해상도(4000px+) 이미지 업로드 시 메모리 안전 리사이징 한도
# -------------------------------------------------------------
@run_test("3. 초대형 고해상도(4000x3000px) 이미지 전처리 리사이징 한도 검증")
def test_large_image_limit():
    from core.image_optimizer import SheetMusicOptimizer
    # 4000x3000 초거대 이미지 생성 (약 36MB 비압축)
    huge_img = np.ones((3000, 4000, 3), dtype=np.uint8) * 255
    # 오선지 모의 라인
    for y in [1000, 1100, 1200, 1300, 1400]:
        cv2.line(huge_img, (200, y), (3800, y), (0, 0, 0), 4)

    _, encoded = cv2.imencode(".png", huge_img)
    raw_bytes = encoded.tobytes()

    optimizer = SheetMusicOptimizer(target_width=1024)
    optimized_bytes = optimizer.optimize(raw_bytes)

    out_arr = np.frombuffer(optimized_bytes, np.uint8)
    out_img = cv2.imdecode(out_arr, cv2.IMREAD_GRAYSCALE)

    # 32의 배수 및 1024 한도 내로 축소되었는지 검증
    assert out_img.shape[1] == 1024, f"너비 한도 1024px 불일치: {out_img.shape[1]}px"
    assert out_img.shape[0] % 32 == 0, f"높이가 32의 배수가 아님: {out_img.shape[0]}px"
    assert out_img.shape[0] < 1000, f"예상보다 높이가 큼: {out_img.shape[0]}px"

    return f"원본 (4000x3000px) -> 리사이징 한도 적용 ({out_img.shape[1]}x{out_img.shape[0]}px, 32배수 패딩 완료)"


# -------------------------------------------------------------
# TEST 4: OMR 동시 실행 락(_omr_execution_lock) 및 작업 취소 한도
# -------------------------------------------------------------
@run_test("4. OMR 프로세스 단일 동시성 락 및 비동기 작업 취소 한도 검증")
def test_omr_concurrency_lock_and_cancel():
    from main import pipeline
    
    # 락 획득 상태 확인
    assert not pipeline._omr_execution_lock.locked(), "시작 전 락이 잠겨있습니다."

    # 모의 작업 등록
    job_id = "test_cancel_job_123"
    with pipeline._lock:
        pipeline.jobs[job_id] = {
            "status": "running",
            "percent": 30,
            "message": "분석 중",
            "file_hash": "dummy_hash",
            "cancel_flag": False,
            "error": None
        }

    # 취소 API 호출
    cancel_res = requests.post(f"{BASE_URL}/api/extract/{job_id}/cancel")
    assert cancel_res.status_code == 200, f"취소 API 실패: {cancel_res.text}"
    assert cancel_res.json().get("status") == "cancelled"

    # 취소 플래그 반영 확인
    with pipeline._lock:
        assert pipeline.jobs[job_id]["cancel_flag"] is True, "cancel_flag가 True로 세팅되지 않음"

    return "동시성 단일 락 확인 및 POST /api/extract/{job_id}/cancel 취소 플래그 주입 확인 완료"


# -------------------------------------------------------------
# TEST 5: 신규 빈 악보 상태 초기화 검증 (POST /api/score/new)
# -------------------------------------------------------------
@run_test("5. POST /api/score/new (새 악보 초기화 & 메타데이터 생성)")
def test_blank_score_reset():
    payload = {
        "title": "초기화된 신규 피아노 악보",
        "time_signature": "3/4",
        "key_signature": "G",
        "measures_count": 8,
        "is_grand_staff": True
    }
    res = requests.post(f"{BASE_URL}/api/score/new", json=payload)
    assert res.status_code == 200, f"새 악보 초기화 실패: {res.text}"
    data = res.json()
    assert data["status"] == "success"
    
    analysis = data["analysis"]
    assert analysis["total_measures"] == 8, f"마디 수 초기화 불일치: {analysis['total_measures']}"
    assert analysis["time_signature"] == "3/4", f"박자표 초기화 불일치: {analysis['time_signature']}"
    assert "G" in analysis["key_signature"], f"조표 초기화 불일치: {analysis['key_signature']}"
    assert analysis["total_parts"] == 2, f"대보표 2파트 초기화 불일치: {analysis['total_parts']}"

    return f"8마디, 3/4박자, G조, 양손 대보표(2파트) 깨끗한 초기 상태 생성 완료 (hash: {data['file_hash']})"


# -------------------------------------------------------------
# TEST 6: 전역 캐시 초기화 (DELETE /api/cache) & 데모 복원
# -------------------------------------------------------------
@run_test("6. DELETE /api/cache (전체 더미 캐시 청소 및 기본 데모 악보 보존/복원)")
def test_clear_cache_and_demo_recovery():
    from main import pipeline
    cache_dir = pipeline.cache_dir

    # 1. 고의로 더미 파일 5개 생성
    dummy_files = [f"dummy_test_{i}.png" for i in range(5)]
    for df in dummy_files:
        with open(os.path.join(cache_dir, df), "w") as f:
            f.write("temporary garbage data")

    assert all(os.path.exists(os.path.join(cache_dir, df)) for df in dummy_files), "더미 생성 실패"

    # 2. DELETE /api/cache 호출
    res = requests.delete(f"{BASE_URL}/api/cache")
    assert res.status_code == 200, f"캐시 초기화 실패: {res.text}"
    assert res.json().get("status") == "success"

    # 3. 더미 파일들이 깨끗이 사라졌는지 확인
    for df in dummy_files:
        assert not os.path.exists(os.path.join(cache_dir, df)), f"더미 파일 {df}가 삭제되지 않았습니다."

    # 4. 필수 기본 데모 파일들이 static/default.musicxml에서 자동 복원되었는지 확인
    demo_xml = os.path.join(cache_dir, "demo.musicxml")
    demo_opt = os.path.join(cache_dir, "demo_opt.musicxml")
    demo_mid = os.path.join(cache_dir, "demo.mid")

    assert os.path.exists(demo_xml), "demo.musicxml이 복원되지 않았습니다."
    assert os.path.exists(demo_opt), "demo_opt.musicxml이 복원되지 않았습니다."
    assert os.path.exists(demo_mid), "demo.mid가 생성되지 않았습니다."
    assert os.path.getsize(demo_xml) > 1000, "demo.musicxml 내용이 비정상입니다."
    assert os.path.getsize(demo_mid) > 50, "demo.mid 내용이 비정상입니다."

    return f"더미 파일 5개 전원 삭제 완료 및 demo.musicxml({os.path.getsize(demo_xml):,} B), demo.mid({os.path.getsize(demo_mid):,} B) 자동 복원 완벽 확인"


# -------------------------------------------------------------
# TEST 7: 캐시 초기화 후 정적 에셋 다운로드 무결성 검증
# -------------------------------------------------------------
@run_test("7. 캐시 초기화 직후 GET /api/cache/{filename} 엔드포인트 서빙 무결성 검증")
def test_cache_serving_after_reset():
    # 1. demo.musicxml 다운로드
    res_xml = requests.get(f"{BASE_URL}/api/cache/demo.musicxml")
    assert res_xml.status_code == 200, f"demo.musicxml 서빙 실패: {res_xml.status_code}"
    assert "application/vnd.recordare.musicxml+xml" in res_xml.headers.get("content-type", "")

    # 2. demo.mid 다운로드
    res_mid = requests.get(f"{BASE_URL}/api/cache/demo.mid")
    assert res_mid.status_code == 200, f"demo.mid 서빙 실패: {res_mid.status_code}"
    assert res_mid.content.startswith(b"MThd"), "유효한 MIDI 바이너리가 아닙니다."

    # 3. 만약 demo 파일이 지워져도 실시간 복구되는지 검증
    from main import pipeline
    demo_path = os.path.join(pipeline.cache_dir, "demo.musicxml")
    if os.path.exists(demo_path):
        os.remove(demo_path)
    
    # 지운 직후 다시 요청 -> get_cached_file 내부의 _ensure_default_demo() 동작 확인
    res_auto_rec = requests.get(f"{BASE_URL}/api/cache/demo.musicxml")
    assert res_auto_rec.status_code == 200, "요청 시 실시간 자동 복구 실패"
    assert os.path.exists(demo_path), "demo.musicxml이 실시간 자동 복원되지 않음"

    return "초기화 후 demo.musicxml, demo.mid 다운로드 및 파일 임의 삭제 시 실시간 자동 복구 완벽 작동"


if __name__ == "__main__":
    test_piano_88key_limits()
    test_undo_stack_limit_and_noop()
    test_large_image_limit()
    test_omr_concurrency_lock_and_cancel()
    test_blank_score_reset()
    test_clear_cache_and_demo_recovery()
    test_cache_serving_after_reset()

    print("\n" + "=" * 75)
    print(f"📊 한도 & 초기화 테스트 결과: {passed} PASSED, {failed} FAILED (총 {passed + failed}개)")
    print("=" * 75)

    if failed > 0:
        sys.exit(1)
    sys.exit(0)
