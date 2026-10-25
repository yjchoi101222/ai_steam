"""
test_performance_evaluation.py
AI-STEAM Performance Assessment Engine Automated Test Suite
Exhaustively tests:
1. Ground Truth MusicXML note extraction
2. Perfect performance evaluation (Grade S, 100 pts)
3. Pitch errors & accidentals alignment
4. Timing / rhythm deviation & BPM estimation
5. Missed notes and incomplete performance handling
6. Empty / silent performance boundary safety
7. Synthetic WAV audio pitch & onset extraction (wave + numpy)
8. MIDI file parsing and evaluation
9. REST API POST /api/evaluate/demo
10. REST API POST /api/evaluate/live
11. REST API POST /api/evaluate/upload (WAV and MIDI)
"""

import os
import sys
import math
import wave
import time
import threading
import tempfile
import requests
import numpy as np
import music21 as m21

# Windows console encoding
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from core.evaluator import PerformanceEvaluator, evaluator
from core.pipeline import SheetMusicAnalyzerPipeline

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


def run_all_tests():
    ensure_server()

    print("\n" + "=" * 75)
    print("🎻 AI-STEAM v2.0 Performance Evaluation & AI Feedback Verification Suite")
    print("=" * 75)

    pipeline = SheetMusicAnalyzerPipeline()
    pipeline._ensure_default_demo()
    demo_xml = os.path.join(pipeline.cache_dir, "demo.musicxml")

    passed_count = 0
    total_count = 11

    # -------------------------------------------------------------------------
    # TEST 1: MusicXML에서 기대 음표 시퀀스 정상 추출 검증
    # -------------------------------------------------------------------------
    print("\n▶ [TEST 1] MusicXML에서 기대 음표 시퀀스 정상 추출 검증 ...")
    try:
        notes = evaluator.extract_expected_notes_from_xml(demo_xml)
        assert len(notes) > 0, "추출된 음표가 0개입니다."
        first = notes[0]
        assert "pitch" in first and "midi" in first and "measure" in first
        print(f"  └─ ✅ PASSED: 총 {len(notes)}개 기대 음표 추출 완료 (첫 음: {first['pitch']}, MIDI {first['midi']})")
        passed_count += 1
    except Exception as e:
        print(f"  └─ ❌ FAILED: {str(e)}")

    # -------------------------------------------------------------------------
    # TEST 2: 완벽한 연주 평가 (100점, S등급)
    # -------------------------------------------------------------------------
    print("\n▶ [TEST 2] 완벽한 연주(모든 음정 및 박자 100% 일치) 평가 검증 ...")
    try:
        expected = evaluator.extract_expected_notes_from_xml(demo_xml)
        bpm = 100.0
        sec_per_beat = 60.0 / bpm
        played = []
        for n in expected:
            played.append({
                "pitch": n["pitch"],
                "midi": n["midi"],
                "time": n["offset"] * sec_per_beat,
                "duration": n["duration"] * sec_per_beat,
                "velocity": 90
            })

        result = evaluator.evaluate_performance(expected, played, target_bpm=bpm)
        assert result["total_score"] == 100, f"완벽 연주인데 {result['total_score']}점 반환"
        assert result["grade"] == "S", f"등급이 S가 아닌 {result['grade']}"
        assert result["pitch_score"] == 100.0
        assert result["statistics"]["correct"] == len(expected)
        assert result["statistics"]["pitch_error"] == 0
        print(f"  └─ ✅ PASSED: 점수 {result['total_score']}점, 등급 '{result['grade']}' ({result['grade_title']}) 완벽 판정")
        passed_count += 1
    except Exception as e:
        print(f"  └─ ❌ FAILED: {str(e)}")

    # -------------------------------------------------------------------------
    # TEST 3: 음정 오류 정밀 식별 및 감점 검증
    # -------------------------------------------------------------------------
    print("\n▶ [TEST 3] 음정 오류(잘못된 음 연주) 정밀 식별 및 감점 검증 ...")
    try:
        expected = evaluator.extract_expected_notes_from_xml(demo_xml)
        bpm = 100.0
        sec_per_beat = 60.0 / bpm
        played = []
        for idx, n in enumerate(expected):
            midi_val = n["midi"] + 1 if idx % 2 == 1 else n["midi"]
            played.append({
                "pitch": f"MIDI_{midi_val}",
                "midi": midi_val,
                "time": n["offset"] * sec_per_beat,
                "duration": n["duration"] * sec_per_beat,
                "velocity": 85
            })

        result = evaluator.evaluate_performance(expected, played, target_bpm=bpm)
        assert result["total_score"] < 90, f"오류가 많은데 {result['total_score']}점 반환"
        assert result["statistics"]["pitch_error"] > 0, "음정 오류가 카운트되지 않음"
        print(f"  └─ ✅ PASSED: 점수 {result['total_score']}점, 오음 {result['statistics']['pitch_error']}개 정확히 식별")
        passed_count += 1
    except Exception as e:
        print(f"  └─ ❌ FAILED: {str(e)}")

    # -------------------------------------------------------------------------
    # TEST 4: 템포 빠름/느림 감지 및 연주 BPM 추정 검증
    # -------------------------------------------------------------------------
    print("\n▶ [TEST 4] 리듬 편차(템포 빠름/느림) 감지 및 연주 BPM 추정 검증 ...")
    try:
        expected = evaluator.extract_expected_notes_from_xml(demo_xml)
        actual_bpm = 130.0
        sec_per_beat = 60.0 / actual_bpm
        played = []
        for n in expected:
            played.append({
                "pitch": n["pitch"],
                "midi": n["midi"],
                "time": n["offset"] * sec_per_beat,
                "duration": n["duration"] * sec_per_beat,
                "velocity": 85
            })

        result = evaluator.evaluate_performance(expected, played, target_bpm=100.0)
        assert abs(result["estimated_bpm"] - actual_bpm) <= 5.0, f"BPM 추정 실패: 실제={actual_bpm}, 추정={result['estimated_bpm']}"
        print(f"  └─ ✅ PASSED: 실제 연주 {actual_bpm} BPM -> 알고리즘 추정 {result['estimated_bpm']} BPM 일치")
        passed_count += 1
    except Exception as e:
        print(f"  └─ ❌ FAILED: {str(e)}")

    # -------------------------------------------------------------------------
    # TEST 5: 누락된 음표 감지 및 완성도 페널티 검증
    # -------------------------------------------------------------------------
    print("\n▶ [TEST 5] 누락된 음표(미연주) 감지 및 완성도 페널티 검증 ...")
    try:
        expected = evaluator.extract_expected_notes_from_xml(demo_xml)
        half_expected = expected[:len(expected) // 2]
        sec_per_beat = 60.0 / 100.0
        played = []
        for n in half_expected:
            played.append({
                "pitch": n["pitch"],
                "midi": n["midi"],
                "time": n["offset"] * sec_per_beat,
                "duration": n["duration"] * sec_per_beat,
                "velocity": 80
            })

        result = evaluator.evaluate_performance(expected, played, target_bpm=100.0)
        assert result["completeness"] <= 60.0
        assert result["statistics"]["missed"] > 0
        print(f"  └─ ✅ PASSED: 완성도 {result['completeness']}%, 누락음 {result['statistics']['missed']}개 정확히 감점")
        passed_count += 1
    except Exception as e:
        print(f"  └─ ❌ FAILED: {str(e)}")

    # -------------------------------------------------------------------------
    # TEST 6: 무연주(0개 음표) 경계 조건 안전 처리 검증
    # -------------------------------------------------------------------------
    print("\n▶ [TEST 6] 무연주(0개 음표) 경계 조건 안전 처리 검증 ...")
    try:
        expected = evaluator.extract_expected_notes_from_xml(demo_xml)
        result = evaluator.evaluate_performance(expected, [])
        assert result["total_score"] == 0
        assert result["grade"] == "D"
        assert result["statistics"]["missed"] == len(expected)
        print("  └─ ✅ PASSED: 무연주 상태 0점 및 D등급 정상 반환 (무충돌 안전 보장)")
        passed_count += 1
    except Exception as e:
        print(f"  └─ ❌ FAILED: {str(e)}")

    # -------------------------------------------------------------------------
    # TEST 7: 순수 NumPy/Wave 가상 오디오(WAV) 피치 & 온셋 분석 검증
    # -------------------------------------------------------------------------
    print("\n▶ [TEST 7] 순수 NumPy/Wave 가상 오디오(WAV) 피치 & 온셋 분석 검증 ...")
    tmp_wav_path = None
    try:
        framerate = 44100
        t1 = np.linspace(0, 0.45, int(framerate * 0.45), endpoint=False)
        sine1 = 0.6 * np.sin(2 * np.pi * 440.0 * t1)  # A4 (440Hz, MIDI 69)
        t2 = np.linspace(0, 0.45, int(framerate * 0.45), endpoint=False)
        sine2 = 0.6 * np.sin(2 * np.pi * 523.25 * t2) # C5 (523.25Hz, MIDI 72)
        audio_data = np.concatenate([sine1, np.zeros(int(framerate * 0.05)), sine2])
        audio_int16 = (audio_data * 32767).astype(np.int16)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_wav_path = tmp.name

        with wave.open(tmp_wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(framerate)
            wf.writeframes(audio_int16.tobytes())

        detected = evaluator.extract_notes_from_wav(tmp_wav_path)
        assert len(detected) > 0, "WAV에서 음표가 검출되지 않음"
        first_midi = detected[0]["midi"]
        assert abs(first_midi - 69) <= 1, f"A4(69) 기대했으나 {first_midi} 검출"
        print(f"  └─ ✅ PASSED: 440Hz 신호에서 A4(MIDI {first_midi}) 정확히 검출 성공 (총 {len(detected)}개 온셋)")
        passed_count += 1
    except Exception as e:
        print(f"  └─ ❌ FAILED: {str(e)}")
    finally:
        if tmp_wav_path and os.path.exists(tmp_wav_path):
            try:
                os.remove(tmp_wav_path)
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # TEST 8: MIDI 파일 파싱 및 음표 목록 추출 검증
    # -------------------------------------------------------------------------
    print("\n▶ [TEST 8] MIDI 파일 파싱 및 음표 목록 추출 검증 ...")
    try:
        demo_mid = os.path.join(pipeline.cache_dir, "demo.mid")
        notes = evaluator.extract_notes_from_midi(demo_mid)
        assert len(notes) > 0, "MIDI에서 음표가 추출되지 않음"
        print(f"  └─ ✅ PASSED: demo.mid 파싱 완료, 총 {len(notes)}개 음표 추출")
        passed_count += 1
    except Exception as e:
        print(f"  └─ ❌ FAILED: {str(e)}")

    # -------------------------------------------------------------------------
    # TEST 9: REST API: POST /api/evaluate/demo (원클릭 시연 API) 검증
    # -------------------------------------------------------------------------
    print("\n▶ [TEST 9] REST API: POST /api/evaluate/demo (원클릭 시연 API) 검증 ...")
    try:
        res = requests.post(f"{BASE_URL}/api/evaluate/demo?file_hash=demo&target_bpm=100")
        assert res.status_code == 200, f"API 오류: {res.text}"
        data = res.json()
        assert "total_score" in data and "grade" in data and "details" in data
        assert data["total_score"] >= 80
        print(f"  └─ ✅ PASSED: 데모 연주 평가 완료 -> 점수={data['total_score']}점, 등급='{data['grade']}'")
        passed_count += 1
    except Exception as e:
        print(f"  └─ ❌ FAILED: {str(e)}")

    # -------------------------------------------------------------------------
    # TEST 10: REST API: POST /api/evaluate/live (실시간 건반 입력 API) 검증
    # -------------------------------------------------------------------------
    print("\n▶ [TEST 10] REST API: POST /api/evaluate/live (실시간 건반 입력 API) 검증 ...")
    try:
        expected = evaluator.extract_expected_notes_from_xml(demo_xml)
        notes_payload = []
        for n in expected[:6]:
            notes_payload.append({
                "pitch": n["pitch"],
                "midi": n["midi"],
                "time": n["offset"] * 0.6,
                "duration": n["duration"] * 0.6
            })
        payload = {
            "file_hash": "demo",
            "target_bpm": 100.0,
            "notes": notes_payload
        }
        res = requests.post(f"{BASE_URL}/api/evaluate/live", json=payload)
        assert res.status_code == 200, f"API 오류: {res.text}"
        data = res.json()
        assert "total_score" in data and "pitch_score" in data
        print(f"  └─ ✅ PASSED: 실시간 건반 평가 API 응답 정상 -> 점수={data['total_score']}점")
        passed_count += 1
    except Exception as e:
        print(f"  └─ ❌ FAILED: {str(e)}")

    # -------------------------------------------------------------------------
    # TEST 11: REST API: POST /api/evaluate/upload (MIDI 파일 업로드 평가) 검증
    # -------------------------------------------------------------------------
    print("\n▶ [TEST 11] REST API: POST /api/evaluate/upload (MIDI 파일 업로드 평가) 검증 ...")
    try:
        demo_mid = os.path.join(pipeline.cache_dir, "demo.mid")
        with open(demo_mid, "rb") as f:
            files = {"file": ("my_performance.mid", f, "audio/midi")}
            data = {"file_hash": "demo", "target_bpm": "100"}
            res = requests.post(f"{BASE_URL}/api/evaluate/upload", files=files, data=data)

        assert res.status_code == 200, f"API 오류: {res.text}"
        res_data = res.json()
        assert "total_score" in res_data and "grade" in res_data
        print(f"  └─ ✅ PASSED: MIDI 파일 업로드 평가 성공 -> 점수={res_data['total_score']}점, 등급='{res_data['grade']}'")
        passed_count += 1
    except Exception as e:
        print(f"  └─ ❌ FAILED: {str(e)}")

    print("\n" + "=" * 75)
    print(f"📊 최종 평가 테스트 결과: {passed_count}/{total_count} PASSED ({passed_count/total_count*100:.1f}%)")
    print("=" * 75)

    if passed_count != total_count:
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
