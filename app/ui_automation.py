from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class UIDrawResult:
    success: bool
    drawn_segments: int
    message: str


class KompasUIAutomator:
    """Управление КОМПАС через окно/мышь для наблюдаемого построения.

    Важно: это fallback для случаев, когда COM-рисование нестабильно на конкретной версии.
    """

    def draw_segments_in_open_window(
        self,
        segments: list[dict[str, float]],
        draw_delay_s: float = 0.01,
    ) -> UIDrawResult:
        if not segments:
            return UIDrawResult(False, 0, "UI-рисование пропущено: нет сегментов")

        try:
            import pyautogui  # type: ignore
            import pygetwindow as gw  # type: ignore
        except Exception as exc:  # noqa: BLE001
            return UIDrawResult(False, 0, f"UI-рисование недоступно: {exc}")

        windows = [w for w in gw.getAllWindows() if w.title and "КОМПАС" in w.title.upper()]
        if not windows:
            return UIDrawResult(False, 0, "Окно КОМПАС не найдено для UI-рисования")

        w = windows[0]
        try:
            w.activate()
            time.sleep(0.2)
            if hasattr(w, "maximize"):
                w.maximize()
                time.sleep(0.2)
        except Exception:
            pass

        left, top, width, height = int(w.left), int(w.top), int(w.width), int(w.height)
        if width < 500 or height < 350:
            return UIDrawResult(False, 0, "Размер окна КОМПАС слишком мал для UI-рисования")

        # Рабочее поле внутри окна (эмпирические проценты по интерфейсу КОМПАС).
        workspace = (
            int(left + width * 0.27),
            int(top + height * 0.18),
            int(left + width * 0.95),
            int(top + height * 0.92),
        )

        # Кнопка инструмента "Отрезок" (эмпирически в верхней ленте).
        line_tool_x = int(left + width * 0.13)
        line_tool_y = int(top + height * 0.105)

        pyautogui.PAUSE = max(0.001, min(draw_delay_s, 0.08))
        pyautogui.FAILSAFE = False

        try:
            pyautogui.click(line_tool_x, line_tool_y)
            time.sleep(0.1)
        except Exception as exc:  # noqa: BLE001
            return UIDrawResult(False, 0, f"Не удалось выбрать инструмент 'Отрезок': {exc}")

        x0, y0, x1, y1 = workspace
        ww = max(1, x1 - x0)
        wh = max(1, y1 - y0)

        # Нормализация соответствует box в vectorize.py: x=[25..185], y=[35..145]
        def to_screen(x_mm: float, y_mm: float) -> tuple[int, int]:
            nx = (x_mm - 25.0) / 160.0
            ny = (y_mm - 35.0) / 110.0
            nx = max(0.0, min(1.0, nx))
            ny = max(0.0, min(1.0, ny))
            sx = int(x0 + nx * ww)
            sy = int(y1 - ny * wh)
            return sx, sy

        drawn = 0
        for seg in segments:
            try:
                sx1, sy1 = to_screen(float(seg["x1"]), float(seg["y1"]))
                sx2, sy2 = to_screen(float(seg["x2"]), float(seg["y2"]))
            except Exception:
                continue

            if abs(sx1 - sx2) + abs(sy1 - sy2) < 3:
                continue

            try:
                pyautogui.click(sx1, sy1)
                pyautogui.click(sx2, sy2)
                drawn += 1
                if drawn % 40 == 0:
                    time.sleep(0.03)
            except Exception:
                continue

        try:
            pyautogui.press("esc")
        except Exception:
            pass

        if drawn == 0:
            return UIDrawResult(False, 0, "UI-рисование не нанесло ни одного сегмента")
        return UIDrawResult(True, drawn, f"UI-рисование выполнено: нанесено сегментов {drawn}")
