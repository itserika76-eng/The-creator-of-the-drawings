from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Segment:
    x1: float
    y1: float
    x2: float
    y2: float


class ImageVectorizer:
    """Преобразует изображение чертежа в набор сегментов для CAD-экспорта.

    Упор на стабильность: минимум ложных длинных линий и более аккуратная геометрия.
    """

    def extract_segments(self, image_path: Path, max_segments: int = 900) -> list[Segment]:
        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore
        except Exception:
            return []

        img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return []

        # Контраст + шумоподавление
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        norm = clahe.apply(img)
        blur = cv2.GaussianBlur(norm, (3, 3), 0)

        # Бинарная маска и границы объекта
        _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)))

        ys, xs = np.where(bw > 0)
        if len(xs) < 20 or len(ys) < 20:
            return []

        min_x, max_x = int(xs.min()), int(xs.max())
        min_y, max_y = int(ys.min()), int(ys.max())

        # Отсечь рамки и поля, оставить область самого чертежа
        pad_x = int((max_x - min_x) * 0.03)
        pad_y = int((max_y - min_y) * 0.03)
        min_x = max(0, min_x + pad_x)
        min_y = max(0, min_y + pad_y)
        max_x = min(img.shape[1] - 1, max_x - pad_x)
        max_y = min(img.shape[0] - 1, max_y - pad_y)

        roi = blur[min_y:max_y, min_x:max_x]
        if roi.size == 0:
            return []

        # Детектор отрезков LSD обычно даёт более «чертёжные» сегменты, чем сырые контуры
        lsd = cv2.createLineSegmentDetector(0)
        detected = lsd.detect(roi)[0]

        raw_segments: list[tuple[float, float, float, float]] = []
        if detected is not None:
            for s in detected:
                x1, y1, x2, y2 = s[0]
                x1 += min_x
                x2 += min_x
                y1 += min_y
                y2 += min_y
                raw_segments.append((float(x1), float(y1), float(x2), float(y2)))

        # fallback на Хафф, если LSD дал слишком мало
        if len(raw_segments) < 80:
            edges = cv2.Canny(roi, 40, 120)
            lines = cv2.HoughLinesP(
                edges,
                rho=1,
                theta=np.pi / 180,
                threshold=45,
                minLineLength=12,
                maxLineGap=6,
            )
            if lines is not None:
                for l in lines:
                    x1, y1, x2, y2 = l[0]
                    raw_segments.append((float(x1 + min_x), float(y1 + min_y), float(x2 + min_x), float(y2 + min_y)))

        if not raw_segments:
            return []

        # Фильтры: убрать чрезмерно длинные/короткие и дубликаты
        diag = math.hypot(max_x - min_x, max_y - min_y)
        min_len = max(6.0, diag * 0.008)
        max_len = diag * 0.35

        uniq: dict[tuple[int, int, int, int], tuple[float, float, float, float]] = {}
        for x1, y1, x2, y2 in raw_segments:
            length = math.hypot(x2 - x1, y2 - y1)
            if length < min_len or length > max_len:
                continue

            # нормализованный ключ без учета направления
            a = (round(x1 / 2), round(y1 / 2))
            b = (round(x2 / 2), round(y2 / 2))
            k = tuple(sorted((a, b)))
            key = (k[0][0], k[0][1], k[1][0], k[1][1])
            uniq[key] = (x1, y1, x2, y2)

        segs = list(uniq.values())
        if not segs:
            return []

        # Сортируем для предсказуемого «пошагового» построения слева-направо, сверху-вниз
        segs.sort(key=lambda s: ((s[1] + s[3]) * 0.5, (s[0] + s[2]) * 0.5))
        segs = segs[:max_segments]

        # Fit-to-box на рабочее поле листа
        xs2 = [s[0] for s in segs] + [s[2] for s in segs]
        ys2 = [s[1] for s in segs] + [s[3] for s in segs]
        sx0, sx1 = min(xs2), max(xs2)
        sy0, sy1 = min(ys2), max(ys2)
        span_x = max(1.0, sx1 - sx0)
        span_y = max(1.0, sy1 - sy0)

        box_x0, box_y0 = 30.0, 40.0
        box_w, box_h = 150.0, 100.0
        scale = min(box_w / span_x, box_h / span_y)

        result: list[Segment] = []
        for x1, y1, x2, y2 in segs:
            nx1 = box_x0 + (x1 - sx0) * scale
            ny1 = box_y0 + (sy1 - y1) * scale
            nx2 = box_x0 + (x2 - sx0) * scale
            ny2 = box_y0 + (sy1 - y2) * scale
            if abs(nx1 - nx2) + abs(ny1 - ny2) < 0.2:
                continue
            result.append(Segment(nx1, ny1, nx2, ny2))

        return result


def segments_as_dict(segments: list[Segment]) -> list[dict[str, float]]:
    return [{"x1": s.x1, "y1": s.y1, "x2": s.x2, "y2": s.y2} for s in segments]
