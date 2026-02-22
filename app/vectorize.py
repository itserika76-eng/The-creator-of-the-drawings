from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

CAD_BOX = {"x0": 30.0, "y0": 40.0, "w": 150.0, "h": 100.0}


@dataclass
class Segment:
    x1: float
    y1: float
    x2: float
    y2: float


class ImageVectorizer:
    """Преобразует изображение чертежа в набор сегментов для CAD-экспорта."""

    def extract_segments(self, image_path: Path, max_segments: int = 500) -> list[Segment]:
        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore
        except Exception:
            return []

        img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return []

        blur = cv2.GaussianBlur(img, (3, 3), 0)
        _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))

        ys, xs = np.where(bw > 0)
        if len(xs) < 20:
            return []

        min_x, max_x = int(xs.min()), int(xs.max())
        min_y, max_y = int(ys.min()), int(ys.max())
        roi = bw[min_y:max_y, min_x:max_x]
        if roi.size == 0:
            return []

        # 1) Основные контуры (лучше сохраняют форму простых объектов вроде дома)
        contours, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        raw_segments: list[tuple[float, float, float, float]] = []
        for cnt in contours:
            peri = cv2.arcLength(cnt, True)
            if peri < 40:
                continue
            approx = cv2.approxPolyDP(cnt, 0.01 * peri, True)
            pts = approx[:, 0, :]
            if len(pts) < 2:
                continue
            for i in range(len(pts)):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % len(pts)]
                raw_segments.append((float(x1 + min_x), float(y1 + min_y), float(x2 + min_x), float(y2 + min_y)))

        # 2) Добираем внутренние линии через LSD
        lsd = cv2.createLineSegmentDetector(0)
        detected = lsd.detect(roi)[0]
        if detected is not None:
            for s in detected:
                x1, y1, x2, y2 = s[0]
                raw_segments.append((float(x1 + min_x), float(y1 + min_y), float(x2 + min_x), float(y2 + min_y)))

        if not raw_segments:
            return []

        diag = math.hypot(max_x - min_x, max_y - min_y)
        min_len = max(8.0, diag * 0.02)
        max_len = diag * 0.9

        def snap_angle(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float, float, float]:
            dx, dy = x2 - x1, y2 - y1
            ang = abs(math.degrees(math.atan2(dy, dx))) % 180
            # для простых чертежей стабилизируем горизонтали/вертикали/диагонали
            if ang < 8 or ang > 172:
                y2 = y1
            elif 82 < ang < 98:
                x2 = x1
            return x1, y1, x2, y2

        uniq: dict[tuple[int, int, int, int], tuple[float, float, float, float]] = {}
        for x1, y1, x2, y2 in raw_segments:
            x1, y1, x2, y2 = snap_angle(x1, y1, x2, y2)
            length = math.hypot(x2 - x1, y2 - y1)
            if length < min_len or length > max_len:
                continue
            a = (round(x1 / 2), round(y1 / 2))
            b = (round(x2 / 2), round(y2 / 2))
            k = tuple(sorted((a, b)))
            key = (k[0][0], k[0][1], k[1][0], k[1][1])
            uniq[key] = (x1, y1, x2, y2)

        segs = list(uniq.values())
        if not segs:
            return []
        segs.sort(key=lambda s: ((s[1] + s[3]) * 0.5, (s[0] + s[2]) * 0.5))
        segs = segs[:max_segments]

        xs2 = [s[0] for s in segs] + [s[2] for s in segs]
        ys2 = [s[1] for s in segs] + [s[3] for s in segs]
        sx0, sx1 = min(xs2), max(xs2)
        sy0, sy1 = min(ys2), max(ys2)
        span_x = max(1.0, sx1 - sx0)
        span_y = max(1.0, sy1 - sy0)

        scale = min(CAD_BOX["w"] / span_x, CAD_BOX["h"] / span_y)
        result: list[Segment] = []
        for x1, y1, x2, y2 in segs:
            nx1 = CAD_BOX["x0"] + (x1 - sx0) * scale
            ny1 = CAD_BOX["y0"] + (sy1 - y1) * scale
            nx2 = CAD_BOX["x0"] + (x2 - sx0) * scale
            ny2 = CAD_BOX["y0"] + (sy1 - y2) * scale
            if abs(nx1 - nx2) + abs(ny1 - ny2) < 0.4:
                continue
            result.append(Segment(nx1, ny1, nx2, ny2))

        return result


def segments_as_dict(segments: list[Segment]) -> list[dict[str, float]]:
    return [{"x1": s.x1, "y1": s.y1, "x2": s.x2, "y2": s.y2} for s in segments]


def cad_box_as_dict() -> dict[str, float]:
    return dict(CAD_BOX)
