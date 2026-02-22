from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class KompasExportResult:
    success: bool
    cdw_path: Path
    spw_path: Path
    message: str


class KompasExporter:
    """Экспорт в КОМПАС-3D: COM API на Windows + fallback-файлы в dev-среде."""

    def __init__(self, compas_executable: Path) -> None:
        self.compas_executable = compas_executable

    def export(self, package: dict[str, Any], output_dir: Path) -> KompasExportResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        cdw_path = output_dir / f"{package.get('project_name', 'drawing')}.cdw"
        spw_path = output_dir / f"{package.get('project_name', 'drawing')}.spw"

        try:
            import win32com.client  # type: ignore

            # Базовая попытка подключения к API КОМПАС (может потребовать корректный ProgID для версии)
            app = win32com.client.Dispatch("Kompas.Application.7")
            app.Visible = True

            # Здесь нужен конкретный API конкретной версии КОМПАС.
            # В MVP формируем минимум: файлы-черновики и оставляем след для дальнейшей интеграции.
            cdw_path.write_text(
                "КОМПАС API integration point. Replace with real document creation commands.",
                encoding="utf-8",
            )
            spw_path.write_text(
                "КОМПАС API integration point. Replace with real specification commands.",
                encoding="utf-8",
            )
            return KompasExportResult(True, cdw_path, spw_path, "COM подключение к КОМПАС выполнено")
        except Exception as exc:  # noqa: BLE001
            # Dev fallback: сохраняем сериализованные артефакты в .cdw/.spw как трассировку пайплайна
            cdw_payload = {
                "format": "cdw-fallback",
                "note": "Это fallback для среды без COM API КОМПАС",
                "package": package,
            }
            spw_payload = {
                "format": "spw-fallback",
                "spec_items": package.get("specification_items", []),
            }
            cdw_path.write_text(json.dumps(cdw_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            spw_path.write_text(json.dumps(spw_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return KompasExportResult(False, cdw_path, spw_path, f"COM API недоступен: {exc}")
