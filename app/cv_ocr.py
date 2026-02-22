from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CVOCRResult:
    detected_lines: int
    detected_circles: int
    ocr_text: str
    title_block_found: bool
    entities: list[str]
    warnings: list[str]


class CVOCRPipeline:
    """CV+OCR обработка чертежей с мягким fallback, если зависимости не установлены."""

    def analyze_drawing_image(self, image_path: Path) -> CVOCRResult:
        warnings: list[str] = []
        entities: list[str] = []
        detected_lines = 0
        detected_circles = 0
        ocr_text = ""
        title_block_found = False

        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"OpenCV недоступен: {exc}")
            return CVOCRResult(0, 0, "", False, ["контур"], warnings)

        img = cv2.imread(str(image_path))
        if img is None:
            warnings.append("Не удалось прочитать изображение")
            return CVOCRResult(0, 0, "", False, ["контур"], warnings)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)

        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=120, minLineLength=40, maxLineGap=8)
        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=30,
            param1=120,
            param2=30,
            minRadius=5,
            maxRadius=120,
        )

        detected_lines = 0 if lines is None else len(lines)
        detected_circles = 0 if circles is None else len(circles[0])

        if detected_lines > 20:
            entities.append("контур")
        if detected_lines > 50:
            entities.append("размерные линии")
        if detected_circles > 0:
            entities.append("отверстия/окружности")

        # Грубый поиск рамки/штампа в нижней правой части
        h, w = gray.shape
        roi = gray[int(h * 0.72) : h, int(w * 0.55) : w]
        _, roi_bw = cv2.threshold(roi, 180, 255, cv2.THRESH_BINARY_INV)
        non_zero = cv2.countNonZero(roi_bw)
        fill_ratio = non_zero / max(1, roi_bw.size)
        title_block_found = fill_ratio > 0.08
        if title_block_found:
            entities.append("основная надпись")

        # OCR через pytesseract (если доступен)
        try:
            import pytesseract  # type: ignore

            ocr_text = pytesseract.image_to_string(roi, lang="rus+eng")
            if ocr_text.strip():
                entities.append("текст рамки")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"OCR недоступен: {exc}")

        if not entities:
            entities.append("контур")

        return CVOCRResult(
            detected_lines=detected_lines,
            detected_circles=detected_circles,
            ocr_text=ocr_text.strip(),
            title_block_found=title_block_found,
            entities=sorted(set(entities)),
            warnings=warnings,
        )

    @staticmethod
    def to_dict(result: CVOCRResult) -> dict[str, Any]:
        return {
            "detected_lines": result.detected_lines,
            "detected_circles": result.detected_circles,
            "ocr_text": result.ocr_text,
            "title_block_found": result.title_block_found,
            "entities": result.entities,
            "warnings": result.warnings,
        }
