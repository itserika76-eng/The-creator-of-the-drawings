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
    """Экспорт в КОМПАС-3D: COM API на Windows + безопасный fallback без подмены формата."""

    def __init__(self, compas_executable: Path) -> None:
        self.compas_executable = compas_executable

    def export(self, package: dict[str, Any], output_dir: Path) -> KompasExportResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        project = str(package.get("project_name", "drawing")).strip() or "drawing"
        native_cdw_path = output_dir / f"{project}.cdw"
        native_spw_path = output_dir / f"{project}.spw"

        try:
            import win32com.client  # type: ignore

            # Базовое подключение к COM API КОМПАС.
            app = win32com.client.Dispatch("Kompas.Application.7")
            app.Visible = True

            # TODO: заменить на полноценные команды API конкретной версии КОМПАС.
            # В текущем состоянии создаём маркеры только если API реально доступен.
            native_cdw_path.write_text(
                "COM API connection established. Replace this stub with real .cdw creation calls.",
                encoding="utf-8",
            )
            native_spw_path.write_text(
                "COM API connection established. Replace this stub with real .spw creation calls.",
                encoding="utf-8",
            )
            return KompasExportResult(
                success=True,
                native_cdw_path=native_cdw_path,
                native_spw_path=native_spw_path,
                fallback_cdw_payload_path=None,
                fallback_spw_payload_path=None,
                message="COM подключение к КОМПАС выполнено (требуется донастройка команд создания документов)",
            )
        except Exception as exc:  # noqa: BLE001
            # ВАЖНО: не создаём .cdw/.spw фейковым содержимым, чтобы КОМПАС не пытался открыть их как валидные документы.
            fallback_cdw_payload_path = output_dir / f"{project}.cdw.fallback.json"
            fallback_spw_payload_path = output_dir / f"{project}.spw.fallback.json"

            cdw_payload = {
                "format": "cdw-fallback-payload",
                "note": "Это не файл КОМПАС. Используется как диагностический payload для dev-среды без COM API.",
                "package": package,
            }
            spw_payload = {
                "format": "spw-fallback-payload",
                "note": "Это не файл КОМПАС. Используется как диагностический payload для dev-среды без COM API.",
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
                message=f"COM API недоступен: {exc}. Созданы только fallback payload-файлы (.fallback.json).",
            )
