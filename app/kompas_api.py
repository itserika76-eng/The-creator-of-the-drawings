from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class KompasExportResult:
    success: bool
    native_cdw_path: Path | None
    native_spw_path: Path | None
    fallback_cdw_payload_path: Path | None
    fallback_spw_payload_path: Path | None
    message: str


class KompasExporter:
    """Экспорт в КОМПАС-3D: создаёт валидный .cdw и переносит векторизованную геометрию."""

    def __init__(self, compas_executable: Path) -> None:
        self.compas_executable = compas_executable

    def export(self, package: dict[str, Any], output_dir: Path) -> KompasExportResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        project = str(package.get("project_name", "drawing")).strip() or "drawing"
        native_cdw_path = output_dir / f"{project}.cdw"
        native_spw_path = output_dir / f"{project}.spw"

        try:
            created = self._try_create_native_documents(
                native_cdw_path=native_cdw_path,
                native_spw_path=native_spw_path,
                package=package,
            )
            if created:
                return KompasExportResult(
                    success=True,
                    native_cdw_path=native_cdw_path,
                    native_spw_path=native_spw_path if native_spw_path.exists() else None,
                    fallback_cdw_payload_path=None,
                    fallback_spw_payload_path=None,
                    message="Нативный документ КОМПАС с геометрией создан через COM API",
                )
            raise RuntimeError("COM доступен, но создать валидный .cdw с геометрией не удалось")
        except Exception as exc:  # noqa: BLE001
            fallback_cdw_payload_path = output_dir / f"{project}.cdw.fallback.json"
            fallback_spw_payload_path = output_dir / f"{project}.spw.fallback.json"

            cdw_payload = {
                "format": "cdw-fallback-payload",
                "note": "Это не файл КОМПАС. Используется как диагностический payload для среды без рабочего COM API.",
                "package": package,
            }
            spw_payload = {
                "format": "spw-fallback-payload",
                "note": "Это не файл КОМПАС. Используется как диагностический payload для среды без рабочего COM API.",
                "spec_items": package.get("specification_items", []),
            }

            fallback_cdw_payload_path.write_text(json.dumps(cdw_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            fallback_spw_payload_path.write_text(json.dumps(spw_payload, ensure_ascii=False, indent=2), encoding="utf-8")

            return KompasExportResult(
                success=False,
                native_cdw_path=None,
                native_spw_path=None,
                fallback_cdw_payload_path=fallback_cdw_payload_path,
                fallback_spw_payload_path=fallback_spw_payload_path,
                message=f"Не удалось создать валидный .cdw через COM API: {exc}",
            )

    def _try_create_native_documents(self, native_cdw_path: Path, native_spw_path: Path, package: dict[str, Any]) -> bool:
        import win32com.client  # type: ignore

        errors: list[str] = []

        try:
            app7 = win32com.client.Dispatch("Kompas.Application.7")
            app7.Visible = True
            if self._create_cdw_v7(app7, native_cdw_path, package):
                self._create_spw_v7(app7, native_spw_path)
                return True
        except Exception as exc:  # noqa: BLE001
            errors.append(f"v7: {exc}")

        try:
            app5 = win32com.client.Dispatch("KOMPAS.Application.5")
            app5.Visible = True
            if self._create_cdw_v5(app5, native_cdw_path, package):
                self._create_spw_v5(app5, native_spw_path)
                return True
        except Exception as exc:  # noqa: BLE001
            errors.append(f"v5: {exc}")

        raise RuntimeError("; ".join(errors) if errors else "Не удалось подключиться к COM API")

    def _draw_segments_on_object(self, draw_obj: Any, package: dict[str, Any]) -> int:
        segments = package.get("geometry_segments", [])
        if not isinstance(segments, list):
            return 0

        drawn = 0
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            try:
                x1, y1 = float(seg["x1"]), float(seg["y1"])
                x2, y2 = float(seg["x2"]), float(seg["y2"])
            except Exception:  # noqa: BLE001
                continue

            ok = False
            # Популярные методы 2D API
            for method_name, args in (
                ("ksLineSeg", (x1, y1, x2, y2, 1)),
                ("LineSeg", (x1, y1, x2, y2, 1)),
                ("ksLine", (x1, y1, x2, y2, 1)),
            ):
                method = getattr(draw_obj, method_name, None)
                if method is None:
                    continue
                try:
                    result = method(*args)
                    ok = bool(result) or result is None
                    if ok:
                        break
                except Exception:  # noqa: BLE001
                    continue

            if ok:
                drawn += 1

        return drawn

    def _create_cdw_v7(self, app7: Any, path: Path, package: dict[str, Any]) -> bool:
        docs = getattr(app7, "Documents", None)
        if docs is None:
            return False

        created_doc = None
        for args in ((1, True), (1,), ("Чертеж", True)):
            try:
                created_doc = docs.Add(*args)
                if created_doc is not None:
                    break
            except Exception:  # noqa: BLE001
                continue
        if created_doc is None:
            return False

        # Ищем 2D объект рисования
        draw_obj = None
        for attr in ("ActiveDocument2D", "Document2D", "ViewsAndLayersManager"):
            candidate = getattr(created_doc, attr, None)
            if candidate is not None:
                draw_obj = candidate
                break
        if draw_obj is None:
            draw_obj = created_doc

        drawn = self._draw_segments_on_object(draw_obj, package)
        if drawn < 20:
            # Если геометрии почти нет, не считаем результат пригодным (чтобы не получать пустую рамку)
            return False

        for save_args in ((str(path),), (str(path), 0), (str(path), True)):
            try:
                created_doc.SaveAs(*save_args)
                if path.exists() and path.stat().st_size > 0:
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False

    def _create_spw_v7(self, app7: Any, path: Path) -> bool:
        docs = getattr(app7, "Documents", None)
        if docs is None:
            return False

        created_doc = None
        for args in ((5, True), (4, True), (5,), (4,)):
            try:
                created_doc = docs.Add(*args)
                if created_doc is not None:
                    break
            except Exception:  # noqa: BLE001
                continue
        if created_doc is None:
            return False

        for save_args in ((str(path),), (str(path), 0), (str(path), True)):
            try:
                created_doc.SaveAs(*save_args)
                if path.exists() and path.stat().st_size > 0:
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False

    def _create_cdw_v5(self, app5: Any, path: Path, package: dict[str, Any]) -> bool:
        doc2d = app5.Document2D()

        created = False
        for create_args in ((str(path), 0, False), (str(path), 0), (str(path),)):
            try:
                result = doc2d.ksCreateDocument(*create_args)
                if result:
                    created = True
                    break
            except Exception:  # noqa: BLE001
                continue

        if not created:
            return False

        drawn = self._draw_segments_on_object(doc2d, package)
        if drawn < 20:
            return False

        try:
            doc2d.ksSaveDocument(str(path))
        except Exception:  # noqa: BLE001
            pass
        return path.exists() and path.stat().st_size > 0

    @staticmethod
    def _create_spw_v5(app5: Any, path: Path) -> bool:
        try:
            doc = app5.SpcDocument()
        except Exception:  # noqa: BLE001
            return False

        for create_args in ((str(path), 0, False), (str(path), 0), (str(path),)):
            try:
                result = doc.ksCreateDocument(*create_args)
                if result and path.exists() and path.stat().st_size > 0:
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False
