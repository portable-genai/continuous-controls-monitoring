"""Control-test packs: the shipped defaults are valid, and the validator can reject a bad pack.

The pack-schema check is the ``pack_schema_validity`` metric's oracle: an internally
inconsistent pack is a configuration error, caught before the engine runs it. This suite proves
both directions, so the metric is not falsely green.
"""

from __future__ import annotations

from continuous_controls_monitoring.domain.kernel import Severity
from continuous_controls_monitoring.domain.models import (
    ControlTestPack,
    Dimension,
    PassCriteria,
)
from continuous_controls_monitoring.domain.models import (
    TestKind as TKind,
)
from continuous_controls_monitoring.domain.packs import (
    DEFAULT_PACKS,
    all_valid,
    default_packs,
    load_packs,
    validate_pack,
)


def test_every_shipped_pack_is_valid() -> None:
    assert all_valid(DEFAULT_PACKS)
    assert {p.test_kind for p in DEFAULT_PACKS} == set(TKind), "one pack per test kind"


def test_a_threshold_pack_with_no_threshold_is_rejected() -> None:
    bad = ControlTestPack(
        pack_id="p",
        control_id="C1",
        title="t",
        test_kind=TKind.THRESHOLD,
        evidence_source="src",
        cadence="daily",
        dimensions=(Dimension.OPERATING,),
        severity=Severity.HIGH,
        criteria=PassCriteria(threshold_value=None),
    )
    problems = validate_pack(bad)
    assert problems
    assert not all_valid((bad,))


def test_a_config_scan_pack_with_no_expected_attributes_is_rejected() -> None:
    bad = ControlTestPack(
        pack_id="p",
        control_id="C1",
        title="t",
        test_kind=TKind.CONFIG_SCAN,
        evidence_source="src",
        cadence="daily",
        dimensions=(Dimension.OPERATING,),
        severity=Severity.HIGH,
        criteria=PassCriteria(expected_attributes=()),
    )
    assert validate_pack(bad)


def test_an_unconfigured_policy_uses_the_shipped_defaults() -> None:
    assert load_packs(None) == default_packs()
    assert load_packs({}) == default_packs()


def test_a_configured_policy_overrides_the_defaults() -> None:
    policy = {
        "control_packs": [
            {
                "pack_id": "custom",
                "control_id": "X1",
                "test_kind": "threshold",
                "evidence_source": "scc",
                "severity": "critical",
                "criteria": {"gate_severity": "high", "threshold_value": 5.0},
            }
        ]
    }
    packs = load_packs(policy)
    assert len(packs) == 1
    assert packs[0].pack_id == "custom"
    assert packs[0].criteria.threshold_value == 5.0
    assert all_valid(packs)


def test_a_deliberately_empty_pack_list_is_honoured_not_reverted() -> None:
    """An operator who configured zero packs expressed an intent; it is not the unset default."""
    assert load_packs({"control_packs": []}) == ()
