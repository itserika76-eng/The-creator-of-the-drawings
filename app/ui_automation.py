from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class UIDrawResult:
    success: bool
    drawn_segments: int
    message: str


class KompasUIAutomator:
    """Управление КОМПАС через окно/мышь для наблюдаемого построения."""

    def _find_kompas_window(self):
        import pygetwindow as gw  # type: ignore

        windows = [w for w in gw.getAllWindows() if w.title and "КОМПАС" in w.title.upper()]
        if not windows:
            return None
        return windows[0]

    def _activate_and_maximize(self, w) -> None:
        try:
            w.activate()
            time.sleep(0.25)
            if hasattr(w, "maximize"):
                w.maximize()
                time.sleep(0.25)
        except Exception:
            pass

    def _open_new_drawing_doc(self, pyautogui, w) -> None:
        left, top, width, height = int(w.left), int(w.top), int(w.width), int(w.height)
        pyautogui.hotkey("ctrl", "n")
        time.sleep(0.45)
        draw_tile_x = int(left + width * 0.47)
        draw_tile_y = int(top + height * 0.38)
        pyautogui.click(draw_tile_x, draw_tile_y)
        time.sleep(0.15)
        pyautogui.press("enter")
        time.sleep(0.8)

    def _score_batch(self, before_img, after_img, target_edges) -> float:
        import cv2  # type: ignore
        import numpy as np  # type: ignore

        b_gray = cv2.cvtColor(before_img, cv2.COLOR_RGB2GRAY)
        a_gray = cv2.cvtColor(after_img, cv2.COLOR_RGB2GRAY)

        b_edges = cv2.Canny(b_gray, 60, 140)
        a_edges = cv2.Canny(a_gray, 60, 140)
        new_edges = cv2.bitwise_and(a_edges, cv2.bitwise_not(b_edges))

        if target_edges is None:
            return float(np.count_nonzero(new_edges))

        # F-score-like: насколько новые штрихи совпадают с целевой картой
        overlap = np.count_nonzero(cv2.bitwise_and(new_edges, target_edges))
        drawn = max(1, np.count_nonzero(new_edges))
        target = max(1, np.count_nonzero(target_edges))
        precision = overlap / drawn
        recall = overlap / target
        if precision + recall == 0:
            return 0.0
        return 2 * precision * recall / (precision + recall)

    def _build_target_edges(self, source_image_path: str | None, workspace_wh: tuple[int, int]):
        if not source_image_path:
            return None
        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore

            img = cv2.imread(str(source_image_path), cv2.IMREAD_GRAYSCALE)
            if img is None:
                return None
            img = cv2.resize(img, workspace_wh)
            _, bw = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            edges = cv2.Canny(bw, 50, 150)
            kernel = np.ones((2, 2), np.uint8)
            edges = cv2.dilate(edges, kernel, iterations=1)
            return edges
        except Exception:
            return None

    def draw_segments_in_open_window(
        self,
        segments: list[dict[str, float]],
        draw_delay_s: float = 0.01,
        geometry_box: dict[str, float] | None = None,
        source_image_path: str | None = None,
        ensure_new_document: bool = True,
    ) -> UIDrawResult:
        if not segments:
            return UIDrawResult(False, 0, "UI-рисование пропущено: нет сегментов")

        try:
            import pyautogui  # type: ignore
            import pygetwindow as _  # type: ignore
        except Exception as exc:  # noqa: BLE001
            return UIDrawResult(False, 0, f"UI-рисование недоступно: {exc}")

        w = self._find_kompas_window()
        if not w:
            return UIDrawResult(False, 0, "Окно КОМПАС не найдено для UI-рисования")

        self._activate_and_maximize(w)

        if ensure_new_document:
            self._open_new_drawing_doc(pyautogui, w)
            w = self._find_kompas_window() or w
            self._activate_and_maximize(w)

        left, top, width, height = int(w.left), int(w.top), int(w.width), int(w.height)
        if width < 500 or height < 350:
            return UIDrawResult(False, 0, "Размер окна КОМПАС слишком мал для UI-рисования")

        workspace = (
            int(left + width * 0.27),
            int(top + height * 0.18),
            int(left + width * 0.95),
            int(top + height * 0.92),
        )

        line_tool_x = int(left + width * 0.13)
        line_tool_y = int(top + height * 0.105)

        pyautogui.PAUSE = max(0.001, min(draw_delay_s, 0.06))
        pyautogui.FAILSAFE = False

        try:
            pyautogui.click(line_tool_x, line_tool_y)
            time.sleep(0.15)
        except Exception as exc:  # noqa: BLE001
            return UIDrawResult(False, 0, f"Не удалось выбрать инструмент 'Отрезок': {exc}")

        x0, y0, x1, y1 = workspace
        ww = max(1, x1 - x0)
        wh = max(1, y1 - y0)
        box = geometry_box or {"x0": 30.0, "y0": 40.0, "w": 150.0, "h": 100.0}

        target_edges = self._build_target_edges(source_image_path, (ww, wh))

        def to_screen(x_mm: float, y_mm: float) -> tuple[int, int]:
            nx = (x_mm - float(box.get("x0", 30.0))) / max(1e-6, float(box.get("w", 150.0)))
            ny = (y_mm - float(box.get("y0", 40.0))) / max(1e-6, float(box.get("h", 100.0)))
            nx = max(0.0, min(1.0, nx))
            ny = max(0.0, min(1.0, ny))
            sx = int(x0 + nx * ww)
            sy = int(y1 - ny * wh)
            return sx, sy

        drawn = 0
        batch_size = 12
        accepted_score = 0.0

        for i in range(0, len(segments), batch_size):
            batch = segments[i : i + batch_size]
            before = pyautogui.screenshot(region=(x0, y0, ww, wh))

            batch_drawn = 0
            for seg in batch:
                try:
                    sx1, sy1 = to_screen(float(seg["x1"]), float(seg["y1"]))
                    sx2, sy2 = to_screen(float(seg["x2"]), float(seg["y2"]))
                except Exception:
                    continue

                if abs(sx1 - sx2) + abs(sy1 - sy2) < 3:
                    continue

                try:
                    # плавнее: подводим курсор к началу
                    pyautogui.moveTo(sx1, sy1, duration=0.03)
                    pyautogui.click(sx1, sy1)
                    pyautogui.moveTo(sx2, sy2, duration=0.04)
                    pyautogui.click(sx2, sy2)
                    batch_drawn += 1
                except Exception:
                    continue

            after = pyautogui.screenshot(region=(x0, y0, ww, wh))
            try:
                import numpy as np  # type: ignore

                score = self._score_batch(np.array(before), np.array(after), target_edges)
            except Exception:
                score = 1.0

            # Если качество стало хуже, откатываем пакет (редактирование/исправление)
            if target_edges is not None and score + 1e-6 < accepted_score and batch_drawn > 0:
                for _ in range(batch_drawn):
                    pyautogui.hotkey("ctrl", "z")
                    time.sleep(0.01)
                # попытка альтернативы: уменьшаем влияние, пропускаем текущий пакет
                continue

            if score > accepted_score:
                accepted_score = score
            drawn += batch_drawn
            if drawn % 40 == 0:
                time.sleep(0.04)

        try:
            pyautogui.press("esc")
        except Exception:
            pass

        if drawn == 0:
            return UIDrawResult(False, 0, "UI-рисование не нанесло ни одного сегмента")

        extra = f", quality_score={accepted_score:.4f}" if target_edges is not None else ""
        return UIDrawResult(True, drawn, f"UI-рисование выполнено: нанесено сегментов {drawn}{extra}")
