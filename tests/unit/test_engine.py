"""The deterministic control-test engine: per-kind rules, scoring, verdict, determinism.

The consequential decision lives here, so this is where it is pinned. One test per test kind
(each constructs the minimal evidence that triggers exactly its finding), the design checks, the
no-evidence escalation (absence of evidence is a deficiency, never a pass), the gate rule, and a
determinism replay. Every assertion below fails if the corresponding rule is mutated, which is
what makes each metric able to go red.
"""

from __future__ import annotations

from datetime import date

from continuous_controls_monitoring.domain.kernel import Severity
from continuous_controls_monitoring.domain.models import (
    ControlTestPack,
    Dimension,
    EffectivenessRating,
    EvidenceRecord,
    FindingKind,
    InventoryControl,
    PassCriteria,
)
from continuous_controls_monitoring.domain.models import (
    TestKind as TKind,
)
from continuous_controls_monitoring.domain.testing import ControlTestEngine

_AS_OF = date(2026, 8, 1)
_ENGINE = ControlTestEngine()


def _control(control_id: str = "C1") -> InventoryControl:
    return InventoryControl(control_id=control_id, title="c", owner="owner@bank.example")


def _pack(kind: TKind, criteria: PassCriteria, control_id: str = "C1") -> ControlTestPack:
    return ControlTestPack(
        pack_id=f"pack-{control_id}",
        control_id=control_id,
        title="t",
        test_kind=kind,
        evidence_source="src",
        cadence="daily",
        dimensions=(Dimension.DESIGN, Dimension.OPERATING),
        severity=Severity.HIGH,
        criteria=criteria,
    )


def _ev(control_id: str, kind: TKind, **attrs: str) -> EvidenceRecord:
    return EvidenceRecord(
        control_id=control_id, kind=kind, source="src", identifier="id-1", attributes=dict(attrs)
    )


# --------------------------------------------------------------------------- #
# Design effectiveness
# --------------------------------------------------------------------------- #
def test_a_control_absent_from_inventory_is_a_design_deficiency() -> None:
    pack = _pack(TKind.CONFIG_SCAN, PassCriteria(expected_attributes=(("k", "v"),)))
    result = _ENGINE.evaluate(pack, None, (_ev("C1", TKind.CONFIG_SCAN, k="v"),), as_of=_AS_OF)
    assert result.design.rating is EffectivenessRating.DEFICIENT
    assert any(f.kind is FindingKind.CONTROL_NOT_IN_INVENTORY for f in result.findings)
    assert result.passed is False


# --------------------------------------------------------------------------- #
# Operating effectiveness, per kind
# --------------------------------------------------------------------------- #
def test_config_scan_flags_a_drifted_attribute() -> None:
    pack = _pack(TKind.CONFIG_SCAN, PassCriteria(expected_attributes=(("state", "enforced"),)))
    ok = _ENGINE.evaluate(
        pack, _control(), (_ev("C1", TKind.CONFIG_SCAN, state="enforced"),), as_of=_AS_OF
    )
    assert ok.passed is True
    assert ok.operating.rating is EffectivenessRating.EFFECTIVE

    drift = _ENGINE.evaluate(
        pack, _control(), (_ev("C1", TKind.CONFIG_SCAN, state="inherited"),), as_of=_AS_OF
    )
    assert drift.passed is False
    assert any(f.kind is FindingKind.CONFIG_DRIFT for f in drift.findings)


def test_access_recert_flags_a_stale_entitlement() -> None:
    pack = _pack(TKind.ACCESS_RECERT, PassCriteria(max_recert_age_days=90))
    fresh = _ENGINE.evaluate(
        pack,
        _control(),
        (_ev("C1", TKind.ACCESS_RECERT, recertified_days_ago="30"),),
        as_of=_AS_OF,
    )
    assert fresh.passed is True

    stale = _ENGINE.evaluate(
        pack,
        _control(),
        (_ev("C1", TKind.ACCESS_RECERT, recertified_days_ago="200"),),
        as_of=_AS_OF,
    )
    assert stale.passed is False
    assert any(f.kind is FindingKind.STALE_RECERTIFICATION for f in stale.findings)


def test_access_recert_with_no_recert_date_escalates() -> None:
    """A missing figure must not resolve to 'no finding': it escalates."""
    pack = _pack(TKind.ACCESS_RECERT, PassCriteria(max_recert_age_days=90))
    result = _ENGINE.evaluate(pack, _control(), (_ev("C1", TKind.ACCESS_RECERT),), as_of=_AS_OF)
    assert result.passed is False
    assert any(f.kind is FindingKind.STALE_RECERTIFICATION for f in result.findings)


def test_transaction_sample_flags_exceptions_over_the_limit() -> None:
    pack = _pack(TKind.TRANSACTION_SAMPLE, PassCriteria(max_exceptions=0))
    clean = _ENGINE.evaluate(
        pack, _control(), (_ev("C1", TKind.TRANSACTION_SAMPLE, outcome="ok"),), as_of=_AS_OF
    )
    assert clean.passed is True

    breach = _ENGINE.evaluate(
        pack,
        _control(),
        (_ev("C1", TKind.TRANSACTION_SAMPLE, outcome="exception"),),
        as_of=_AS_OF,
    )
    assert breach.passed is False
    assert any(f.kind is FindingKind.SAMPLE_EXCEPTION for f in breach.findings)


def test_threshold_flags_a_breach() -> None:
    pack = _pack(TKind.THRESHOLD, PassCriteria(threshold_value=30.0, threshold_direction="max"))
    within = _ENGINE.evaluate(
        pack, _control(), (_ev("C1", TKind.THRESHOLD, value="10"),), as_of=_AS_OF
    )
    assert within.passed is True

    over = _ENGINE.evaluate(
        pack, _control(), (_ev("C1", TKind.THRESHOLD, value="99"),), as_of=_AS_OF
    )
    assert over.passed is False
    assert any(f.kind is FindingKind.THRESHOLD_BREACH for f in over.findings)


# --------------------------------------------------------------------------- #
# No evidence, the gate, and determinism
# --------------------------------------------------------------------------- #
def test_no_evidence_is_a_deficiency_not_a_pass() -> None:
    pack = _pack(TKind.CONFIG_SCAN, PassCriteria(expected_attributes=(("k", "v"),)))
    result = _ENGINE.evaluate(pack, _control(), (), as_of=_AS_OF)
    assert result.passed is False
    assert result.operating.rating is EffectivenessRating.DEFICIENT
    assert any(f.kind is FindingKind.NO_EVIDENCE for f in result.findings)


def test_a_sub_gate_finding_reports_but_does_not_fail_the_control() -> None:
    """Gate is HIGH; a MEDIUM-severity pack violation reports but the control still passes."""
    pack = ControlTestPack(
        pack_id="p",
        control_id="C1",
        title="t",
        test_kind=TKind.CONFIG_SCAN,
        evidence_source="src",
        cadence="daily",
        dimensions=(Dimension.DESIGN, Dimension.OPERATING),
        severity=Severity.MEDIUM,
        criteria=PassCriteria(gate_severity=Severity.HIGH, expected_attributes=(("k", "v"),)),
    )
    result = _ENGINE.evaluate(
        pack, _control(), (_ev("C1", TKind.CONFIG_SCAN, k="wrong"),), as_of=_AS_OF
    )
    assert result.findings, "a sub-gate finding is still reported"
    assert result.passed is True, "a sub-gate finding must not fail the gate"


def test_the_result_is_deterministic() -> None:
    pack = _pack(TKind.CONFIG_SCAN, PassCriteria(expected_attributes=(("state", "enforced"),)))
    evidence = (_ev("C1", TKind.CONFIG_SCAN, state="inherited"),)
    first = _ENGINE.evaluate(pack, _control(), evidence, as_of=_AS_OF)
    second = _ENGINE.evaluate(pack, _control(), evidence, as_of=_AS_OF)
    assert first.summary == second.summary
    assert first.design == second.design
    assert first.operating == second.operating
    assert [f.rule_id for f in first.findings] == [f.rule_id for f in second.findings]
