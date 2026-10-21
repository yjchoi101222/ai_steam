import copy
import music21 as m21
from typing import Optional


class ScoreCorrector:
    """
    OMR(oemer) 결과물 1차 자동 교정기:
    1. 중복 노이즈 제거 (동일 오프셋의 중복 피치 정리)
    2. 88건반(A0~C8) 옥타브 범위 보정
    3. 2048th/1024th 등 비정상적 극소 파편 음표 제거 및 보정
    4. 높은음자리표(Treble) / 낮은음자리표(Bass) 기본값 검증 및 보정
    5. 마디 박자 구조(makeMeasures/makeTies) 정규화
    """

    def __init__(self, min_quarter_length: float = 0.125):
        # 1/32음표(0.125 quarter length) 미만의 비정상 파편 필터링 기준
        self.min_quarter_length = min_quarter_length
        self.min_midi_pitch = 21   # A0
        self.max_midi_pitch = 108  # C8

    def run_all(self, score: m21.stream.Score) -> m21.stream.Score:
        """모든 교정 파이프라인을 순서환적으로 적용합니다."""
        if score is None:
            return score

        # 1. 음자리표 보정
        score = self.fix_clefs(score)

        # 2. 파편 음표 제거/보정
        score = self.remove_micro_fragments(score)

        # 3. 동일 오프셋 중복 피치 제거
        score = self.deduplicate_notes(score)

        # 4. 88건반 옥타브 범위 클램핑
        score = self.clamp_88_keys(score)

        # 5. 마디 박자 정규화
        score = self.normalize_measures(score)

        return score

    def fix_clefs(self, score: m21.stream.Score) -> m21.stream.Score:
        """각 파트에 적합한 음자리표(1번 파트: 높은음자리표, 2번 파트: 낮은음자리표)를 보장합니다."""
        try:
            for idx, part in enumerate(score.parts):
                clefs = list(part.recurse().getElementsByClass(m21.clef.Clef))
                if not clefs:
                    first_measure = part.getElementsByClass(m21.stream.Measure).first()
                    target = first_measure if first_measure else part
                    if idx == 0:
                        target.insert(0.0, m21.clef.TrebleClef())
                    else:
                        target.insert(0.0, m21.clef.BassClef())
        except Exception as e:
            print(f"[Corrector] 음자리표 보정 중 경고: {e}")
        return score

    def remove_micro_fragments(self, score: m21.stream.Score) -> m21.stream.Score:
        """OMR 인식 오류로 발생한 2048th, 1024th 등의 극소 파편 음표를 정리합니다."""
        try:
            for part in score.parts:
                for measure in part.getElementsByClass(m21.stream.Measure):
                    elements_to_remove = []
                    for el in list(measure.notesAndRests):
                        ql = float(el.quarterLength)
                        if ql < self.min_quarter_length:
                            elements_to_remove.append(el)
                    for el in elements_to_remove:
                        measure.remove(el)
        except Exception as e:
            print(f"[Corrector] 파편 음표 정리 중 경고: {e}")
        return score

    def deduplicate_notes(self, score: m21.stream.Score) -> m21.stream.Score:
        """동일 마디 내 같은 오프셋에 겹쳐 있는 중복 음표/화음 피치를 정리합니다."""
        try:
            for part in score.parts:
                for measure in part.getElementsByClass(m21.stream.Measure):
                    seen_offsets = {}
                    for el in list(measure.notes):
                        off = round(float(el.offset), 3)
                        if el.isNote:
                            p_name = el.pitch.nameWithOctave
                            if off in seen_offsets and p_name in seen_offsets[off]:
                                measure.remove(el)
                            else:
                                seen_offsets.setdefault(off, set()).add(p_name)
                        elif el.isChord:
                            unique_pitches = []
                            seen_in_chord = set()
                            for p in el.pitches:
                                if p.nameWithOctave not in seen_in_chord:
                                    seen_in_chord.add(p.nameWithOctave)
                                    unique_pitches.append(p)
                            el.pitches = unique_pitches
        except Exception as e:
            print(f"[Corrector] 중복 음표 제거 중 경고: {e}")
        return score

    def clamp_88_keys(self, score: m21.stream.Score) -> m21.stream.Score:
        """피아노 88건반(A0 21 ~ C8 108) 범위를 벗어난 이상 옥타브를 안전 영역으로 전조합니다."""
        try:
            for el in score.recurse().getElementsByClass([m21.note.Note, m21.chord.Chord]):
                if el.isNote:
                    self._clamp_pitch(el.pitch)
                elif el.isChord:
                    for p in el.pitches:
                        self._clamp_pitch(p)
        except Exception as e:
            print(f"[Corrector] 옥타브 클램핑 중 경고: {e}")
        return score

    def _clamp_pitch(self, pitch_obj: m21.pitch.Pitch):
        """단일 Pitch 객체의 MIDI 번호를 검사하여 88건반 내로 옥타브 이동합니다."""
        while pitch_obj.midi < self.min_midi_pitch and pitch_obj.octave is not None:
            pitch_obj.octave += 1
        while pitch_obj.midi > self.max_midi_pitch and pitch_obj.octave is not None:
            pitch_obj.octave -= 1

    def normalize_measures(self, score: m21.stream.Score) -> m21.stream.Score:
        """마디 길이 초과 및 연결선(Tie) 구조를 음악 규칙에 맞게 정규화합니다."""
        try:
            for part in score.parts:
                part.makeMeasures(inPlace=True)
                part.makeTies(inPlace=True)
        except Exception as e:
            print(f"[Corrector] 마디 정규화 경고: {e}")
        return score
