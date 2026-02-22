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
    """Преобразует изображение чертежа в набор осевых сегментов (skeleton-first)."""

    def _skeletonize(self, bw):
        import cv2  # type: ignore
        import numpy as np  # type: ignore

        skel = np.zeros(bw.shape, np.uint8)
        element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        img = bw.copy()

        for _ in range(300):
            eroded = cv2.erode(img, element)
            opened = cv2.dilate(eroded, element)
            temp = cv2.subtract(img, opened)
            skel = cv2.bitwise_or(skel, temp)
            img = eroded.copy()
            if cv2.countNonZero(img) == 0:
                break

        return skel

    def extract_segments(self, image_path: Path, max_segments: int = 220) -> list[Segment]:
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

        # Удаляем мелкий шум и оставляем только крупные компоненты
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
        cleaned = np.zeros_like(bw)
        min_area = max(80, int(img.shape[0] * img.shape[1] * 0.0005))
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area >= min_area:
                cleaned[labels == i] = 255

        ys, xs = np.where(cleaned > 0)
        if len(xs) < 20:
            return []

        min_x, max_x = int(xs.min()), int(xs.max())
        min_y, max_y = int(ys.min()), int(ys.max())
        roi = cleaned[min_y:max_y, min_x:max_x]
        if roi.size == 0:
            return []

        skel = self._skeletonize(roi)
        lines = cv2.HoughLinesP(
            skel,
            rho=1,
            theta=np.pi / 180,
            threshold=14,
            minLineLength=max(10, int(min(roi.shape) * 0.06)),
            maxLineGap=5,
        )
        if lines is None:
            return []

        raw: list[tuple[float, float, float, float]] = []
        for l in lines:
            x1, y1, x2, y2 = l[0]
            x1 += min_x
            x2 += min_x
            y1 += min_y
            y2 += min_y
            raw.append((float(x1), float(y1), float(x2), float(y2)))

        diag = math.hypot(max_x - min_x, max_y - min_y)
        min_len = max(8.0, diag * 0.03)
        max_len = diag * 0.75

        def snap_angle(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float, float, float]:
            dx, dy = x2 - x1, y2 - y1
            ang = abs(math.degrees(math.atan2(dy, dx))) % 180
            if ang < 8 or ang > 172:
                y2 = y1
            elif 82 < ang < 98:
                x2 = x1
            elif 38 < ang < 52 or 128 < ang < 142:
                # стабилизация диагоналей ~45° для крыш/скосов
                signx = 1 if dx >= 0 else -1
                signy = 1 if dy >= 0 else -1
                m = max(abs(dx), abs(dy))
                x2 = x1 + signx * m
                y2 = y1 + signy * m
            return x1, y1, x2, y2

        uniq: dict[tuple[int, int, int, int], tuple[float, float, float, float]] = {}
        margin_x = int((max_x - min_x) * 0.015)
        margin_y = int((max_y - min_y) * 0.015)

        for x1, y1, x2, y2 in raw:
            x1, y1, x2, y2 = snap_angle(x1, y1, x2, y2)
            length = math.hypot(x2 - x1, y2 - y1)
            if length < min_len or length > max_len:
                continue

            # Убираем артефакты на самом краю ROI (часто рамки/обрезки)
            if (x1 <= min_x + margin_x and x2 <= min_x + margin_x) or (x1 >= max_x - margin_x and x2 >= max_x - margin_x):
                continue
            if (y1 <= min_y + margin_y and y2 <= min_y + margin_y) or (y1 >= max_y - margin_y and y2 >= max_y - margin_y):
                continue

            a = (round(x1 / 2), round(y1 / 2))
            b = (round(x2 / 2), round(y2 / 2))
            k = tuple(sorted((a, b)))
            key = (k[0][0], k[0][1], k[1][0], k[1][1])
            uniq[key] = (x1, y1, x2, y2)

        segs = list(uniq.values())
        if not segs:
            return []

        segs.sort(key=lambda s: (((s[1] + s[3]) * 0.5), ((s[0] + s[2]) * 0.5), -math.hypot(s[2] - s[0], s[3] - s[1])))
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
            if abs(nx1 - nx2) + abs(ny1 - ny2) < 0.5:
                continue
            result.append(Segment(nx1, ny1, nx2, ny2))

        return result


def segments_as_dict(segments: list[Segment]) -> list[dict[str, float]]:
    return [{"x1": s.x1, "y1": s.y1, "x2": s.x2, "y2": s.y2} for s in segments]


def cad_box_as_dict() -> dict[str, float]:
    return dict(CAD_BOX)
