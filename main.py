"""Shared-State Release Crew.

Three supplied specialists inspect a release candidate in declared order.
Complete only make_role_input, make_handoff, and run_crew.

The state, finding, handoff, result types, role field allow-lists, specialist
wrappers, and Groq-compatible specialist are supplied. Pytest uses deterministic
callables, so no provider or network access is required.

Required behavior:
- make_role_input returns a new dictionary containing only allowed state fields,
  with copied values that cannot mutate the original state.
- make_handoff returns only role, finding_id, severity, and summary.
- run_crew follows the supplied specialist sequence, not a hard-coded role order.
- Each specialist receives only fields allowed for its role.
- Normalize every successful finding into SharedFinding using the executing role;
  never copy private_data into shared state or handoffs.
- Accumulate findings and handoffs without overwriting earlier work.
- Return exactly one SpecialistResult per supplied specialist.
- If one specialist raises an exception, record status="failed" and continue.

Not required: choosing a framework, generating personas, parallel execution,
debate rounds, real model calls during evaluation, or deployment.
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Any

from utils.models import (
    ROLE_FIELD_ALLOWLISTS,
    CrewResult,
    Handoff,
    ReleaseState,
    SharedFinding,
    SpecialistFinding,
    SpecialistResult,
    SpecialistSpec,
)


def make_role_input(state: ReleaseState, allowed_fields: tuple[str, ...]) -> dict[str, Any]:
    # TODO 1: Return a new dictionary containing only allowed_fields that are
    # present in state. Copy mutable values deeply enough that a specialist
    # cannot change the caller-owned ReleaseState through its input.
    if state is None or not allowed_fields:
        return {}

    role_input: dict[str, Any] = {}
    if dataclasses.is_dataclass(state):
        valid_fields = {f.name for f in dataclasses.fields(state)}
        for field in allowed_fields:
            if field in valid_fields:
                role_input[field] = copy.deepcopy(getattr(state, field))
    elif isinstance(state, dict):
        for field in allowed_fields:
            if field in state:
                role_input[field] = copy.deepcopy(state[field])
    else:
        for field in allowed_fields:
            if hasattr(state, field) and not field.startswith("_"):
                val = getattr(state, field)
                if not callable(val):
                    role_input[field] = copy.deepcopy(val)

    return role_input


def make_handoff(role: str, finding: SpecialistFinding) -> Handoff:
    # TODO 2: Construct Handoff with only role, finding_id, severity, and
    # summary. Never include finding.private_data.
    finding_id = (
        getattr(finding, "finding_id", None)
        if not isinstance(finding, dict)
        else finding.get("finding_id")
    )
    severity = (
        getattr(finding, "severity", None)
        if not isinstance(finding, dict)
        else finding.get("severity")
    )
    summary = (
        getattr(finding, "summary", None)
        if not isinstance(finding, dict)
        else finding.get("summary")
    )

    return Handoff(
        role=role,
        finding_id=finding_id,
        severity=severity,
        summary=summary,
    )


def run_declared_sequence(
    initial_state: ReleaseState,
    specialists: tuple[SpecialistSpec, ...],
) -> CrewResult:
    """Sequential runner executing specialists in declared order."""
    if not specialists:
        return CrewResult(results=(), findings=(), handoffs=())

    accumulated_findings: list[SharedFinding] = list(getattr(initial_state, "findings", ()))
    accumulated_handoffs: list[Handoff] = list(getattr(initial_state, "handoffs", ()))
    results: list[SpecialistResult] = []

    current_state = initial_state

    for spec in specialists:
        role = getattr(spec, "role", None) if not isinstance(spec, dict) else spec.get("role")
        reviewer = (
            getattr(spec, "reviewer", None)
            if not isinstance(spec, dict)
            else spec.get("reviewer")
        )

        allowed_fields = ROLE_FIELD_ALLOWLISTS.get(role, ())

        try:
            role_input = make_role_input(current_state, allowed_fields)
            finding = reviewer(role_input)

            finding_id = (
                getattr(finding, "finding_id", None)
                if not isinstance(finding, dict)
                else finding.get("finding_id")
            )
            severity = (
                getattr(finding, "severity", None)
                if not isinstance(finding, dict)
                else finding.get("severity")
            )
            summary = (
                getattr(finding, "summary", None)
                if not isinstance(finding, dict)
                else finding.get("summary")
            )

            shared_finding = SharedFinding(
                role=role,
                finding_id=finding_id,
                severity=severity,
                summary=summary,
            )
            handoff = make_handoff(role, finding)

            accumulated_findings.append(shared_finding)
            accumulated_handoffs.append(handoff)

            if dataclasses.is_dataclass(current_state):
                current_state = dataclasses.replace(
                    current_state,
                    findings=tuple(accumulated_findings),
                    handoffs=tuple(accumulated_handoffs),
                )
            elif isinstance(current_state, dict):
                current_state = dict(
                    current_state,
                    findings=tuple(accumulated_findings),
                    handoffs=tuple(accumulated_handoffs),
                )

            results.append(
                SpecialistResult(
                    role=role,
                    status="completed",
                    finding_id=finding_id,
                    error=None,
                )
            )
        except Exception:
            results.append(
                SpecialistResult(
                    role=role,
                    status="failed",
                    finding_id=None,
                    error="specialist_failed",
                )
            )

    return CrewResult(
        results=tuple(results),
        findings=tuple(accumulated_findings),
        handoffs=tuple(accumulated_handoffs),
    )


def run_crew(
    initial_state: ReleaseState,
    specialists: tuple[SpecialistSpec, ...],
) -> CrewResult:
    # TODO 3: Process the supplied specialist sequence in order. Build each
    # role's allowlisted input, normalize successful findings with the executing
    # role, accumulate shared findings and handoffs, record exactly one result
    # per specialist, and continue after an exception with status="failed".
    return run_declared_sequence(initial_state, specialists)
