from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PROJECT_FORMAT = "SilverStar_FLP_Project"
PROJECT_VERSION = 1


@dataclass(slots=True)
class ProjectDocument:
    log_references: list[str] = field(default_factory=list)
    active_log_index: int = 0
    replay_configurations: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: str = ""
    ui_state: dict[str, Any] = field(default_factory=dict)
    project_path: Path | None = None

    def LogReference_Add(self, log_path: Path) -> None:
        path = Path(log_path).resolve()
        reference = self._Reference_Encode(path)
        if reference not in self.log_references:
            self.log_references.append(reference)

    def LogPaths_Resolve(self) -> tuple[Path, ...]:
        return tuple(self._Reference_Decode(reference) for reference in self.log_references)

    def _Reference_Encode(self, log_path: Path) -> str:
        if self.project_path is None:
            return str(log_path)
        try:
            return str(log_path.relative_to(self.project_path.parent.resolve()))
        except ValueError:
            return str(log_path)

    def _Reference_Decode(self, reference: str) -> Path:
        path = Path(reference)
        if path.is_absolute() or self.project_path is None:
            return path
        return (self.project_path.parent / path).resolve()


def Project_Save(document: ProjectDocument, path: Path) -> None:
    project_path = Path(path).resolve()
    project_path.parent.mkdir(parents=True, exist_ok=True)
    document.project_path = project_path
    payload = {
        "format": PROJECT_FORMAT,
        "version": PROJECT_VERSION,
        "log_references": list(document.log_references),
        "active_log_index": document.active_log_index,
        "replay_configurations": document.replay_configurations,
        "notes": document.notes,
        "ui_state": document.ui_state,
    }
    temporary_path = project_path.with_suffix(project_path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(project_path)


def Project_Load(path: Path) -> ProjectDocument:
    project_path = Path(path).resolve()
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    if payload.get("format") != PROJECT_FORMAT:
        raise ValueError("project_format_invalid")
    if int(payload.get("version", 0)) != PROJECT_VERSION:
        raise ValueError("project_version_unsupported")
    return ProjectDocument(
        log_references=[str(value) for value in payload.get("log_references", [])],
        active_log_index=int(payload.get("active_log_index", 0)),
        replay_configurations=dict(payload.get("replay_configurations", {})),
        notes=str(payload.get("notes", "")),
        ui_state=dict(payload.get("ui_state", {})),
        project_path=project_path,
    )


def Project_ToDict(document: ProjectDocument) -> dict[str, Any]:
    payload = asdict(document)
    payload["project_path"] = (
        str(document.project_path) if document.project_path is not None else None
    )
    return payload
