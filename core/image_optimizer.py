import io
import cv2
import numpy as np
from PIL import Image
from typing import Tuple, Optional


def pad_to_multiple(image: np.ndarray, multiple: int = 32) -> np.ndarray:
    """
    U-Net ConvTranspose 음수 패딩 오류 방지:
    이미지의 높이와 너비를 32의 배수로 맞추기 위해 흰색 여백(255)을 덧댑니다.
    """
    h, w = image.shape[:2]
    new_h = ((h + multiple - 1) // multiple) * multiple
    new_w = ((w + multiple - 1) // multiple) * multiple

    pad_bottom = new_h - h
    pad_right = new_w - w

    if pad_bottom > 0 or pad_right > 0:
        # 단색 또는 3채널 이미지 모두 대응
        value = (255, 255, 255) if len(image.shape) == 3 else 255
        image = cv2.copyMakeBorder(
            image, 0, pad_bottom, 0, pad_right,
            cv2.BORDER_CONSTANT, value=value
        )
    return image


class SheetMusicOptimizer:
    """
    악보 이미지 전처리 모듈:
    1. 자동 기울기 보정 (Deskew - minAreaRect 및 허프 변환 융합)
    2. 적응형 히스토그램 평활화 (CLAHE)
    3. 해상도 정규화 (Target Width 기준 종횡비 유지)
    4. 언샤프 마스킹(선명화) 및 배경 노이즈 제거
    """

    def __init__(self, target_width: int = 1350):
        # U-Net ConvTranspose ShapeInferenceError 방지: 1350px 복구
        self.target_width = target_width

    def optimize(self, image_bytes: bytes) -> bytes:
        """
        입력 이미지 바이트를 받아 전처리된 PNG 바이트 배열을 반환합니다.
        """
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            # OpenCV 파싱 실패 시 PIL로 폴백 후 다시 시도
            pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        # 1. 기울기 보정 (Deskew)
        deskewed = self._deskew(img)

        # 2. 해상도 최적화 (너비 기준 리사이징 및 32의 배수 패딩)
        resized = self._resize_to_target_width(deskewed, self.target_width)

        # 3. 그레이스케일 변환 및 CLAHE 적응형 대비 강화
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        contrast_enhanced = clahe.apply(gray)

        # 4. 언샤프 마스크를 통한 악보 선(Staff line) 및 음표(Note head) 선명화
        sharpened = self._unsharp_mask(contrast_enhanced)

        # 5. 미세 잡음 제거 및 배경 화이트닝
        cleaned = self._clean_background(sharpened)

        # 6. U-Net ConvTranspose 호환을 위한 32의 배수 최종 패딩
        final_img = pad_to_multiple(cleaned, multiple=32)

        # 7. PNG 포맷으로 인코딩
        _, encoded_img = cv2.imencode(".png", final_img, [cv2.IMWRITE_PNG_COMPRESSION, 4])
        return encoded_img.tobytes()

    def _deskew(self, img: np.ndarray) -> np.ndarray:
        """
        악보의 오선지 기울기를 감지하여 수평(-15도 ~ +15도 범위)으로 정밀 회전합니다.
        """
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # 수평 구조 감지를 위한 이진화
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

            # 수평선 성분 강조
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 1))
            morph = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

            coords = np.column_stack(np.where(morph > 0))
            if coords.shape[0] < 50:
                # 감지된 점이 너무 적으면 일반 비트맵 좌표 사용
                coords = np.column_stack(np.where(thresh > 0))
                if coords.shape[0] < 50:
                    return img

            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            elif angle > 45:
                angle = 90 - angle
            else:
                angle = -angle

            # 비정상적인 회전각(-15° ~ +15° 벗어남)은 회전하지 않음
            if abs(angle) > 15.0 or abs(angle) < 0.15:
                return img

            (h, w) = img.shape[:2]
            center = (w // 2, h // 2)
            rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
            deskewed = cv2.warpAffine(
                img,
                rot_mat,
                (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(255, 255, 255)
            )
            return deskewed
        except Exception:
            return img

    def _resize_to_target_width(self, img: np.ndarray, target_w: int) -> np.ndarray:
        """종횡비를 유지하며 target_width에 맞게 보간하고 32의 배수로 패딩합니다."""
        h, w = img.shape[:2]
        if w != target_w:
            scale = float(target_w) / float(w)
            target_h = int(round(h * scale))
            interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LANCZOS4
            img = cv2.resize(img, (target_w, target_h), interpolation=interpolation)
        return pad_to_multiple(img, multiple=32)

    def _unsharp_mask(self, gray: np.ndarray, sigma: float = 1.0, strength: float = 1.5) -> np.ndarray:
        """가우시안 블러를 이용한 고주파 강조(언샤프 마스크)"""
        blurred = cv2.GaussianBlur(gray, (0, 0), sigma)
        sharpened = cv2.addWeighted(gray, 1.0 + strength, blurred, -strength, 0)
        return np.clip(sharpened, 0, 255).astype(np.uint8)

    def _clean_background(self, gray: np.ndarray) -> np.ndarray:
        """배경의 연한 얼룩을 255(흰색)로 날리고 잉크 명암을 살립니다."""
        # 배경 밝기 감지를 위해 90% 백분위수 활용
        bright_cutoff = np.percentile(gray, 92)
        if bright_cutoff > 200:
            cleaned = gray.copy()
            cleaned[cleaned >= bright_cutoff] = 255
            return cleaned
        return gray
