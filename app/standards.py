from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class StandardRule:
    code: str
    title: str
    category: str
    must_have: list[str]


DEFAULT_RULES = [
    StandardRule(
        code="ГОСТ 2.104",
        title="Основные надписи",
        category="ЕСКД",
        must_have=["основная надпись", "обозначение документа", "масштаб"],
    ),
    StandardRule(
        code="ГОСТ 2.109",
        title="Основные требования к чертежам",
        category="ЕСКД",
        must_have=["виды", "разрезы", "сечения", "размеры"],
    ),
    StandardRule(
        code="ГОСТ 2.307",
        title="Нанесение размеров и предельных отклонений",
        category="ЕСКД",
        must_have=["размерные линии", "выносные линии", "единицы измерения"],
    ),
    StandardRule(
        code="ГОСТ 2.108",
        title="Спецификация",
        category="ЕСКД",
        must_have=["позиции", "обозначение", "наименование", "количество"],
    ),
]


def validate_package(package: dict[str, Any]) -> list[str]:
    """Возвращает список предупреждений по обязательным полям стандартов."""
    text_blob = " ".join(str(v).lower() for v in package.values())
    warnings: list[str] = []

    for rule in DEFAULT_RULES:
        missing = [item for item in rule.must_have if item.lower() not in text_blob]
        if missing:
            warnings.append(
                f"{rule.code} ({rule.title}): отсутствуют ключевые элементы: {', '.join(missing)}"
            )

    warnings.extend(validate_designations_and_tolerances(package))
    warnings.extend(validate_specification(package))
    return warnings


def validate_designations_and_tolerances(package: dict[str, Any]) -> list[str]:
    """Проверка обозначений, допусков и единиц измерения."""
    notes = str(package.get("notes", "")).lower()
    text_blob = " ".join(str(v).lower() for v in package.values())
    warnings: list[str] = []

    if "обозначение" not in text_blob:
        warnings.append("Обозначение документа/узла не найдено в пакете")
    if "допуск" not in text_blob and "h7" not in text_blob and "js" not in text_blob:
        warnings.append("Не найдено указание допусков/посадок")
    if "мм" not in text_blob and "миллиметр" not in text_blob and "единицы измерения" not in notes:
        warnings.append("Не указаны единицы измерения (рекомендуется мм)")

    return warnings


def validate_specification(package: dict[str, Any]) -> list[str]:
    items = package.get("specification_items", [])
    if not isinstance(items, list) or not items:
        return ["Спецификация пуста или не заполнена"]

    warnings: list[str] = []
    required = {"Позиция", "Обозначение", "Наименование", "Кол-во"}

    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            warnings.append(f"Строка спецификации #{idx} имеет неверный формат")
            continue
        missing = [field for field in required if field not in item or not str(item.get(field, "")).strip()]
        if missing:
            warnings.append(f"Строка спецификации #{idx}: отсутствуют поля {', '.join(missing)}")

    return warnings


def rules_as_dict() -> list[dict[str, Any]]:
    return [asdict(rule) for rule in DEFAULT_RULES]
