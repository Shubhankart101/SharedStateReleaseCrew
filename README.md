# Shared-State Release Crew

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/pytest-21%20passed-brightgreen.svg)](test_crew.py)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Architecture: LangGraph Sequential Shell](https://img.shields.io/badge/Architecture-LangGraph%20Sequential%20Shell-purple.svg)](#architecture--dataflow)

A modular, privacy-preserving software release review crew. Configured security, reliability, and accessibility specialists inspect a release candidate in a declared sequence. Each specialist is restricted to approved state fields via role-based allow-lists, and only bounded public findings and handoffs enter shared state while strictly isolating private specialist data.

---

## 📌 Problem Overview

In modern multi-agent software governance and CI/CD automation, orchestrating sequential specialist reviews introduces critical state management and privacy challenges:

1. **State Mutation & Context Pollution:** Injected specialist agents or tools may inadvertently mutate caller-owned release state or attempt to alter shared records directly.
2. **Data Leakage & Sensitive Context:** Specialists frequently collect proprietary traces, memory dumps, or credentials (`private_data`) during analysis. Exposing these private diagnostics to subsequent specialists or public dashboards violates compliance and least-privilege security boundaries.
3. **Information Asymmetry & Least-Privilege Access:** Each specialist role has distinct visibility requirements. For example, security specialists evaluate initial risk notes without bias from other specialists, while reliability and accessibility specialists must review previously accumulated findings and handoffs to detect cross-cutting regressions.
4. **Fragile Sequence Execution:** In unmanaged multi-agent pipelines, a failure or exception raised by one specialist (e.g. database timeout, rate limit, unhandled syntax) can crash the entire pipeline, erasing previously validated findings and preventing downstream specialists from running.

### Design Principles

- **Strict State Immutability:** Uses deep copying (`copy.deepcopy`) on all filtered state fields so specialists can never mutate caller-owned `ReleaseState` dictionaries.
- **Bounded Handoffs:** Strips away all specialist `private_data`, normalizing findings strictly into public `SharedFinding` and `Handoff` records (`role`, `finding_id`, `severity`, `summary`).
- **Dynamic Declared Ordering:** Respects any declared sequence of `SpecialistSpec` entries without hard-coding an execution sequence.
- **Fault-Tolerant Continuation:** Catches exceptions from failing specialists, logs a structured `SpecialistResult(role, status="failed", finding_id=None, error="specialist_failed")`, and seamlessly proceeds with remaining specialists without losing accumulated findings.
- **Deterministic & Zero-Dependency Testing:** Decouples runner logic from live LLM backends so unit and integration test suites execute deterministically in milliseconds without API keys or external services.

---

## 🏗️ Architecture & Dataflow

```
                    +--------------------------------+
                    | Initial ReleaseState (Frozen)  |
                    +---------------+----------------+
                                    |
                    +---------------+----------------+
                    |      for spec in specialists   | <-------------------------+
                    +---------------+----------------+                           |
                                    |                                            |
            +-----------------------v-----------------------+                    |
            | TODO 1: make_role_input(current_state, allow) |                    |
            |  - Filter by ROLE_FIELD_ALLOWLISTS            |                    |
            |  - Deep-copy mutable values                   |                    |
            +-----------------------+-----------------------+                    |
                                    | Safe Role Input                            |
            +-----------------------v-----------------------+                    |
            |         Execute Specialist Reviewer           |                    |
            |             spec.reviewer(role_input)         |                    |
            +-----------------------+-----------------------+                    |
                                    |                                            |
                     +--------------+--------------+                             |
                     |                             |                             |
                 [Success]                     [Exception]                       |
                     |                             |                             |
    +----------------v---------------+             |                             |
    | TODO 2: make_handoff(role, f)  |             v                             |
    |  - Exclude private_data        |    +--------------------------------+     |
    |  - SharedFinding normalization |    | Append failed SpecialistResult |     |
    +----------------+---------------+    |  status="failed"               |     |
                     |                    |  error="specialist_failed"     |     |
    +----------------v---------------+    +----------------+---------------+     |
    | Append to Shared Findings &    |                     |                     |
    | Handoffs; Update current_state |                     |                     |
    | Append completed SpecialistRes |                     |                     |
    +----------------+---------------+                     |                     |
                     |                                     |                     |
                     +-------------------------------------+                     |
                                    |                                            |
                                    +--- More specialists in sequence? --- YES --+
                                    |
                                   NO
                                    |
                    +---------------v----------------+
                    |       Return CrewResult        |
                    |  - ordered results             |
                    |  - accumulated findings        |
                    |  - accumulated handoffs        |
                    +--------------------------------+
```

---

## 📋 Role-Specific Field Allow-Lists

Access to release candidate data is governed by strict allow-lists defined in `ROLE_FIELD_ALLOWLISTS`:

| Specialist Role | Allowed Fields | Description |
|---|---|---|
| **`security`** | `release_id`, `change_summary`, `risk_level`, `security_notes` | Restricted to initial security notes, change summary, and risk tier. Conceals prior findings/handoffs to ensure unbiased security audits. |
| **`reliability`** | `release_id`, `change_summary`, `build_metrics`, `findings`, `handoffs` | Inspects build/latency metrics along with earlier public findings and handoffs to evaluate reliability impact. |
| **`accessibility`** | `release_id`, `change_summary`, `ui_report`, `findings`, `handoffs` | Inspects UI/DOM reports along with earlier public findings and handoffs to ensure full WCAG/ARIA compliance. |

---

## ⚙️ Core Functions (`main.py`)

### 1. `make_role_input(state: ReleaseState, allowed_fields: tuple[str, ...]) -> dict[str, Any]`
- Evaluates the provided `allowed_fields` against fields present on `state`.
- Deeply copies (`copy.deepcopy`) every selected value to ensure complete mutation isolation.
- Omits unlisted fields and ignores requested fields not present on `state`.
- Returns a fresh dictionary containing only authorized, copied data.

### 2. `make_handoff(role: str, finding: SpecialistFinding) -> Handoff`
- Extracts public summary attributes: `role`, `finding_id`, `severity`, and `summary`.
- Strictly excludes `SpecialistFinding.private_data` from entering the handoff.
- Returns an immutable `Handoff` dataclass instance.

### 3. `run_declared_sequence(initial_state: ReleaseState, specialists: tuple[SpecialistSpec, ...]) -> CrewResult` / `run_crew`
- Follows the declared `specialists` sequence order dynamically.
- For each specialist:
  - Fetches role-specific allow-lists from `ROLE_FIELD_ALLOWLISTS`.
  - Filters `current_state` with `make_role_input`.
  - Calls `spec.reviewer(role_input)`.
  - On success: normalizes finding into `SharedFinding`, generates bounded `Handoff`, updates `current_state` with accumulated records, and records `SpecialistResult(role, status="completed", finding_id=..., error=None)`.
  - On exception: catches errors safely, appends `SpecialistResult(role, status="failed", finding_id=None, error="specialist_failed")`, preserves existing accumulated findings, and proceeds to the next specialist.
- For an empty sequence (`specialists=()`), returns `CrewResult(results=(), findings=(), handoffs=())`.

---

## 📊 Data Models (`utils/models.py`)

| Model | Kind | Fields | Purpose |
|---|---|---|---|
| `SharedFinding` | Frozen Dataclass | `role`, `finding_id`, `severity`, `summary` | Public finding visible to subsequent specialists who have `"findings"` in their allow-list. |
| `SpecialistFinding` | Frozen Dataclass | `finding_id`, `severity`, `summary`, `private_data` | Raw specialist output containing sensitive private context (`private_data`). |
| `Handoff` | Frozen Dataclass | `role`, `finding_id`, `severity`, `summary` | Bounded public communication record between review stages. |
| `ReleaseState` | Frozen Dataclass | `release_id`, `change_summary`, `risk_level`, `security_notes`, `build_metrics`, `ui_report`, `findings`, `handoffs` | Caller-owned release candidate state. |
| `SpecialistSpec` | Frozen Dataclass | `role`, `reviewer` | Specialist declaration pairing role identifier with reviewer callable. |
| `SpecialistResult` | Frozen Dataclass | `role`, `status`, `finding_id`, `error` | Status outcome per specialist (`"completed"` or `"failed"`). |
| `CrewResult` | Frozen Dataclass | `results`, `findings`, `handoffs` | Comprehensive crew outcome containing ordered results, public findings, and handoffs. |

---

## 🧪 Test Suite & Verification

The test suite (`test_crew.py`) provides 100% specification coverage with 21 unit tests:

```bash
$ pytest -v
============================= test session starts =============================
platform win32 -- Python 3.14.6, pytest-8.4.1, pluggy-1.6.0
rootdir: C:\Users\Dell\OneDrive\Desktop\Assignment\SharedStateReleaseCrew
collected 21 items

test_crew.py::TestMakeRoleInput::test_returns_only_allowed_fields_present_in_state PASSED [  4%]
test_crew.py::TestMakeRoleInput::test_omits_unlisted_fields PASSED       [  9%]
test_crew.py::TestMakeRoleInput::test_ignores_allowed_fields_not_present_in_state PASSED [ 14%]
test_crew.py::TestMakeRoleInput::test_empty_allowed_fields_returns_empty_dict PASSED [ 19%]
test_crew.py::TestMakeRoleInput::test_none_state_returns_empty_dict PASSED [ 23%]
test_crew.py::TestMakeRoleInput::test_deep_copy_prevents_state_mutation PASSED [ 28%]
test_crew.py::TestMakeRoleInput::test_security_allowlist_fields PASSED   [ 33%]
test_crew.py::TestMakeRoleInput::test_reliability_allowlist_fields PASSED [ 38%]
test_crew.py::TestMakeRoleInput::test_accessibility_allowlist_fields PASSED [ 42%]
test_crew.py::TestMakeHandoff::test_creates_bounded_handoff_with_required_fields PASSED [ 47%]
test_crew.py::TestMakeHandoff::test_excludes_private_data PASSED         [ 52%]
test_crew.py::TestMakeHandoff::test_dict_finding_support PASSED          [ 57%]
test_crew.py::TestRunCrew::test_empty_specialist_sequence_returns_empty_tuples PASSED [ 61%]
test_crew.py::TestRunCrew::test_successful_ordered_sequence_execution PASSED [ 66%]
test_crew.py::TestRunCrew::test_reverse_sequence_order_is_respected PASSED [ 71%]
test_crew.py::TestRunCrew::test_specialist_exception_records_failure_and_continues PASSED [ 76%]
test_crew.py::TestRunCrew::test_all_specialists_fail PASSED              [ 80%]
test_crew.py::TestRunCrew::test_no_private_data_leaks_into_crew_result PASSED [ 85%]
test_crew.py::TestRunCrew::test_pre_existing_findings_preserved PASSED   [ 90%]
test_crew.py::TestRunCrew::test_original_state_never_mutated PASSED      [ 95%]
test_crew.py::TestRunCrew::test_run_declared_sequence_alias PASSED       [100%]

============================= 21 passed in 0.11s ==============================
```

### Verified Properties

- **Isolation:** Mutations to nested structures inside specialist inputs have zero impact on caller-owned state.
- **Privacy:** `private_data` dictionaries are completely absent from `SharedFinding`, `Handoff`, and aggregate outputs.
- **Least-Privilege Visibility:** Downstream specialists only access earlier findings/handoffs if explicitly permitted by their allow-list.
- **Fault Resilience:** Unhandled exceptions in specialists are trapped and recorded as `status="failed"`, `error="specialist_failed"`, preserving previously accumulated findings and continuing remaining specialists.
- **Declared Sequencing:** Arbitrary sequences (forward, reverse, single-specialist, or custom combinations) execute in declared order.

---

## 🚀 Quickstart

### Prerequisites

- Python 3.10+
- `pytest`

### Installation

```bash
git clone https://github.com/Shubhankart101/SharedStateReleaseCrew.git
cd SharedStateReleaseCrew
pip install -r requirements.txt
```

### Run Tests

```bash
pytest -v
```

### Programmatic Usage

```python
from main import run_crew
from utils.models import ReleaseState, SpecialistSpec, SpecialistFinding

# Define release candidate state
state = ReleaseState(
    release_id="REL-101",
    change_summary="Update auth and payment APIs",
    risk_level="medium",
    security_notes={"scopes": ["read", "write"]},
    build_metrics={"latency_p99": 110},
    ui_report={"contrast": 5.0},
)

# Define specialists
def security_check(data):
    return SpecialistFinding(
        finding_id="SEC-1",
        severity="LOW",
        summary="Auth scopes verified",
        private_data={"internal_token": "secret"},
    )

def reliability_check(data):
    return SpecialistFinding(
        finding_id="REL-1",
        severity="INFO",
        summary="Latency within SLA",
        private_data={"trace": [1, 2, 3]},
    )

crew = (
    SpecialistSpec(role="security", reviewer=security_check),
    SpecialistSpec(role="reliability", reviewer=reliability_check),
)

result = run_crew(state, crew)

print("Crew Execution Status:")
for res in result.results:
    print(f"Role: {res.role} | Status: {res.status} | Finding: {res.finding_id}")

print("\nShared Findings:")
for finding in result.findings:
    print(f"[{finding.severity}] {finding.role}: {finding.summary}")
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
