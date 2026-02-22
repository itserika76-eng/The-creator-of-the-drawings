from __future__ import annotations

import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


try:
    from .cv_ocr import CVOCRPipeline
    from .kompas_api import KompasExporter
    from .legal_update import LegalRegistryUpdater
    from .rag import StandardsRAG, hits_as_dict
    from .standards import validate_package, rules_as_dict
except ImportError:
    from cv_ocr import CVOCRPipeline
    from kompas_api import KompasExporter
    from legal_update import LegalRegistryUpdater
    from rag import StandardsRAG, hits_as_dict
    from standards import validate_package, rules_as_dict


@dataclass
class BuildResult:
    package_path: Path
    specification_path: Path
    macro_template_path: Path
    cdw_path: Path | None
    spw_path: Path | None
    fallback_cdw_payload_path: Path | None
    fallback_spw_payload_path: Path | None
    warnings: list[str]
    opened_in_kompas: bool
    open_message: str


class DrawingEngine:
    """Ядро прототипа: формирует пакет данных и запускает экспорт в КОМПАС-3D."""

    def __init__(self, compas_executable: Path, output_dir: Path) -> None:
        self.compas_executable = compas_executable
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.cv_pipeline = CVOCRPipeline()
        self.rag = StandardsRAG(Path(__file__).parent / "data" / "standards")
        self.registry_updater = LegalRegistryUpdater(
            registry_path=Path(__file__).parent / "data" / "standards_registry.json",
            docs_dir=self.output_dir,
        )
        self.kompas_exporter = KompasExporter(compas_executable=compas_executable)

    def build_from_image(self, image_path: Path, project_name: str) -> BuildResult:
        cv_result = self.cv_pipeline.analyze_drawing_image(image_path)
        rag_hits = self.rag.retrieve(f"{project_name} ГОСТ ЕСКД рамка спецификация", top_k=3)

        package: dict[str, Any] = {
            "project_name": project_name,
            "source": "image",
            "image_path": str(image_path),
            "cv_ocr": self.cv_pipeline.to_dict(cv_result),
            "detected_entities": cv_result.entities,
            "reference_standards_hits": hits_as_dict(rag_hits),
            "specification_items": [
                {
                    "Позиция": 1,
                    "Обозначение": f"{project_name[:8].upper()}-001",
                    "Наименование": "Сборочная единица",
                    "Кол-во": 1,
                    "Примечание": "Автосоздано",
                }
            ],
            "notes": "Масштаб 1:1, единицы измерения мм, допуск H7 для ключевых посадок.",
            "standard_profile": "ЕСКД",
        }
        if cv_result.warnings:
            package["cv_warnings"] = cv_result.warnings

        return self._persist_artifacts(package)

    def build_from_prompt(self, prompt: str, project_name: str) -> BuildResult:
        facts = self._search_reference_facts(prompt)
        rag_hits = self.rag.retrieve(prompt, top_k=5)

        package: dict[str, Any] = {
            "project_name": project_name,
            "source": "prompt",
            "prompt": prompt,
            "reference_facts": facts,
            "reference_standards_hits": hits_as_dict(rag_hits),
            "detected_entities": [
                "виды",
                "разрезы",
                "сечения",
                "размерные линии",
                "основная надпись",
                "обозначение документа",
            ],
            "specification_items": [
                {
                    "Позиция": 1,
                    "Обозначение": f"{project_name[:8].upper()}-001",
                    "Наименование": "Деталь",
                    "Кол-во": 1,
                    "Примечание": "Сгенерировано по запросу",
                }
            ],
            "notes": "Единицы измерения мм. Указать допуск ±0.1 мм и посадки H7/js6 при необходимости.",
            "standard_profile": "ЕСКД",
        }
        return self._persist_artifacts(package)

    def _search_reference_facts(self, query: str) -> list[dict[str, str]]:
        """Лёгкий онлайн-поиск: извлекает краткую сводку из Wikipedia API."""
        try:
            import json as _json
            import urllib.parse
            import urllib.request

            params = urllib.parse.urlencode({
                "action": "query",
                "list": "search",
                "srsearch": query,
                "utf8": 1,
                "format": "json",
                "srlimit": 3,
            })
            url = f"https://ru.wikipedia.org/w/api.php?{params}"
            with urllib.request.urlopen(url, timeout=10) as response:
                payload = _json.loads(response.read().decode("utf-8"))
            items = payload.get("query", {}).get("search", [])
            return [
                {
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", "").replace("<span class=\"searchmatch\">", "").replace("</span>", ""),
                }
                for item in items
            ]
        except Exception as exc:  # noqa: BLE001
            return [{"title": "Поиск недоступен", "snippet": str(exc)}]

    def _persist_artifacts(self, package: dict[str, Any]) -> BuildResult:
        package["compas_executable"] = str(self.compas_executable)
        package["standards"] = rules_as_dict()

        legal_snapshot = self.registry_updater.update_allowed_sources_snapshot()
        package["legal_sources_snapshot"] = str(legal_snapshot)

        warnings = validate_package(package)

        package_path = self.output_dir / "drawing_package.json"
        with package_path.open("w", encoding="utf-8") as fp:
            json.dump(package, fp, ensure_ascii=False, indent=2)

        specification_path = self.output_dir / "specification.csv"
        with specification_path.open("w", encoding="utf-8", newline="") as fp:
            writer = csv.writer(fp, delimiter=";")
            writer.writerow(["Позиция", "Обозначение", "Наименование", "Кол-во", "Примечание"])
            for item in package.get("specification_items", []):
                writer.writerow(
                    [
                        item.get("Позиция", ""),
                        item.get("Обозначение", ""),
                        item.get("Наименование", ""),
                        item.get("Кол-во", ""),
                        item.get("Примечание", ""),
                    ]
                )

        macro_template_path = self.output_dir / "kompas_macro_template.py"
        with macro_template_path.open("w", encoding="utf-8") as fp:
            fp.write(
                """# Шаблон макроса для КОМПАС-3D
# TODO: заменить на полноценные вызовы API вашей версии КОМПАС

DRAWING_PACKAGE = 'drawing_package.json'
print('Импортируйте пакет в реальный API КОМПАС-3D:', DRAWING_PACKAGE)
"""
            )

        export_result = self.kompas_exporter.export(package=package, output_dir=self.output_dir)
        if not export_result.success:
            warnings.append(export_result.message)

        opened_in_kompas, open_message = self._open_generated_drawing(export_result.native_cdw_path)
        if not opened_in_kompas and open_message:
            warnings.append(open_message)

        return BuildResult(
            package_path=package_path,
            specification_path=specification_path,
            macro_template_path=macro_template_path,
            cdw_path=export_result.native_cdw_path,
            spw_path=export_result.native_spw_path,
            fallback_cdw_payload_path=export_result.fallback_cdw_payload_path,
            fallback_spw_payload_path=export_result.fallback_spw_payload_path,
            warnings=warnings,
            opened_in_kompas=opened_in_kompas,
            open_message=open_message,
        )

    def _open_generated_drawing(self, cdw_path: Path | None) -> tuple[bool, str]:
        if cdw_path is None:
            return False, "Автооткрытие в КОМПАС пропущено: нативный .cdw не создан"

        if not cdw_path.exists():
            return False, f"Автооткрытие в КОМПАС пропущено: файл не найден ({cdw_path})"

        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["cmd", "/c", "start", "", str(self.compas_executable), str(cdw_path)])
            else:
                subprocess.Popen([str(self.compas_executable), str(cdw_path)])
            return True, f"Чертеж открыт в КОМПАС: {cdw_path}"
        except Exception as exc:  # noqa: BLE001
            return False, f"Не удалось автоматически открыть чертеж в КОМПАС: {exc}"
