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

    def extract_segments(self, image_path: Path, max_segments: int = 2000) -> list[Segment]:
        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore
        except Exception:
            return []

        img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return []

        blur = cv2.GaussianBlur(img, (3, 3), 0)
        bw = cv2.adaptiveThreshold(
            blur,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            35,
            7,
        )

        # Подавление мелкого шума
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel)

        segments_px: list[tuple[float, float, float, float]] = []

        # 1) Линейная детекция Хаффа
        lines = cv2.HoughLinesP(
            bw,
            rho=1,
            theta=np.pi / 180,
            threshold=55,
            minLineLength=12,
            maxLineGap=7,
        )
        if lines is not None:
            for l in lines:
                x1, y1, x2, y2 = l[0]
                if abs(x1 - x2) + abs(y1 - y2) >= 3:
                    segments_px.append((float(x1), float(y1), float(x2), float(y2)))

        # 2) Контуры + полилинии (добираем кривые ступенчатой аппроксимацией)
        contours, _ = cv2.findContours(bw, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        for cnt in contours[:500]:
            peri = cv2.arcLength(cnt, True)
            if peri < 25:
                continue
            approx = cv2.approxPolyDP(cnt, 0.003 * peri, True)
            pts = approx[:, 0, :]
            if len(pts) < 2:
                continue
            for i in range(len(pts)):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % len(pts)]
                if abs(int(x1) - int(x2)) + abs(int(y1) - int(y2)) >= 3:
                    segments_px.append((float(x1), float(y1), float(x2), float(y2)))

        if not segments_px:
            return []

        # Удаляем дубликаты и почти-дубликаты грубым округлением
        uniq: dict[tuple[int, int, int, int], tuple[float, float, float, float]] = {}
        for x1, y1, x2, y2 in segments_px:
            key = tuple(sorted(((round(x1), round(y1)), (round(x2), round(y2)))))
            flat_key = (key[0][0], key[0][1], key[1][0], key[1][1])
            uniq[flat_key] = (x1, y1, x2, y2)

        segs = list(uniq.values())[:max_segments]

        # Fit-to-box в рабочую область листа, чтобы геометрия была видна в центре
        xs = [s[0] for s in segs] + [s[2] for s in segs]
        ys = [s[1] for s in segs] + [s[3] for s in segs]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(1.0, max_x - min_x)
        span_y = max(1.0, max_y - min_y)

        # Поле чертежа (примерно внутри рамки A4 в мм)
        box_x0, box_y0 = 25.0, 35.0
        box_w, box_h = 160.0, 110.0
        s = min(box_w / span_x, box_h / span_y)

        segments: list[Segment] = []
        for x1, y1, x2, y2 in segs:
            nx1 = box_x0 + (x1 - min_x) * s
            ny1 = box_y0 + (max_y - y1) * s
            nx2 = box_x0 + (x2 - min_x) * s
            ny2 = box_y0 + (max_y - y2) * s
            if abs(nx1 - nx2) + abs(ny1 - ny2) < 0.25:
                continue
            segments.append(Segment(nx1, ny1, nx2, ny2))

        return segments


def segments_as_dict(segments: list[Segment]) -> list[dict[str, float]]:
    return [{"x1": s.x1, "y1": s.y1, "x2": s.x2, "y2": s.y2} for s in segments]
