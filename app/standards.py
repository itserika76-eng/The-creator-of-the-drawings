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

    return warnings


def rules_as_dict() -> list[dict[str, Any]]:
    return [asdict(rule) for rule in DEFAULT_RULES]
