from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SharedFinding:
    role: str
    finding_id: str
    severity: str
    summary: str


@dataclass(frozen=True)
class SpecialistFinding:
    finding_id: str
    severity: str
    summary: str
    private_data: dict[str, Any]


@dataclass(frozen=True)
class Handoff:
    role: str
    finding_id: str
    severity: str
    summary: str


@dataclass(frozen=True)
class ReleaseState:
    release_id: str
    change_summary: str
    risk_level: str
    security_notes: dict[str, Any]
    build_metrics: dict[str, Any]
    ui_report: dict[str, Any]
    findings: tuple[SharedFinding, ...] = ()
    handoffs: tuple[Handoff, ...] = ()


@dataclass(frozen=True)
class SpecialistSpec:
    role: str
    reviewer: Callable[[dict[str, Any]], SpecialistFinding]


@dataclass(frozen=True)
class SpecialistResult:
    role: str
    status: str
    finding_id: str | None
    error: str | None


@dataclass(frozen=True)
class CrewResult:
    results: tuple[SpecialistResult, ...]
    findings: tuple[SharedFinding, ...]
    handoffs: tuple[Handoff, ...]


ROLE_FIELD_ALLOWLISTS = {
    "security": ("release_id", "change_summary", "risk_level", "security_notes"),
    "reliability": ("release_id", "change_summary", "build_metrics", "findings", "handoffs"),
    "accessibility": ("release_id", "change_summary", "ui_report", "findings", "handoffs"),
}
