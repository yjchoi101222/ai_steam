import os
import sys
import io
import time
import uuid
import tempfile
import subprocess
import hashlib
import shutil
import threading
import multiprocessing
from typing import Dict, Any, Optional, List, Tuple

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

import music21 as m21
from core.corrector import ScoreCorrector
from core.image_optimizer import SheetMusicOptimizer


class SheetMusicAnalyzerPipeline:
    """
    악보 이미지 전처리, OMR(oemer) 추출(비동기 잡 관리/취소), 음악 이론 분석,
    양손 보표 지원 및 정밀 오프셋 기반 수동 교정, Undo/Redo 스냅샷 히스토리를
    담당하는 핵심 파이프라인 클래스
    """

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir:
            self.base_dir = os.path.abspath(base_dir)
        else:
            self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.cache_dir = os.path.join(self.base_dir, "omr_cache")
        os.makedirs(self.cache_dir, exist_ok=True)

        # OMR 비동기 잡 상태 추적 딕셔너리
        # job_id: {"status": "pending"|"running"|"completed"|"failed"|"cancelled", "percent": int, "message": str, "file_hash": str, "cancel_flag": bool, "error": str}
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.job_processes: Dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

        # 각 file_hash 별 Undo/Redo 히스토리 스택 (최대 20개 저장)
        # file_hash: {"undo": [xml_str, ...], "redo": [xml_str, ...]}
        self.history: Dict[str, Dict[str, List[str]]] = {}

    def _ensure_demo_file(self):
        """데모 악보 요청 시 캐시 폴더에 기본 악보가 없으면 복사"""
        cache_opt = os.path.join(self.cache_dir, "demo_opt.musicxml")
        cache_raw = os.path.join(self.cache_dir, "demo.musicxml")
        if not os.path.exists(cache_opt) and not os.path.exists(cache_raw):
            default_src = os.path.join(self.base_dir, "static", "default.musicxml")
            if os.path.exists(default_src):
                shutil.copy2(default_src, cache_raw)
                shutil.copy2(default_src, cache_opt)

    def preprocess_image(self, image_bytes: bytes, filename: str) -> Dict[str, Any]:
        """[1단계] 업로드된 악보 이미지(또는 PDF 첫 페이지)를 전처리합니다."""
        if filename.lower().endswith(".pdf"):
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(stream=image_bytes, filetype="pdf")
                if len(doc) > 0:
                    page = doc.load_page(0)
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    image_bytes = pix.tobytes("png")
                doc.close()
            except Exception as e:
                raise RuntimeError(f"PDF 파일 변환 실패: {str(e)}")

        file_hash = hashlib.sha256(image_bytes).hexdigest()
        cache_img_path = os.path.join(self.cache_dir, f"{file_hash}.png")

        optimizer = SheetMusicOptimizer(target_width=1800)
        optimized_image_bytes = optimizer.optimize(image_bytes)
        with open(cache_img_path, "wb") as f:
            f.write(optimized_image_bytes)

        return {
            "file_hash": file_hash,
            "filename": filename,
            "image_url": f"/api/cache/{file_hash}.png"
        }

    def start_extract_job(self, file_hash: str, filename: str, mode: str = "fast") -> str:
        """[2단계] 비동기 OMR 추출 잡(Job)을 등록하고 백그라운드 스레드로 실행합니다."""
        job_id = str(uuid.uuid4())
        with self._lock:
            self.jobs[job_id] = {
                "job_id": job_id,
                "file_hash": file_hash,
                "filename": filename,
                "mode": mode,
                "status": "pending",
                "percent": 0,
                "message": "OMR 작업 대기 중...",
                "cancel_flag": False,
                "error": None,
                "start_time": time.time()
            }

        worker_thread = threading.Thread(
            target=self._run_extract_worker,
            args=(job_id, file_hash, filename, mode),
            daemon=True
        )
        worker_thread.start()
        return job_id

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """잡의 현재 진행률 및 상태를 반환합니다."""
        with self._lock:
            if job_id not in self.jobs:
                raise KeyError(f"존재하지 않는 작업 ID: {job_id}")
            return dict(self.jobs[job_id])

    def cancel_job(self, job_id: str) -> bool:
        """진행 중인 OMR 잡을 즉시 중단하고 프로세스를 종료합니다."""
        with self._lock:
            if job_id not in self.jobs:
                return False
            self.jobs[job_id]["cancel_flag"] = True
            self.jobs[job_id]["status"] = "cancelled"
            self.jobs[job_id]["message"] = "사용자에 의해 취소되었습니다."

        if job_id in self.job_processes:
            try:
                proc = self.job_processes[job_id]
                if proc.poll() is None:
                    proc.terminate()
                    time.sleep(0.2)
                    if proc.poll() is None:
                        proc.kill()
            except Exception as e:
                print(f"[Cancel Error] 프로세스 강제 종료 중 예외: {e}")
        return True

    def _run_extract_worker(self, job_id: str, file_hash: str, filename: str, mode: str):
        """백그라운드 스레드에서 oemer 엔진을 호출하고 상태를 갱신합니다."""
        def progress_cb(msg: str, percent: int):
            with self._lock:
                if job_id in self.jobs:
                    self.jobs[job_id]["percent"] = percent
                    self.jobs[job_id]["message"] = msg

        def cancel_check_cb() -> bool:
            with self._lock:
                return self.jobs.get(job_id, {}).get("cancel_flag", False)

        try:
            with self._lock:
                self.jobs[job_id]["status"] = "running"
                self.jobs[job_id]["percent"] = 5
                self.jobs[job_id]["message"] = "OMR 엔진 초기화 중..."

            cache_img_path = os.path.join(self.cache_dir, f"{file_hash}.png")
            if not os.path.exists(cache_img_path):
                raise FileNotFoundError("전처리된 이미지가 캐시에 존재하지 않습니다.")

            with open(cache_img_path, "rb") as f:
                img_bytes = f.read()

            xml_filepath, temp_work_dir = self._run_oemer(
                image_bytes=img_bytes,
                filename=filename,
                mode=mode,
                job_id=job_id,
                progress_callback=progress_cb,
                cancel_check_callback=cancel_check_cb
            )

            cache_xml_path = os.path.join(self.cache_dir, f"{file_hash}.musicxml")
            shutil.copy2(xml_filepath, cache_xml_path)
            self._cleanup_temp_file(temp_work_dir)

            with self._lock:
                self.jobs[job_id]["status"] = "completed"
                self.jobs[job_id]["percent"] = 100
                self.jobs[job_id]["message"] = "MusicXML 추출 완료!"

        except Exception as e:
            with self._lock:
                if self.jobs.get(job_id, {}).get("cancel_flag", False):
                    self.jobs[job_id]["status"] = "cancelled"
                    self.jobs[job_id]["message"] = "사용자에 의해 취소됨"
                else:
                    self.jobs[job_id]["status"] = "failed"
                    self.jobs[job_id]["error"] = str(e)
                    self.jobs[job_id]["message"] = f"추출 실패: {str(e)}"
        finally:
            with self._lock:
                if job_id in self.job_processes:
                    del self.job_processes[job_id]

    def optimize_xml(self, file_hash: str) -> bool:
        """[3단계] 추출된 MusicXML의 노이즈 제거 및 음악 규칙 교정을 수행합니다."""
        if file_hash == "demo":
            self._ensure_demo_file()

        cache_xml_path = os.path.join(self.cache_dir, f"{file_hash}.musicxml")
        cache_opt_xml_path = os.path.join(self.cache_dir, f"{file_hash}_opt.musicxml")

        if not os.path.exists(cache_xml_path) and os.path.exists(cache_opt_xml_path):
            shutil.copy2(cache_opt_xml_path, cache_xml_path)

        if not os.path.exists(cache_xml_path):
            raise FileNotFoundError(f"원본 MusicXML({file_hash}) 파일을 찾을 수 없습니다.")

        score = self._load_musicxml(cache_xml_path)
        if not score:
            shutil.copy2(cache_xml_path, cache_opt_xml_path)
            return True

        try:
            corrector = ScoreCorrector()
            score = corrector.run_all(score)
            score.write("musicxml", fp=cache_opt_xml_path)
        except Exception as e:
            print(f"[Optimizer Warning] 교정 중 예외 발생, 원본 유지: {e}")
            shutil.copy2(cache_xml_path, cache_opt_xml_path)

        # 초기 스냅샷을 Undo 히스토리에 저장
        self._push_snapshot(file_hash, cache_opt_xml_path)
        return True

    def render_audio(self, file_hash: str) -> Dict[str, Any]:
        """[4단계] 악보 메타데이터를 분석하고 재생/다운로드용 MIDI 파일을 생성합니다."""
        if file_hash == "demo":
            self._ensure_demo_file()

        cache_opt_xml_path = os.path.join(self.cache_dir, f"{file_hash}_opt.musicxml")
        cache_xml_path = os.path.join(self.cache_dir, f"{file_hash}.musicxml")

        target_xml = cache_opt_xml_path if os.path.exists(cache_opt_xml_path) else cache_xml_path
        if not os.path.exists(target_xml):
            raise FileNotFoundError(f"렌더링할 MusicXML 파일을 찾을 수 없습니다: {file_hash}")

        score = self._load_musicxml(target_xml)
        if not score:
            raise RuntimeError("MusicXML 파싱에 실패했습니다.")

        output_midi_path = os.path.join(self.cache_dir, f"{file_hash}.mid")
        try:
            score.write("midi", fp=output_midi_path)
        except Exception as e:
            print(f"[MIDI Export Warning] MIDI 생성 실패: {e}")

        analysis_result = self._analyze_score(score)

        return {
            "status": "success",
            "analysis": analysis_result,
            "midi_url": f"/api/cache/{file_hash}.mid",
            "xml_url": f"/api/cache/{os.path.basename(target_xml)}",
            "hash": file_hash
        }

    def edit_note_in_xml(
        self,
        file_hash: str,
        measure_number: int,
        note_index: Optional[int] = None,
        note_offset: Optional[float] = None,
        new_pitch: Optional[str] = None,
        new_duration: Optional[float] = None,
        part_index: int = 0,
        is_chord_add: bool = False,
        action: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        [정밀 타겟팅 수동 교정 알고리즘]
        - 보표 선택(part_index), 마디(measure_number), 마디 내 박자 위치(note_offset) 또는 인덱스(note_index)로 타겟팅.
        - 피치 변경, 쉼표(REST) 변환, 화음(Chord) 추가, 음길이(Duration) 변경, 반음/옥타브 전조 지원.
        - Undo/Redo 스택에 수정 전 상태 자동 기록.
        """
        if file_hash == "demo":
            self._ensure_demo_file()

        cache_opt_xml_path = os.path.join(self.cache_dir, f"{file_hash}_opt.musicxml")
        cache_xml_path = os.path.join(self.cache_dir, f"{file_hash}.musicxml")
        target_xml = cache_opt_xml_path if os.path.exists(cache_opt_xml_path) else cache_xml_path

        if not os.path.exists(target_xml):
            raise ValueError("MusicXML 파일을 찾을 수 없습니다.")

        # 수정 전 스냅샷 백업
        self._push_snapshot(file_hash, target_xml)

        score = m21.converter.parse(target_xml)
        if not score.parts:
            raise ValueError("악보에 파트가 존재하지 않습니다.")

        # 안전한 보표 선택 (단일 선율일 경우 0번으로 폴백)
        safe_part_idx = part_index if 0 <= part_index < len(score.parts) else 0
        part = score.parts[safe_part_idx]

        measure = part.measure(measure_number)
        if not measure:
            # 0부터 시작하거나 누락된 마디 번호 처리
            measures_list = list(part.getElementsByClass(m21.stream.Measure))
            if 1 <= measure_number <= len(measures_list):
                measure = measures_list[measure_number - 1]
            else:
                raise ValueError(f"{measure_number}번 마디를 찾을 수 없습니다.")

        notes_and_rests = list(measure.notesAndRests)
        if not notes_and_rests:
            raise ValueError(f"{measure_number}번 마디에 음표나 쉼표가 없습니다.")

        # 정밀 타겟팅: note_offset이 지정되어 있으면 오프셋이 가장 가까운 원소 탐색
        target_element = None
        if note_offset is not None:
            best_diff = 999999.0
            for el in notes_and_rests:
                diff = abs(float(el.offset) - float(note_offset))
                if diff < best_diff:
                    best_diff = diff
                    target_element = el
            # 오차 허용 범위(0.25 beat 이하)가 아닐 때 인덱스 폴백
            if best_diff > 0.5 and note_index is not None:
                target_element = None

        if target_element is None:
            safe_idx = 0
            if note_index is not None:
                safe_idx = max(0, min(note_index, len(notes_and_rests) - 1))
            target_element = notes_and_rests[safe_idx]

        old_duration = float(target_element.quarterLength)
        cur_duration = new_duration if (new_duration and new_duration > 0) else old_duration

        # 1. 액션별 분기 (삭제, 전조 등)
        if action == "delete" or (new_pitch and new_pitch.upper() == "REST"):
            if not target_element.isRest:
                new_rest = m21.note.Rest()
                new_rest.quarterLength = cur_duration
                measure.replace(target_element, new_rest)
                target_element = new_rest
        elif action in ["semitone_up", "semitone_down", "octave_up", "octave_down"]:
            step_map = {
                "semitone_up": 1,
                "semitone_down": -1,
                "octave_up": 12,
                "octave_down": -12
            }
            semitones = step_map[action]
            interval_obj = m21.interval.Interval(semitones)
            if target_element.isNote:
                target_element.pitch.transpose(interval_obj, inPlace=True)
            elif target_element.isChord:
                for p in target_element.pitches:
                    p.transpose(interval_obj, inPlace=True)
        elif new_pitch:
            new_pitch_clean = new_pitch.strip()
            try:
                if target_element.isRest:
                    # 쉼표를 음표로 전환
                    new_n = m21.note.Note(new_pitch_clean)
                    new_n.quarterLength = cur_duration
                    measure.replace(target_element, new_n)
                    target_element = new_n
                elif is_chord_add:
                    # Shift + 건반: 화음 쌓기
                    new_p = m21.pitch.Pitch(new_pitch_clean)
                    if target_element.isNote:
                        chord_notes = [target_element.pitch, new_p]
                        new_chord = m21.chord.Chord(chord_notes)
                        new_chord.quarterLength = cur_duration
                        measure.replace(target_element, new_chord)
                        target_element = new_chord
                    elif target_element.isChord:
                        existing = [p.nameWithOctave for p in target_element.pitches]
                        if new_p.nameWithOctave not in existing:
                            target_element.add(new_p)
                else:
                    # 일반 피치 교체
                    if target_element.isNote:
                        target_element.pitch = m21.pitch.Pitch(new_pitch_clean)
                    elif target_element.isChord:
                        # 화음의 최상위/첫 번째 음정을 새 피치로 변환하거나 단일 음표로 정규화
                        old_p = target_element.pitches[0]
                        new_p = m21.pitch.Pitch(new_pitch_clean)
                        interval_diff = m21.interval.Interval(old_p, new_p)
                        for p in target_element.pitches:
                            p.transpose(interval_diff, inPlace=True)
            except m21.pitch.PitchException:
                raise ValueError(f"'{new_pitch}'는 올바른 음정 형식이 아닙니다 (예: C4, F#5, Bb3).")

        # 2. 박자(Duration) 변경 시 마디 채움 및 정규화
        if new_duration and new_duration > 0 and abs(new_duration - old_duration) > 1e-4:
            diff = new_duration - old_duration
            target_element.quarterLength = new_duration
            if diff < 0:
                # 박자가 줄어들었을 경우 남는 공간에 보정 쉼표 삽입
                filler = m21.note.Rest()
                filler.quarterLength = round(abs(diff), 4)
                measure.insert(float(target_element.offset) + new_duration, filler)
            else:
                # 박자가 늘어났을 경우 마디 넘침 정규화
                part.makeMeasures(inPlace=True)
                part.makeTies(inPlace=True)

        # 수정 결과 저장
        score.write("musicxml", fp=cache_opt_xml_path)
        try:
            score.write("midi", fp=os.path.join(self.cache_dir, f"{file_hash}.mid"))
        except Exception:
            pass

        return {
            "status": "success",
            "message": "음표가 성공적으로 수정되었습니다.",
            "midi_url": f"/api/cache/{file_hash}.mid",
            "analysis": self._analyze_score(score)
        }

    def _push_snapshot(self, file_hash: str, xml_path: str):
        """현재 XML 내용을 Undo 스택에 저장 (최대 20개)"""
        try:
            with open(xml_path, "r", encoding="utf-8") as f:
                content = f.read()
            if file_hash not in self.history:
                self.history[file_hash] = {"undo": [], "redo": []}
            undo_list = self.history[file_hash]["undo"]
            if not undo_list or undo_list[-1] != content:
                undo_list.append(content)
                if len(undo_list) > 20:
                    undo_list.pop(0)
            # 새 변경 발생 시 Redo 스택 초기화
            self.history[file_hash]["redo"].clear()
        except Exception as e:
            print(f"[Snapshot Warning] 스냅샷 저장 실패: {e}")

    def undo(self, file_hash: str) -> Optional[str]:
        """Undo: 직전 스냅샷으로 복원"""
        if file_hash not in self.history or not self.history[file_hash]["undo"]:
            return None

        cache_opt_xml_path = os.path.join(self.cache_dir, f"{file_hash}_opt.musicxml")
        current_disk_content = ""
        if os.path.exists(cache_opt_xml_path):
            with open(cache_opt_xml_path, "r", encoding="utf-8") as f:
                current_disk_content = f.read()

        # 직전 저장 스냅샷 꺼내기
        prev_xml = self.history[file_hash]["undo"].pop()
        if current_disk_content and current_disk_content != prev_xml:
            self.history[file_hash]["redo"].append(current_disk_content)

        with open(cache_opt_xml_path, "w", encoding="utf-8") as f:
            f.write(prev_xml)
        self._refresh_midi(file_hash, cache_opt_xml_path)
        return prev_xml

    def redo(self, file_hash: str) -> Optional[str]:
        """Redo: 취소했던 스냅샷 복원"""
        if file_hash not in self.history or not self.history[file_hash]["redo"]:
            return None

        cache_opt_xml_path = os.path.join(self.cache_dir, f"{file_hash}_opt.musicxml")
        current_disk_content = ""
        if os.path.exists(cache_opt_xml_path):
            with open(cache_opt_xml_path, "r", encoding="utf-8") as f:
                current_disk_content = f.read()

        next_xml = self.history[file_hash]["redo"].pop()
        if current_disk_content and current_disk_content != next_xml:
            self.history[file_hash]["undo"].append(current_disk_content)

        with open(cache_opt_xml_path, "w", encoding="utf-8") as f:
            f.write(next_xml)
        self._refresh_midi(file_hash, cache_opt_xml_path)
        return next_xml

    def _refresh_midi(self, file_hash: str, xml_path: str):
        try:
            score = self._load_musicxml(xml_path)
            if score:
                score.write("midi", fp=os.path.join(self.cache_dir, f"{file_hash}.mid"))
        except Exception:
            pass

    def _run_oemer(
        self,
        image_bytes: bytes,
        filename: str,
        mode: str = "fast",
        job_id: Optional[str] = None,
        progress_callback=None,
        cancel_check_callback=None
    ) -> Tuple[str, str]:
        """oemer 엔진을 서브프로세스로 실행하여 MusicXML을 추출합니다."""
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(image_bytes))
            max_dim = 1800 if mode == "deep" else 1350
            w, h = img.size
            if max(w, h) > max_dim:
                if progress_callback:
                    progress_callback(f"이미지 해상도 정규화({max_dim}px)...", 8)
                scale = max_dim / float(max(w, h))
                img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
            img = img.convert("RGB")
            out_io = io.BytesIO()
            img.save(out_io, format="PNG")
            image_bytes = out_io.getvalue()
        except Exception as e:
            print(f"[OMR Prep Warning] 이미지 리사이즈 경고: {e}")

        temp_work_dir = tempfile.mkdtemp(prefix="omr_proc_")
        tmp_img_path = os.path.join(temp_work_dir, "input_sheet.png")
        with open(tmp_img_path, "wb") as f:
            f.write(image_bytes)

        process = None
        try:
            if progress_callback:
                progress_callback("AI OMR 신경망 모델 로딩 중...", 12)

            safe_tmp_img_path = tmp_img_path.replace("\\", "/")
            safe_temp_work_dir = temp_work_dir.replace("\\", "/")
            without_deskew_flag = "True" if mode == "fast" else "False"

            wrapper_path = os.path.join(temp_work_dir, "fast_oemer.py")
            with open(wrapper_path, "w", encoding="utf-8") as fw:
                fw.write(f"""import os
import sys
import io
import logging
import cv2

# Windows cp949 방지
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    try:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

cv2.imwrite = lambda *args, **kwargs: True

from oemer.ete import extract, clear_data

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

class Args:
    img_path = "{safe_tmp_img_path}"
    output_path = "{safe_temp_work_dir}"
    use_tf = False
    save_cache = False
    without_deskew = {without_deskew_flag}

try:
    clear_data()
    extract(Args())
except Exception as e:
    err_msg = str(e).encode('utf-8', errors='replace').decode('utf-8', errors='replace')
    try:
        print(f"ERROR: {{err_msg}}", flush=True)
    except Exception:
        pass
    sys.exit(1)
""")
            cmd = [sys.executable, wrapper_path]
            max_threads = str(max(1, multiprocessing.cpu_count() - 1))

            env = os.environ.copy()
            env["OMP_NUM_THREADS"] = max_threads
            env["MKL_NUM_THREADS"] = max_threads
            env["OPENBLAS_NUM_THREADS"] = max_threads
            env["VECLIB_MAXIMUM_THREADS"] = max_threads
            env["NUMEXPR_NUM_THREADS"] = max_threads
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            env["PYTHONLEGACYWINDOWSSTDIO"] = "0"

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env
            )

            if job_id:
                with self._lock:
                    self.job_processes[job_id] = process

            current_percent = 15
            while True:
                if cancel_check_callback and cancel_check_callback():
                    process.terminate()
                    raise RuntimeError("사용자에 의해 분석이 취소되었습니다.")

                line_bytes = process.stdout.readline()
                if not line_bytes and process.poll() is not None:
                    break
                if line_bytes:
                    line_str = line_bytes.decode("utf-8", errors="replace").strip()
                    if not line_str:
                        continue
                    try:
                        print(f"[oemer] {line_str}", flush=True)
                    except Exception:
                        pass
                    if progress_callback:
                        l_lower = line_str.lower()
                        if "staff" in l_lower:
                            current_percent = max(current_percent, 25)
                        elif "dewarp" in l_lower or "deskew" in l_lower:
                            current_percent = max(current_percent, 35)
                        elif "clef" in l_lower or "key" in l_lower:
                            current_percent = max(current_percent, 50)
                        elif "note" in l_lower or "symbol" in l_lower:
                            current_percent = max(current_percent, 70)
                        elif "build" in l_lower or "export" in l_lower or "musicxml" in l_lower:
                            current_percent = max(current_percent, 90)
                        progress_callback(f"oemer > {line_str}", current_percent)

            return_code = process.wait(timeout=600)
            if return_code != 0:
                raise RuntimeError(f"oemer 엔진 실행 오류 (반환 코드: {return_code})")

            expected_xml_path = os.path.join(temp_work_dir, "input_sheet.musicxml")
            if os.path.exists(expected_xml_path):
                return expected_xml_path, temp_work_dir

            xml_files = [os.path.join(temp_work_dir, f) for f in os.listdir(temp_work_dir) if f.endswith(".musicxml")]
            if xml_files:
                return xml_files[0], temp_work_dir

            raise RuntimeError("MusicXML 파일이 출력 디렉토리에 생성되지 않았습니다.")

        except subprocess.TimeoutExpired:
            if process:
                process.kill()
            raise RuntimeError("악보 OMR 분석 시간 초과 (10분)")
        except Exception as e:
            if process and process.poll() is None:
                process.kill()
            raise RuntimeError(f"oemer 분석 실패: {str(e)}")

    def _load_musicxml(self, filepath: str) -> Optional[m21.stream.Score]:
        try:
            return m21.converter.parse(filepath, format="musicxml")
        except Exception as e:
            print(f"[music21 파싱 에러]: {str(e)}")
            return None

    def _analyze_score(self, score: m21.stream.Score) -> Dict[str, Any]:
        """Score 객체에서 조표, 박자표, 마디 수, 음표 수, 보표 정보를 추출합니다."""
        key_str = "C major"
        try:
            ks = score.recurse().getElementsByClass(m21.key.KeySignature)
            if ks:
                key_str = str(ks[0].asKey().name)
            else:
                key = score.analyze("key")
                key_str = f"{key.tonic.name} {key.mode}"
        except Exception:
            pass

        time_sig_str = "4/4"
        try:
            ts = score.recurse().getElementsByClass(m21.meter.TimeSignature)
            if ts:
                time_sig_str = f"{ts[0].numerator}/{ts[0].denominator}"
        except Exception:
            pass

        measure_count = 0
        part_count = len(score.parts) if score.parts else 1
        try:
            if score.parts:
                measure_count = len(score.parts[0].getElementsByClass(m21.stream.Measure))
            else:
                measure_count = len(score.getElementsByClass(m21.stream.Measure))
        except Exception:
            pass

        total_notes = 0
        try:
            total_notes = len(score.recurse().getElementsByClass([m21.note.Note, m21.chord.Chord]))
        except Exception:
            pass

        return {
            "key_signature": key_str,
            "time_signature": time_sig_str,
            "total_measures": measure_count,
            "total_notes": total_notes,
            "total_parts": part_count
        }

    def _cleanup_temp_file(self, filepath: str):
        if filepath and os.path.exists(filepath):
            try:
                if os.path.isdir(filepath):
                    shutil.rmtree(filepath, ignore_errors=True)
                else:
                    os.remove(filepath)
            except Exception:
                pass
