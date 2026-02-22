from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class RegistrySource:
    code: str
    title: str
    url: str
    license: str
    use_policy: str


class LegalRegistryUpdater:
    """Юридически корректный контур обновления нормативной базы.

    Обновление выполняется только из источников, явно указанных в реестре и разрешённых лицензией.
    """

    def __init__(self, registry_path: Path, docs_dir: Path) -> None:
        self.registry_path = registry_path
        self.docs_dir = docs_dir
        self.docs_dir.mkdir(parents=True, exist_ok=True)

    def load_registry(self) -> list[RegistrySource]:
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        sources = payload.get("sources", [])
        return [RegistrySource(**src) for src in sources]

    def update_allowed_sources_snapshot(self) -> Path:
        sources = self.load_registry()
        snapshot = {
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
            "items": [src.__dict__ for src in sources if "разреш" in src.use_policy.lower()],
        }
        out = self.docs_dir / "legal_sources_snapshot.json"
        out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        return out
