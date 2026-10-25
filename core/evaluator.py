"""
core/evaluator.py
AI-STEAM User Performance Assessment & AI Feedback Engine
Evaluates user musical performances (Audio WAV, MIDI, or Live Events) against Ground Truth Sheet Music.
"""

import os
import sys
import math
import wave
import struct
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
import music21 as m21


class PerformanceEvaluator:
    """
    사용자의 연주(오디오 WAV, MIDI, 실시간 건반 이벤트)를
    원본 악보(MusicXML)와 비교하여 음정 정확도, 리듬/템포 정확도,
    완성도 및 마디별 상세 피드백을 산출하는 AI 음악 코칭 평가 엔진.
    """

    def __init__(self, cache_dir: str = "omr_cache"):
        self.cache_dir = cache_dir

    # =========================================================================
    # 1. 원본 악보(MusicXML)에서 기대 음표 시퀀스 추출
    # =========================================================================
    def extract_expected_notes_from_xml(self, xml_path: str) -> List[Dict[str, Any]]:
        """
        MusicXML 악보를 파싱하여 기대되는 순서별 음표 목록을 추출합니다.
        반환: [{"pitch": "E4", "midi": 64, "measure": 1, "offset": 0.0, "duration": 1.0, "part": 0}, ...]
        """
        if not os.path.exists(xml_path):
            raise FileNotFoundError(f"악보 파일을 찾을 수 없습니다: {xml_path}")

        score = m21.converter.parse(xml_path)
        expected_notes: List[Dict[str, Any]] = []

        # 모든 파트 순회 (오른손/주선율 우선)
        for part_idx, part in enumerate(score.parts):
            accumulated_beats = 0.0
            for measure in part.getElementsByClass(m21.stream.Measure):
                measure_num = measure.number or 1
                for element in measure.notesAndRests:
                    if element.isNote:
                        pitch_str = element.pitch.nameWithOctave
                        midi_val = int(element.pitch.midi)
                        dur_beats = float(element.quarterLength)
                        expected_notes.append({
                            "pitch": pitch_str,
                            "midi": midi_val,
                            "measure": measure_num,
                            "offset": accumulated_beats,
                            "duration": dur_beats,
                            "part": part_idx,
                            "is_rest": False
                        })
                        accumulated_beats += dur_beats
                    elif element.isChord:
                        # 화음의 경우 주선율(최상단 음) 및 구성음 추출
                        top_note = element.root() or element.notes[-1]
                        pitch_str = top_note.nameWithOctave
                        midi_val = int(top_note.midi)
                        dur_beats = float(element.quarterLength)
                        expected_notes.append({
                            "pitch": pitch_str,
                            "midi": midi_val,
                            "measure": measure_num,
                            "offset": accumulated_beats,
                            "duration": dur_beats,
                            "part": part_idx,
                            "is_rest": False
                        })
                        accumulated_beats += dur_beats
                    elif element.isRest:
                        dur_beats = float(element.quarterLength)
                        accumulated_beats += dur_beats

        # 오프셋 및 파트 기준으로 정렬
        expected_notes.sort(key=lambda x: (x["offset"], x["part"]))
        return expected_notes

    # =========================================================================
    # 2. 사용자 연주 MIDI 파싱
    # =========================================================================
    def extract_notes_from_midi(self, midi_path: str) -> List[Dict[str, Any]]:
        """
        사용자가 연주한 MIDI 파일을 파싱하여 음표 목록을 추출합니다.
        반환: [{"pitch": "E4", "midi": 64, "time": 0.52, "duration": 0.48, "velocity": 85}, ...]
        """
        if not os.path.exists(midi_path):
            raise FileNotFoundError(f"MIDI 파일을 찾을 수 없습니다: {midi_path}")

        midi_stream = m21.converter.parse(midi_path)
        played_notes: List[Dict[str, Any]] = []

        for element in midi_stream.recurse().notes:
            if element.isNote:
                played_notes.append({
                    "pitch": element.pitch.nameWithOctave,
                    "midi": int(element.pitch.midi),
                    "time": float(element.offset),
                    "duration": float(element.quarterLength),
                    "velocity": getattr(element.volume, "velocity", 80) or 80
                })
            elif element.isChord:
                for n in element.notes:
                    played_notes.append({
                        "pitch": n.pitch.nameWithOctave,
                        "midi": int(n.pitch.midi),
                        "time": float(element.offset),
                        "duration": float(element.quarterLength),
                        "velocity": getattr(n.volume, "velocity", 80) or 80
                    })

        played_notes.sort(key=lambda x: x["time"])
        return played_notes

    # =========================================================================
    # 3. 사용자 연주 오디오(WAV) 피치 & 온셋 분석 (Zero-dependency NumPy/Wave)
    # =========================================================================
    def extract_notes_from_wav(self, wav_path: str) -> List[Dict[str, Any]]:
        """
        사용자가 녹음한 WAV 오디오 파일로부터 온셋(타건 시점) 및 피치(음높이)를 추정합니다.
        외부 무거운 라이브러리 없이 순수 numpy와 wave 모듈을 활용하여 512MB RAM 환경에서도
        초고속(<100ms)으로 안전하게 구동됩니다.
        """
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"오디오 파일을 찾을 수 없습니다: {wav_path}")

        with wave.open(wav_path, "rb") as wf:
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            raw_data = wf.readframes(n_frames)

        if n_frames == 0 or framerate == 0:
            return []

        # 16-bit PCM 정규화
        if sample_width == 2:
            samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
        elif sample_width == 1:
            samples = (np.frombuffer(raw_data, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        elif sample_width == 4:
            samples = np.frombuffer(raw_data, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0

        # 스테레오를 모노로 변환
        if n_channels > 1:
            samples = samples.reshape(-1, n_channels).mean(axis=1)

        # 1. 온셋 검출 (Short-Time Energy Envelope)
        hop_size = int(framerate * 0.02)  # 20ms 홉
        frame_size = int(framerate * 0.04) # 40ms 윈도우
        if len(samples) < frame_size:
            return []

        num_frames = (len(samples) - frame_size) // hop_size
        energy = np.zeros(num_frames, dtype=np.float32)
        for i in range(num_frames):
            start = i * hop_size
            window = samples[start:start + frame_size]
            energy[i] = np.sum(window ** 2)

        # 에너지 미분 및 피크 픽킹
        energy_diff = np.diff(energy)
        energy_diff = np.maximum(0, energy_diff)
        threshold = np.mean(energy_diff) + 0.5 * np.std(energy_diff)

        onset_indices = []
        min_distance_frames = int(0.12 / 0.02)  # 최소 120ms 간격 (동일 음표 중복 방지)
        last_onset = -min_distance_frames

        for i in range(1, len(energy_diff) - 1):
            if energy_diff[i] > threshold and energy_diff[i] > energy_diff[i - 1] and energy_diff[i] >= energy_diff[i + 1]:
                if i - last_onset >= min_distance_frames:
                    onset_indices.append(i)
                    last_onset = i

        # 시작 지점(frame 0)부터 소리가 출력되는 경우 최초 온셋으로 등록
        if num_frames > 0 and energy[0] > np.mean(energy) * 0.15:
            if not onset_indices or onset_indices[0] > min_distance_frames:
                onset_indices.insert(0, 0)

        # 만약 온셋이 검출되지 않았으나 소리가 있다면 균등 샘플링
        if not onset_indices and np.max(np.abs(samples)) > 0.05:
            onset_indices = [0]

        # 2. 각 온셋 구간에서 주파수(f0) 및 MIDI 피치 추출 (Normalized Autocorrelation)
        detected_notes: List[Dict[str, Any]] = []
        min_pitch_hz = 65.0   # C2
        max_pitch_hz = 1050.0 # C6

        min_lag = max(1, int(framerate / max_pitch_hz))
        max_lag = min(frame_size * 2, int(framerate / min_pitch_hz))

        analysis_len = int(framerate * 0.08) # 80ms 분석창

        for idx, onset_frame in enumerate(onset_indices):
            sample_start = onset_frame * hop_size
            sample_end = sample_start + analysis_len
            if sample_end > len(samples):
                break

            seg = samples[sample_start:sample_end]
            # DC 오프셋 제거 및 해밍 윈도우
            seg = seg - np.mean(seg)
            seg = seg * np.hamming(len(seg))

            # 자기상관함수 (Autocorrelation)
            corr = np.correlate(seg, seg, mode="full")
            corr = corr[len(corr) // 2:]

            # 유효 피치 범위 내 최대 피크 탐색
            if len(corr) > max_lag:
                valid_corr = corr[min_lag:max_lag]
                if len(valid_corr) > 0 and np.max(valid_corr) > 0:
                    peak_lag = min_lag + int(np.argmax(valid_corr))
                    if peak_lag > 0:
                        f0 = float(framerate) / peak_lag
                        if min_pitch_hz <= f0 <= max_pitch_hz:
                            midi_val = int(round(69 + 12 * math.log2(f0 / 440.0)))
                            midi_val = max(21, min(108, midi_val))
                            
                            # MIDI 번호를 음이름으로 변환
                            note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
                            step = note_names[midi_val % 12]
                            octave = (midi_val // 12) - 1
                            pitch_name = f"{step}{octave}"

                            onset_time = round(float(sample_start) / framerate, 3)
                            
                            # 다음 온셋까지의 거리로 지속시간 추정
                            if idx + 1 < len(onset_indices):
                                dur = round((onset_indices[idx + 1] - onset_frame) * 0.02, 3)
                            else:
                                dur = 0.5

                            detected_notes.append({
                                "pitch": pitch_name,
                                "midi": midi_val,
                                "time": onset_time,
                                "duration": dur,
                                "velocity": 85
                            })

        return detected_notes

    # =========================================================================
    # 4. 종합 연주 평가 알고리즘 (Needleman-Wunsch Dynamic Alignment)
    # =========================================================================
    def evaluate_performance(
        self,
        expected_notes: List[Dict[str, Any]],
        played_notes: List[Dict[str, Any]],
        target_bpm: float = 100.0
    ) -> Dict[str, Any]:
        """
        기대 음표 시퀀스와 실제 연주 시퀀스를 Needleman-Wunsch 글로벌 서열 정렬하여
        음정 정확도, 박자 정확도, 누락음, 불필요한 음, 종합 점수 및 마디별 피드백을 산출합니다.
        """
        if not expected_notes:
            return {
                "total_score": 0,
                "grade": "D",
                "pitch_score": 0.0,
                "rhythm_score": 0.0,
                "completeness": 0.0,
                "summary": "악보에 평가할 음표가 존재하지 않습니다.",
                "details": [],
                "statistics": {"correct": 0, "pitch_error": 0, "timing_error": 0, "missed": 0, "extra": 0}
            }

        if not played_notes:
            details = []
            for n in expected_notes:
                details.append({
                    "measure": n["measure"],
                    "expected_pitch": n["pitch"],
                    "played_pitch": "-",
                    "status": "missed",
                    "feedback": f"{n['measure']}마디: 음표({n['pitch']})가 연주되지 않았습니다 (누락)",
                    "expected_offset": n["offset"],
                    "played_time": None
                })
            return {
                "total_score": 0,
                "grade": "D",
                "pitch_score": 0.0,
                "rhythm_score": 0.0,
                "completeness": 0.0,
                "summary": "연주된 음표가 감지되지 않았습니다. 마이크 입력 또는 연주 파일 상태를 확인해 주세요.",
                "details": details,
                "statistics": {"correct": 0, "pitch_error": 0, "timing_error": 0, "missed": len(expected_notes), "extra": 0}
            }

        N = len(expected_notes)
        M = len(played_notes)

        # 1. Needleman-Wunsch 서열 정렬 DP 테이블 생성
        # D[i][j]: expected[0..i-1]과 played[0..j-1] 간의 최적 정렬 점수
        DP = np.zeros((N + 1, M + 1), dtype=np.float32)
        GAP_PENALTY = -1.2

        for i in range(N + 1):
            DP[i][0] = i * GAP_PENALTY
        for j in range(M + 1):
            DP[0][j] = j * GAP_PENALTY

        def match_score(exp: Dict[str, Any], ply: Dict[str, Any]) -> float:
            exp_midi = exp["midi"]
            ply_midi = ply["midi"]
            if exp_midi == ply_midi:
                return 2.5  # 완벽 일치
            elif abs(exp_midi - ply_midi) == 1:
                return 0.8  # 반음 오차
            elif abs(exp_midi - ply_midi) == 12:
                return 1.2  # 옥타브 오차
            else:
                return -1.0 # 오음

        for i in range(1, N + 1):
            for j in range(1, M + 1):
                sim = match_score(expected_notes[i - 1], played_notes[j - 1])
                match_val = DP[i - 1][j - 1] + sim
                del_val = DP[i - 1][j] + GAP_PENALTY
                ins_val = DP[i][j - 1] + GAP_PENALTY
                DP[i][j] = max(match_val, del_val, ins_val)

        # 2. 역추적(Backtracking)으로 정렬 쌍 추출
        aligned_pairs: List[Tuple[Optional[int], Optional[int]]] = []
        i, j = N, M

        while i > 0 or j > 0:
            if i > 0 and j > 0:
                sim = match_score(expected_notes[i - 1], played_notes[j - 1])
                if math.isclose(DP[i][j], DP[i - 1][j - 1] + sim, rel_tol=1e-5):
                    aligned_pairs.append((i - 1, j - 1))
                    i -= 1
                    j -= 1
                    continue
            if i > 0 and math.isclose(DP[i][j], DP[i - 1][j] + GAP_PENALTY, rel_tol=1e-5):
                aligned_pairs.append((i - 1, None))
                i -= 1
            elif j > 0:
                aligned_pairs.append((None, j - 1))
                j -= 1
            else:
                break

        aligned_pairs.reverse()

        # 3. 사용자 연주 템포(BPM) 추정 및 스케일링
        # 기대 비트와 실제 연주 시간(초) 간의 상관관계 계산
        matched_times = []
        matched_offsets = []
        for e_idx, p_idx in aligned_pairs:
            if e_idx is not None and p_idx is not None:
                matched_offsets.append(expected_notes[e_idx]["offset"])
                matched_times.append(played_notes[p_idx]["time"])

        if len(matched_offsets) >= 2 and (matched_offsets[-1] - matched_offsets[0]) > 0:
            delta_beats = matched_offsets[-1] - matched_offsets[0]
            delta_seconds = max(0.1, matched_times[-1] - matched_times[0])
            estimated_bpm = round((delta_beats / delta_seconds) * 60.0, 1)
            seconds_per_beat = delta_seconds / delta_beats
        else:
            estimated_bpm = target_bpm
            seconds_per_beat = 60.0 / target_bpm

        # 4. 세부 평가 지표 산출
        correct_pitch_count = 0
        pitch_error_count = 0
        timing_error_count = 0
        missed_count = 0
        extra_count = 0
        timing_deviations_sec = []

        details: List[Dict[str, Any]] = []

        for e_idx, p_idx in aligned_pairs:
            if e_idx is not None and p_idx is not None:
                exp = expected_notes[e_idx]
                ply = played_notes[p_idx]
                measure_num = exp["measure"]

                is_pitch_match = (exp["midi"] == ply["midi"])
                
                # 기대 시간(초) vs 실제 연주 시간(초)
                expected_sec = exp["offset"] * seconds_per_beat
                played_sec = ply["time"]
                time_diff = abs(played_sec - expected_sec)
                timing_deviations_sec.append(time_diff)

                # 타이밍 판정 기준 (0.35초 이내 양호)
                is_timing_good = (time_diff <= 0.35)

                if is_pitch_match and is_timing_good:
                    status = "correct"
                    feedback = f"{measure_num}마디: 완벽한 음정({exp['pitch']})과 정확한 박자"
                    correct_pitch_count += 1
                elif is_pitch_match and not is_timing_good:
                    status = "timing_error"
                    timing_direction = "빠름" if played_sec < expected_sec else "느림"
                    feedback = f"{measure_num}마디: 음정은 맞았으나 템포가 {timing_direction} ({round(time_diff, 2)}초 편차)"
                    correct_pitch_count += 1
                    timing_error_count += 1
                else:
                    status = "pitch_error"
                    diff_semitone = ply["midi"] - exp["midi"]
                    semitone_str = f"+{diff_semitone}" if diff_semitone > 0 else f"{diff_semitone}"
                    feedback = f"{measure_num}마디: 음정 오류 (기대: {exp['pitch']}, 연주: {ply['pitch']}, {semitone_str}반음)"
                    pitch_error_count += 1

                details.append({
                    "measure": measure_num,
                    "expected_pitch": exp["pitch"],
                    "played_pitch": ply["pitch"],
                    "status": status,
                    "feedback": feedback,
                    "expected_offset": exp["offset"],
                    "played_time": ply["time"],
                    "timing_deviation": round(time_diff, 3)
                })

            elif e_idx is not None and p_idx is None:
                exp = expected_notes[e_idx]
                measure_num = exp["measure"]
                missed_count += 1
                details.append({
                    "measure": measure_num,
                    "expected_pitch": exp["pitch"],
                    "played_pitch": "-",
                    "status": "missed",
                    "feedback": f"{measure_num}마디: 음표({exp['pitch']})가 연주되지 않음 (누락)",
                    "expected_offset": exp["offset"],
                    "played_time": None,
                    "timing_deviation": None
                })

            elif e_idx is None and p_idx is not None:
                ply = played_notes[p_idx]
                extra_count += 1
                details.append({
                    "measure": "-",
                    "expected_pitch": "-",
                    "played_pitch": ply["pitch"],
                    "status": "extra",
                    "feedback": f"불필요한 음표({ply['pitch']})가 추가 연주됨 (잡음/미스타건)",
                    "expected_offset": None,
                    "played_time": ply["time"],
                    "timing_deviation": None
                })

        # 5. 점수 계산 (100점 만점)
        # 음정 점수: (맞춘 음표 수 / 총 기대 음표 수) * 100
        pitch_score = round(max(0.0, min(100.0, (correct_pitch_count / float(N)) * 100.0)), 1)
        
        # 리듬 점수: 평균 타이밍 편차(초) 기반 감점
        avg_deviation = float(np.mean(timing_deviations_sec)) if timing_deviations_sec else 0.5
        rhythm_score = round(max(0.0, min(100.0, 100.0 - (avg_deviation * 85.0))), 1)

        # 완성도: 연주한 음표 비율
        completeness = round(max(0.0, min(100.0, (len(played_notes) / float(N)) * 100.0)), 1)

        # 종합 점수 (가중치: 음정 65%, 리듬 35%, 엑스트라 음표 페널티)
        extra_penalty = min(15.0, extra_count * 2.5)
        raw_total = (pitch_score * 0.65) + (rhythm_score * 0.35) - extra_penalty
        total_score = int(round(max(0.0, min(100.0, raw_total))))

        # 등급 부여
        if total_score >= 95:
            grade = "S"
            grade_title = "마스터 (Virtuoso)"
        elif total_score >= 85:
            grade = "A"
            grade_title = "우수 (Excellent)"
        elif total_score >= 75:
            grade = "B"
            grade_title = "양호 (Good)"
        elif total_score >= 60:
            grade = "C"
            grade_title = "연습 필요 (Fair)"
        else:
            grade = "D"
            grade_title = "기초 단계 (Beginner)"

        # 총평 메시지 생성
        summary_lines = []
        if total_score >= 90:
            summary_lines.append("🎉 환상적인 연주입니다! 음정과 템포 모두 원곡의 감성을 훌륭히 재현했습니다.")
        elif total_score >= 75:
            summary_lines.append("👏 전반적으로 안정적인 연주입니다. 일부 마디의 음정 및 템포를 조금만 더 가다듬으면 완벽해집니다.")
        else:
            summary_lines.append("💪 좋은 시도입니다! 틀리거나 누락된 마디를 악보에서 천천히 부분 연습해 보세요.")

        if pitch_error_count > 0:
            summary_lines.append(f"• 음정 오차가 총 {pitch_error_count}개 발견되었습니다. 조표와 임시표를 다시 확인하세요.")
        if timing_error_count > 0:
            summary_lines.append(f"• 템포가 흔들린 마디가 {timing_error_count}개 있습니다. 메트로놈을 켜고 연습을 권장합니다.")
        if missed_count > 0:
            summary_lines.append(f"• 누락된 음표가 {missed_count}개 있습니다.")
        summary_lines.append(f"• 추정 연주 템포: 약 {estimated_bpm} BPM (목표 템포: {target_bpm} BPM)")

        summary_text = "\n".join(summary_lines)

        return {
            "total_score": total_score,
            "grade": grade,
            "grade_title": grade_title,
            "pitch_score": pitch_score,
            "rhythm_score": rhythm_score,
            "completeness": completeness,
            "estimated_bpm": estimated_bpm,
            "target_bpm": target_bpm,
            "summary": summary_text,
            "details": details,
            "statistics": {
                "total_expected": N,
                "total_played": M,
                "correct": correct_pitch_count,
                "pitch_error": pitch_error_count,
                "timing_error": timing_error_count,
                "missed": missed_count,
                "extra": extra_count
            }
        }


# 모듈 레벨 싱글톤 인스턴스
evaluator = PerformanceEvaluator()
