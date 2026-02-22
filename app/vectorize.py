from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Segment:
    x1: float
    y1: float
    x2: float
    y2: float


class ImageVectorizer:
    """Преобразует изображение чертежа в набор линейных сегментов для CAD-экспорта."""

    def extract_segments(self, image_path: Path, max_segments: int = 1200) -> list[Segment]:
        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore
        except Exception:
            return []

        img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return []

        # Бинаризация и выделение контуров
        blur = cv2.GaussianBlur(img, (3, 3), 0)
        bw = cv2.adaptiveThreshold(
            blur,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            35,
            7,
        )

        # Ищем линии по вероятностному Хаффу
        lines = cv2.HoughLinesP(
            bw,
            rho=1,
            theta=np.pi / 180,
            threshold=70,
            minLineLength=20,
            maxLineGap=5,
        )

        if lines is None:
            return []

        h, w = img.shape
        # Нормализуем в условные миллиметры A3/A4 рабочей области
        scale_x = 250.0 / max(1, w)
        scale_y = 170.0 / max(1, h)

        segments: list[Segment] = []
        for l in lines[:max_segments]:
            x1, y1, x2, y2 = l[0]
            # Переворот Y для CAD-координат
            sx1, sy1 = x1 * scale_x, (h - y1) * scale_y
            sx2, sy2 = x2 * scale_x, (h - y2) * scale_y
            if abs(sx1 - sx2) + abs(sy1 - sy2) < 0.5:
                continue
            segments.append(Segment(sx1, sy1, sx2, sy2))

        return segments


def segments_as_dict(segments: list[Segment]) -> list[dict[str, float]]:
    return [{"x1": s.x1, "y1": s.y1, "x2": s.x2, "y2": s.y2} for s in segments]
