import os
# Render 512MB RAM OOM 방지: 딥러닝/수치연산 단일 쓰레드 제한
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import sys
import io
import tempfile
import shutil
from typing import Optional, Dict, Any, List

# Windows cp949 인코딩 오류 완전 방지 (in-place reconfigure)
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

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.pipeline import SheetMusicAnalyzerPipeline
from core.evaluator import PerformanceEvaluator, evaluator

app = FastAPI(
    title="AI-STEAM Interactive Sheet Music Studio",
    description="OMR Sheet Music Recognition & Interactive Score Editor Backend",
    version="2.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)

pipeline = SheetMusicAnalyzerPipeline(base_dir=BASE_DIR)

# 정적 리소스 마운트
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# Pydantic 요청 스키마 정의
class ExtractRequest(BaseModel):
    file_hash: str
    filename: str = "sheet.png"
    mode: str = "fast"


class OptimizeRequest(BaseModel):
    file_hash: str


class RenderRequest(BaseModel):
    file_hash: str


class EditScoreRequest(BaseModel):
    file_hash: str
    measure_number: int
    note_index: Optional[int] = None
    note_offset: Optional[float] = None
    new_pitch: Optional[str] = None
    new_duration: Optional[float] = None
    part_index: int = 0
    is_chord_add: bool = False
    action: Optional[str] = None


class RestoreScoreRequest(BaseModel):
    file_hash: str
    action: str = "undo"  # "undo" 또는 "redo"


class NewScoreRequest(BaseModel):
    title: str = "새 악보"
    time_signature: str = "4/4"
    key_signature: str = "C"
    measures_count: int = 4
    is_grand_staff: bool = True


class LivePerformanceRequest(BaseModel):
    file_hash: str = "demo"
    target_bpm: float = 100.0
    notes: List[Dict[str, Any]] = []


def get_score_xml_path(file_hash: str) -> str:
    """주어진 file_hash에 대응하는 최적화된 MusicXML 악보 파일 경로를 탐색하여 반환합니다."""
    clean_hash = os.path.basename(file_hash)
    opt_path = os.path.join(pipeline.cache_dir, f"{clean_hash}_opt.musicxml")
    if os.path.exists(opt_path):
        return opt_path
    base_path = os.path.join(pipeline.cache_dir, f"{clean_hash}.musicxml")
    if os.path.exists(base_path):
        return base_path
    if clean_hash.startswith("demo"):
        pipeline._ensure_default_demo()
        demo_path = os.path.join(pipeline.cache_dir, "demo_opt.musicxml")
        if os.path.exists(demo_path):
            return demo_path
        demo_fallback = os.path.join(pipeline.cache_dir, "demo.musicxml")
        if os.path.exists(demo_fallback):
            return demo_fallback
    static_default = os.path.join(STATIC_DIR, "default.musicxml")
    if os.path.exists(static_default):
        return static_default
    raise FileNotFoundError(f"악보 파일을 찾을 수 없습니다: {file_hash}")


# ==================== REST API 라우터 ====================

@app.get("/healthz")
@app.get("/health")
async def health_check():
    """클라우드 배포(Render 등) 헬스체크 및 서비스 상태 확인 엔드포인트"""
    return {"status": "healthy", "service": "ai-steam-omr", "version": "2.0.0"}


@app.get("/", response_class=HTMLResponse)
@app.get("/intro", response_class=HTMLResponse)
@app.get("/about", response_class=HTMLResponse)
async def serve_landing():
    """MuseAI 프로젝트 소개 랜딩 페이지(포스터)를 반환합니다."""
    landing_path = os.path.join(STATIC_DIR, "landing.html")
    if os.path.exists(landing_path):
        return FileResponse(landing_path)
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>MuseAI: static/landing.html 파일을 찾을 수 없습니다.</h1>")


@app.get("/editor", response_class=HTMLResponse)
async def serve_editor():
    """인터랙티브 AI 악보 에디터 화면을 반환합니다."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>AI-STEAM 악보 에디터: static/index.html 파일을 찾을 수 없습니다.</h1>")


@app.get("/report", response_class=HTMLResponse)
async def serve_report():
    """송도고등학교 MuseAI 학술 보고서 (논문 포스터) 화면을 반환합니다."""
    report_path = os.path.join(STATIC_DIR, "report.html")
    if os.path.exists(report_path):
        return FileResponse(report_path)
    return HTMLResponse("<h1>MuseAI 학술 보고서: static/report.html 파일을 찾을 수 없습니다.</h1>")


@app.post("/api/preprocess")
async def preprocess(file: UploadFile = File(...)):
    """[1단계] 악보 이미지/PDF 업로드 및 OpenCV 전처리"""
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="업로드된 파일 내용이 비어있습니다.")
        # U-Net ConvTranspose ShapeInferenceError 방지: 1350px 해상도 사용
        result = pipeline.preprocess_image(content, file.filename, target_width=1350)
        return {
            "status": "success",
            "file_hash": result["file_hash"],
            "filename": result["filename"],
            "image_url": result["image_url"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"전처리 실패: {str(e)}")


@app.post("/api/extract")
async def extract(req: ExtractRequest):
    """[2단계] 비동기 OMR(oemer) 추출 작업 등록 (512MB RAM 인스턴스 동시 실행 방지)"""
    if pipeline.is_extracting():
        raise HTTPException(
            status_code=429,
            detail="현재 다른 악보 인식 작업이 진행 중입니다. 클라우드 메모리(512MB) 보호를 위해 이전 작업이 끝난 후 다시 시도해 주세요."
        )
    try:
        job_id = pipeline.start_extract_job(
            file_hash=req.file_hash,
            filename=req.filename,
            mode=req.mode
        )
        return {
            "status": "started",
            "job_id": job_id,
            "file_hash": req.file_hash
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OMR 작업 시작 실패: {str(e)}")


@app.get("/api/extract/status/{job_id}")
async def get_extract_status(job_id: str):
    """OMR 작업 진행률 및 상태 폴링"""
    try:
        status_info = pipeline.get_job_status(job_id)
        return status_info
    except KeyError:
        raise HTTPException(status_code=404, detail="해당 job_id를 찾을 수 없습니다.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/extract/{job_id}/cancel")
async def cancel_extract(job_id: str):
    """OMR 작업 강제 취소"""
    success = pipeline.cancel_job(job_id)
    if success:
        return {"status": "cancelled", "job_id": job_id}
    raise HTTPException(status_code=404, detail="취소할 작업을 찾을 수 없습니다.")


@app.post("/api/optimize")
async def optimize(req: OptimizeRequest):
    """[3단계] MusicXML 음악 규칙 기반 1차 자동 교정"""
    try:
        pipeline.optimize_xml(req.file_hash)
        return {"status": "success", "file_hash": req.file_hash}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"최적화 실패: {str(e)}")


@app.post("/api/render")
async def render(req: RenderRequest):
    """[4단계] 음악 이론 메타데이터 분석 및 MIDI 오디오 파일 생성"""
    try:
        render_data = pipeline.render_audio(req.file_hash)
        return render_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"렌더링 실패: {str(e)}")


@app.post("/api/edit_score")
async def edit_score(req: EditScoreRequest):
    """
    [수동 교정 API]
    마디, 보표(part_index), 오프셋/인덱스 기반 정밀 음표 수정 및 화음/쉼표 변환
    """
    try:
        result = pipeline.edit_note_in_xml(
            file_hash=req.file_hash,
            measure_number=req.measure_number,
            note_index=req.note_index,
            note_offset=req.note_offset,
            new_pitch=req.new_pitch,
            new_duration=req.new_duration,
            part_index=req.part_index,
            is_chord_add=req.is_chord_add,
            action=req.action
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/restore_score")
async def restore_score(req: RestoreScoreRequest):
    """[Undo / Redo API] 직전 수정 스냅샷으로 복원"""
    try:
        if req.action == "undo":
            xml_str = pipeline.undo(req.file_hash)
        elif req.action == "redo":
            xml_str = pipeline.redo(req.file_hash)
        else:
            raise ValueError("action은 'undo' 또는 'redo'여야 합니다.")

        if xml_str is None:
            return {"status": "noop", "message": "더 이상 복원할 히스토리가 없습니다."}

        render_data = pipeline.render_audio(req.file_hash)
        return {
            "status": "success",
            "action": req.action,
            "analysis": render_data["analysis"],
            "midi_url": render_data["midi_url"]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/score/new")
async def create_new_score(req: NewScoreRequest = NewScoreRequest()):
    """[상시 에디터 지원] 데모 악보 없이 새로운 빈 악보(대보표/단일보표)를 생성하여 즉시 편집 모드로 진입합니다."""
    try:
        render_data = pipeline.create_blank_score(
            title=req.title,
            time_signature=req.time_signature,
            key_signature=req.key_signature,
            measures_count=req.measures_count,
            is_grand_staff=req.is_grand_staff
        )
        return render_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"새 악보 생성 실패: {str(e)}")


@app.delete("/api/cache")
async def clear_cache():
    """서버 캐시 디렉터리 정리 API (기본 데모 악보 복원 보장)"""
    try:
        pipeline.clear_cache()
        return {"status": "success", "message": "캐시가 성공적으로 초기화되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"캐시 삭제 실패: {str(e)}")


# ==================== AI PERFORMANCE EVALUATION API ====================

@app.post("/api/evaluate/live")
async def evaluate_live(req: LivePerformanceRequest):
    """[AI 연주 평가] 실시간 가상 건반/마이크 실시간 입력 이벤트 기반 연주 평가"""
    try:
        xml_path = get_score_xml_path(req.file_hash)
        expected_notes = evaluator.extract_expected_notes_from_xml(xml_path)
        eval_result = evaluator.evaluate_performance(
            expected_notes=expected_notes,
            played_notes=req.notes,
            target_bpm=req.target_bpm
        )
        return eval_result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"연주 평가 실패: {str(e)}")


@app.post("/api/evaluate/upload")
async def evaluate_upload(
    file: UploadFile = File(...),
    file_hash: str = Form("demo"),
    target_bpm: float = Form(100.0)
):
    """[AI 연주 평가] 사용자 업로드 오디오(WAV) 또는 MIDI 파일 기반 연주 평가"""
    try:
        xml_path = get_score_xml_path(file_hash)
        expected_notes = evaluator.extract_expected_notes_from_xml(xml_path)

        filename = file.filename.lower()
        suffix = os.path.splitext(filename)[1]

        # 임시 파일 저장 후 분석 (512MB RAM 안전 격리)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            shutil.copyfileobj(file.file, tmp)

        try:
            if suffix in [".mid", ".midi"]:
                played_notes = evaluator.extract_notes_from_midi(tmp_path)
            elif suffix in [".wav", ".wave"]:
                played_notes = evaluator.extract_notes_from_wav(tmp_path)
            else:
                try:
                    played_notes = evaluator.extract_notes_from_wav(tmp_path)
                except Exception:
                    raise ValueError(f"지원하지 않는 오디오 형식입니다 ({suffix}). .wav 또는 .mid 파일을 업로드해 주세요.")

            eval_result = evaluator.evaluate_performance(
                expected_notes=expected_notes,
                played_notes=played_notes,
                target_bpm=target_bpm
            )
            return eval_result
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"연주 파일 평가 실패: {str(e)}")


@app.post("/api/evaluate/demo")
async def evaluate_demo(
    file_hash: str = "demo",
    target_bpm: float = 100.0
):
    """[AI 연주 평가] 원클릭 시연용 데모 연주 평가 (시뮬레이션 연주를 통한 즉각적인 AI 피드백 검증)"""
    try:
        xml_path = get_score_xml_path(file_hash)
        expected_notes = evaluator.extract_expected_notes_from_xml(xml_path)

        seconds_per_beat = 60.0 / target_bpm
        simulated_notes = []
        for idx, exp in enumerate(expected_notes):
            # 5번째 음표에서 반음 샵 오차 모의 (자연스러운 미스타건 시뮬레이션)
            if idx == 4:
                midi = exp["midi"] + 1
                step = exp["pitch"][0] + "#" + exp["pitch"][-1]
            else:
                midi = exp["midi"]
                step = exp["pitch"]

            # 약간의 인간적인 타이밍 지터 (-0.03 ~ +0.05초)
            timing_jitter = ((idx * 7) % 11 - 5) * 0.008
            sim_time = round(exp["offset"] * seconds_per_beat + timing_jitter, 3)
            sim_dur = round(exp["duration"] * seconds_per_beat * 0.95, 3)

            simulated_notes.append({
                "pitch": step,
                "midi": midi,
                "time": sim_time,
                "duration": sim_dur,
                "velocity": 85
            })

        eval_result = evaluator.evaluate_performance(
            expected_notes=expected_notes,
            played_notes=simulated_notes,
            target_bpm=target_bpm
        )
        return eval_result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"데모 연주 평가 실패: {str(e)}")


@app.get("/api/cache/{filename}")
async def get_cached_file(filename: str):
    """생성된 이미지, MusicXML, MIDI 파일을 안전하게 다운로드/서빙합니다."""
    # 경로 조작(Directory Traversal) 방지
    clean_filename = os.path.basename(filename)
    file_path = os.path.join(pipeline.cache_dir, clean_filename)

    if not os.path.exists(file_path):
        if clean_filename.startswith("demo"):
            pipeline._ensure_default_demo()
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="캐시 파일을 찾을 수 없습니다.")

    media_type = "application/octet-stream"
    if clean_filename.endswith(".png"):
        media_type = "image/png"
    elif clean_filename.endswith(".mid") or clean_filename.endswith(".midi"):
        media_type = "audio/midi"
    elif clean_filename.endswith(".musicxml") or clean_filename.endswith(".xml"):
        media_type = "application/vnd.recordare.musicxml+xml"

    return FileResponse(file_path, media_type=media_type, filename=clean_filename)


if __name__ == "__main__":
    import uvicorn
    # Render, Heroku 등 클라우드 환경에서는 PORT 환경 변수를 자동 할당합니다.
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("main:app", host=host, port=port, reload=False)

