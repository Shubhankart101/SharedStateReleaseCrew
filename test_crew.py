"""Unit and integration tests for Shared-State Release Crew."""

from __future__ import annotations

import copy
from typing import Any
import pytest

from main import make_handoff, make_role_input, run_crew, run_declared_sequence
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


@pytest.fixture
def sample_state() -> ReleaseState:
    return ReleaseState(
        release_id="REL-2026-001",
        change_summary="Refactor authentication middleware and optimize DB queries",
        risk_level="high",
        security_notes={
            "auth_type": "OAuth2",
            "token_ttl_seconds": 3600,
            "secret_storage": "vault",
        },
        build_metrics={
            "coverage_pct": 87.5,
            "p99_latency_ms": 120,
            "error_rate_pct": 0.02,
        },
        ui_report={
            "contrast_ratio": 4.8,
            "aria_compliance": True,
            "focusable_elements": 42,
        },
        findings=(),
        handoffs=(),
    )


class TestMakeRoleInput:
    """Tests for make_role_input (TODO 1)."""

    def test_returns_only_allowed_fields_present_in_state(self, sample_state: ReleaseState):
        allowed = ("release_id", "security_notes")
        result = make_role_input(sample_state, allowed)

        assert set(result.keys()) == {"release_id", "security_notes"}
        assert result["release_id"] == "REL-2026-001"
        assert result["security_notes"] == sample_state.security_notes

    def test_omits_unlisted_fields(self, sample_state: ReleaseState):
        allowed = ("release_id",)
        result = make_role_input(sample_state, allowed)

        assert "change_summary" not in result
        assert "risk_level" not in result
        assert "security_notes" not in result
        assert "build_metrics" not in result
        assert "ui_report" not in result

    def test_ignores_allowed_fields_not_present_in_state(self, sample_state: ReleaseState):
        allowed = ("release_id", "non_existent_field", "another_unknown")
        result = make_role_input(sample_state, allowed)

        assert set(result.keys()) == {"release_id"}

    def test_empty_allowed_fields_returns_empty_dict(self, sample_state: ReleaseState):
        result = make_role_input(sample_state, ())
        assert result == {}

    def test_none_state_returns_empty_dict(self):
        assert make_role_input(None, ("release_id",)) == {}

    def test_deep_copy_prevents_state_mutation(self, sample_state: ReleaseState):
        allowed = ("security_notes", "build_metrics")
        result = make_role_input(sample_state, allowed)

        # Mutate the dictionary returned to the specialist
        result["security_notes"]["token_ttl_seconds"] = 999999
        result["security_notes"]["new_malicious_key"] = "injected"
        result["build_metrics"]["coverage_pct"] = 0.0

        # Verify sample_state was not modified
        assert sample_state.security_notes["token_ttl_seconds"] == 3600
        assert "new_malicious_key" not in sample_state.security_notes
        assert sample_state.build_metrics["coverage_pct"] == 87.5

    def test_security_allowlist_fields(self, sample_state: ReleaseState):
        sec_allowed = ROLE_FIELD_ALLOWLISTS["security"]
        result = make_role_input(sample_state, sec_allowed)

        assert set(result.keys()) == set(sec_allowed)
        assert "build_metrics" not in result
        assert "ui_report" not in result
        assert "findings" not in result
        assert "handoffs" not in result

    def test_reliability_allowlist_fields(self, sample_state: ReleaseState):
        rel_allowed = ROLE_FIELD_ALLOWLISTS["reliability"]
        result = make_role_input(sample_state, rel_allowed)

        assert set(result.keys()) == set(rel_allowed)
        assert "security_notes" not in result
        assert "ui_report" not in result

    def test_accessibility_allowlist_fields(self, sample_state: ReleaseState):
        a11y_allowed = ROLE_FIELD_ALLOWLISTS["accessibility"]
        result = make_role_input(sample_state, a11y_allowed)

        assert set(result.keys()) == set(a11y_allowed)
        assert "security_notes" not in result
        assert "build_metrics" not in result


class TestMakeHandoff:
    """Tests for make_handoff (TODO 2)."""

    def test_creates_bounded_handoff_with_required_fields(self):
        finding = SpecialistFinding(
            finding_id="SEC-001",
            severity="CRITICAL",
            summary="Hardcoded secret key detected in migration script",
            private_data={"raw_payload": "secret-12345", "line": 42},
        )

        handoff = make_handoff("security", finding)

        assert isinstance(handoff, Handoff)
        assert handoff.role == "security"
        assert handoff.finding_id == "SEC-001"
        assert handoff.severity == "CRITICAL"
        assert handoff.summary == "Hardcoded secret key detected in migration script"

    def test_excludes_private_data(self):
        finding = SpecialistFinding(
            finding_id="REL-002",
            severity="MEDIUM",
            summary="Query latency exceeds budget by 15%",
            private_data={"db_connection_str": "postgres://user:pass@internal:5432/db"},
        )

        handoff = make_handoff("reliability", finding)

        assert not hasattr(handoff, "private_data")
        assert "db_connection_str" not in str(handoff)

    def test_dict_finding_support(self):
        finding_dict = {
            "finding_id": "DICT-1",
            "severity": "LOW",
            "summary": "Summary from dict",
            "private_data": {"secret": True},
        }
        handoff = make_handoff("custom", finding_dict)
        assert handoff.finding_id == "DICT-1"
        assert handoff.role == "custom"
        assert not hasattr(handoff, "private_data")


class TestRunCrew:
    """Tests for run_crew and run_declared_sequence (TODO 3)."""

    def test_empty_specialist_sequence_returns_empty_tuples(self, sample_state: ReleaseState):
        crew_result = run_crew(sample_state, ())

        assert isinstance(crew_result, CrewResult)
        assert crew_result.results == ()
        assert crew_result.findings == ()
        assert crew_result.handoffs == ()

    def test_successful_ordered_sequence_execution(self, sample_state: ReleaseState):
        call_order = []

        def security_reviewer(data: dict[str, Any]) -> SpecialistFinding:
            call_order.append("security")
            assert "security_notes" in data
            assert "build_metrics" not in data
            return SpecialistFinding(
                finding_id="FIND-SEC",
                severity="HIGH",
                summary="Missing rate limiter",
                private_data={"exploit_poc": "curl ..."},
            )

        def reliability_reviewer(data: dict[str, Any]) -> SpecialistFinding:
            call_order.append("reliability")
            assert "build_metrics" in data
            assert "security_notes" not in data
            assert "findings" in data
            assert len(data["findings"]) == 1
            assert data["findings"][0].finding_id == "FIND-SEC"
            return SpecialistFinding(
                finding_id="FIND-REL",
                severity="LOW",
                summary="Memory usage is stable",
                private_data={"stack_dump": "..."},
            )

        def accessibility_reviewer(data: dict[str, Any]) -> SpecialistFinding:
            call_order.append("accessibility")
            assert "ui_report" in data
            assert "findings" in data
            assert len(data["findings"]) == 2
            return SpecialistFinding(
                finding_id="FIND-A11Y",
                severity="INFO",
                summary="All elements properly tagged",
                private_data={"dom_snapshot": "..."},
            )

        specs = (
            SpecialistSpec(role="security", reviewer=security_reviewer),
            SpecialistSpec(role="reliability", reviewer=reliability_reviewer),
            SpecialistSpec(role="accessibility", reviewer=accessibility_reviewer),
        )

        result = run_crew(sample_state, specs)

        assert call_order == ["security", "reliability", "accessibility"]
        assert len(result.results) == 3
        assert len(result.findings) == 3
        assert len(result.handoffs) == 3

        # Verify results
        assert result.results[0] == SpecialistResult(
            role="security", status="completed", finding_id="FIND-SEC", error=None
        )
        assert result.results[1] == SpecialistResult(
            role="reliability", status="completed", finding_id="FIND-REL", error=None
        )
        assert result.results[2] == SpecialistResult(
            role="accessibility", status="completed", finding_id="FIND-A11Y", error=None
        )

        # Verify shared findings
        assert result.findings[0] == SharedFinding(
            role="security", finding_id="FIND-SEC", severity="HIGH", summary="Missing rate limiter"
        )
        assert result.findings[1] == SharedFinding(
            role="reliability", finding_id="FIND-REL", severity="LOW", summary="Memory usage is stable"
        )
        assert result.findings[2] == SharedFinding(
            role="accessibility", finding_id="FIND-A11Y", severity="INFO", summary="All elements properly tagged"
        )

        # Verify handoffs
        assert result.handoffs[0] == Handoff(
            role="security", finding_id="FIND-SEC", severity="HIGH", summary="Missing rate limiter"
        )

    def test_reverse_sequence_order_is_respected(self, sample_state: ReleaseState):
        call_order = []

        def accessibility_reviewer(data: dict[str, Any]) -> SpecialistFinding:
            call_order.append("accessibility")
            return SpecialistFinding("A1", "LOW", "A11y OK", {})

        def security_reviewer(data: dict[str, Any]) -> SpecialistFinding:
            call_order.append("security")
            assert "findings" not in data
            return SpecialistFinding("S1", "HIGH", "Sec OK", {})

        specs = (
            SpecialistSpec(role="accessibility", reviewer=accessibility_reviewer),
            SpecialistSpec(role="security", reviewer=security_reviewer),
        )

        result = run_crew(sample_state, specs)

        assert call_order == ["accessibility", "security"]
        assert len(result.results) == 2
        assert result.results[0].role == "accessibility"
        assert result.results[1].role == "security"

    def test_specialist_exception_records_failure_and_continues(self, sample_state: ReleaseState):
        call_order = []

        def security_reviewer(data: dict[str, Any]) -> SpecialistFinding:
            call_order.append("security")
            return SpecialistFinding("SEC-OK", "LOW", "Good", {})

        def faulty_reviewer(data: dict[str, Any]) -> SpecialistFinding:
            call_order.append("reliability")
            raise RuntimeError("Database connection timed out during analysis")

        def accessibility_reviewer(data: dict[str, Any]) -> SpecialistFinding:
            call_order.append("accessibility")
            assert "findings" in data
            assert len(data["findings"]) == 1
            assert data["findings"][0].finding_id == "SEC-OK"
            return SpecialistFinding("A11Y-OK", "INFO", "Contrast fine", {})

        specs = (
            SpecialistSpec(role="security", reviewer=security_reviewer),
            SpecialistSpec(role="reliability", reviewer=faulty_reviewer),
            SpecialistSpec(role="accessibility", reviewer=accessibility_reviewer),
        )

        result = run_crew(sample_state, specs)

        assert call_order == ["security", "reliability", "accessibility"]
        assert len(result.results) == 3

        # First specialist succeeded
        assert result.results[0] == SpecialistResult(
            role="security", status="completed", finding_id="SEC-OK", error=None
        )

        # Second specialist failed with exact error "specialist_failed"
        assert result.results[1] == SpecialistResult(
            role="reliability", status="failed", finding_id=None, error="specialist_failed"
        )

        # Third specialist succeeded
        assert result.results[2] == SpecialistResult(
            role="accessibility", status="completed", finding_id="A11Y-OK", error=None
        )

        # Only 2 findings and handoffs accumulated (failed one contributed nothing)
        assert len(result.findings) == 2
        assert result.findings[0].finding_id == "SEC-OK"
        assert result.findings[1].finding_id == "A11Y-OK"
        assert len(result.handoffs) == 2

    def test_all_specialists_fail(self, sample_state: ReleaseState):
        specs = (
            SpecialistSpec(role="security", reviewer=lambda d: 1 / 0),
            SpecialistSpec(role="reliability", reviewer=lambda d: (_ for _ in ()).throw(ValueError("boom"))),
        )
        result = run_crew(sample_state, specs)

        assert len(result.results) == 2
        assert all(r.status == "failed" for r in result.results)
        assert all(r.error == "specialist_failed" for r in result.results)
        assert result.findings == ()
        assert result.handoffs == ()

    def test_no_private_data_leaks_into_crew_result(self, sample_state: ReleaseState):
        private_secret = "SUPER_SECRET_PAYLOAD_98765"

        def sec_reviewer(data: dict[str, Any]) -> SpecialistFinding:
            return SpecialistFinding(
                finding_id="S-1",
                severity="HIGH",
                summary="Public summary",
                private_data={"key": private_secret},
            )

        specs = (SpecialistSpec(role="security", reviewer=sec_reviewer),)
        result = run_crew(sample_state, specs)

        result_str = str(result)
        assert private_secret not in result_str

    def test_pre_existing_findings_preserved(self, sample_state: ReleaseState):
        existing_finding = SharedFinding("pre", "F-0", "LOW", "Pre-existing")
        existing_handoff = Handoff("pre", "F-0", "LOW", "Pre-existing")
        state_with_history = ReleaseState(
            release_id=sample_state.release_id,
            change_summary=sample_state.change_summary,
            risk_level=sample_state.risk_level,
            security_notes=sample_state.security_notes,
            build_metrics=sample_state.build_metrics,
            ui_report=sample_state.ui_report,
            findings=(existing_finding,),
            handoffs=(existing_handoff,),
        )

        specs = (
            SpecialistSpec(
                role="security",
                reviewer=lambda d: SpecialistFinding("S-1", "HIGH", "New", {}),
            ),
        )
        result = run_crew(state_with_history, specs)

        assert len(result.findings) == 2
        assert result.findings[0] == existing_finding
        assert result.findings[1].finding_id == "S-1"
        assert len(result.handoffs) == 2
        assert result.handoffs[0] == existing_handoff
        assert result.handoffs[1].finding_id == "S-1"

    def test_original_state_never_mutated(self, sample_state: ReleaseState):
        def mutator_reviewer(data: dict[str, Any]) -> SpecialistFinding:
            if "security_notes" in data:
                data["security_notes"]["injected"] = "bad"
            return SpecialistFinding("M-1", "INFO", "Done", {"sensitive": 123})

        specs = (SpecialistSpec(role="security", reviewer=mutator_reviewer),)
        result = run_crew(sample_state, specs)

        assert "injected" not in sample_state.security_notes
        assert sample_state.findings == ()
        assert sample_state.handoffs == ()
        assert len(result.findings) == 1

    def test_run_declared_sequence_alias(self, sample_state: ReleaseState):
        specs = (
            SpecialistSpec(
                role="security",
                reviewer=lambda d: SpecialistFinding("S-1", "LOW", "Summary", {}),
            ),
        )
        res1 = run_crew(sample_state, specs)
        res2 = run_declared_sequence(sample_state, specs)

        assert res1 == res2
