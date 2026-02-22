from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from standards import validate_package, rules_as_dict


@dataclass
class BuildResult:
    package_path: Path
    specification_path: Path
    macro_template_path: Path
    warnings: list[str]


class DrawingEngine:
    """Ядро прототипа: формирует пакет данных, пригодный для импорта в КОМПАС-3D."""

    def __init__(self, compas_executable: Path, output_dir: Path) -> None:
        self.compas_executable = compas_executable
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def build_from_image(self, image_path: Path, project_name: str) -> BuildResult:
        package: dict[str, Any] = {
            "project_name": project_name,
            "source": "image",
            "image_path": str(image_path),
            "detected_entities": [
                "контур",
                "размерные линии",
                "осевая линия",
                "основная надпись",
            ],
            "notes": "MVP: подключите CV/OCR для реального распознавания геометрии.",
            "standard_profile": "ЕСКД",
        }
        return self._persist_artifacts(package)

    def build_from_prompt(self, prompt: str, project_name: str) -> BuildResult:
        facts = self._search_reference_facts(prompt)
        package: dict[str, Any] = {
            "project_name": project_name,
            "source": "prompt",
            "prompt": prompt,
            "reference_facts": facts,
            "detected_entities": ["вид спереди", "разрез А-А", "размерные линии", "спецификация"],
            "notes": "MVP: генерация геометрии должна быть доработана CAD-модулем.",
            "standard_profile": "ЕСКД",
        }
        return self._persist_artifacts(package)

    def _search_reference_facts(self, query: str) -> list[dict[str, str]]:
        """Лёгкий онлайн-поиск: извлекает краткую сводку из Wikipedia API."""
        try:
            response = requests.get(
                "https://ru.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "utf8": 1,
                    "format": "json",
                    "srlimit": 3,
                },
                timeout=10,
            )
            response.raise_for_status()
            items = response.json().get("query", {}).get("search", [])
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

        warnings = validate_package(package)

        package_path = self.output_dir / "drawing_package.json"
        with package_path.open("w", encoding="utf-8") as fp:
            json.dump(package, fp, ensure_ascii=False, indent=2)

        specification_path = self.output_dir / "specification.csv"
        with specification_path.open("w", encoding="utf-8", newline="") as fp:
            writer = csv.writer(fp, delimiter=";")
            writer.writerow(["Позиция", "Обозначение", "Наименование", "Кол-во", "Примечание"])
            writer.writerow([1, "MVP-001", "Сборочная единица", 1, "Автосоздано прототипом"])

        macro_template_path = self.output_dir / "kompas_macro_template.py"
        with macro_template_path.open("w", encoding="utf-8") as fp:
            fp.write(
                """# Шаблон макроса для КОМПАС-3D\n"
                "# TODO: подключить официальный API АСКОН и импорт drawing_package.json\n"
                "\n"
                "DRAWING_PACKAGE = 'drawing_package.json'\n"
                "print('Импортируйте пакет в реальный API КОМПАС-3D:', DRAWING_PACKAGE)\n"
                """
            )

        return BuildResult(
            package_path=package_path,
            specification_path=specification_path,
            macro_template_path=macro_template_path,
            warnings=warnings,
        )
