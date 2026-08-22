"""Every eval metric is provably able to go RED (a metric that cannot is not a metric).

The eval scores the engine against the dataset's OWN labels (an independent oracle), so the
proof here is that each underlying computation moves off 1.0 for a wrong answer: the
effectiveness verdict, the groundedness check, and the pack-schema validity. The pii_safety
metric's red-proof lives in ``test_not_falsely_green.py``.
"""

from __future__ import annotations

from datetime import date

from agent_eval_kit import assert_can_go_red

from continuous_controls_monitoring.domain.kernel import Severity
from continuous_controls_monitoring.domain.models import (
    ControlTestPack,
    Dimension,
    EvidenceRecord,
    InventoryControl,
    PassCriteria,
    TestKind,
)
from continuous_controls_monitoring.domain.narration import is_grounded
from continuous_controls_monitoring.domain.packs import DEFAULT_PACKS, validate_pack
from continuous_controls_monitoring.domain.testing import ControlTestEngine

_AS_OF = date(2026, 8, 1)
_ENGINE = ControlTestEngine()

_PACK = ControlTestPack(
    pack_id="p",
    control_id="C1",
    title="t",
    test_kind=TestKind.CONFIG_SCAN,
    evidence_source="src",
    cadence="daily",
    dimensions=(Dimension.DESIGN, Dimension.OPERATING),
    severity=Severity.HIGH,
    criteria=PassCriteria(
        gate_severity=Severity.HIGH, expected_attributes=(("state", "enforced"),)
    ),
)
_CONTROL = InventoryControl(control_id="C1", title="t", owner="owner@bank.example")
_FAIL = _ENGINE.evaluate(
    _PACK,
    _CONTROL,
    (
        EvidenceRecord(
            control_id="C1",
            kind=TestKind.CONFIG_SCAN,
            source="src",
            identifier="b1",
            attributes={"state": "inherited"},
        ),
    ),
    as_of=_AS_OF,
)


def test_effectiveness_accuracy_can_go_red() -> None:
    """Scoring the engine verdict against the WRONG expected label goes red."""

    def _score(expected_passed: bool) -> float:
        return 1.0 if _FAIL.passed is expected_passed else 0.0

    assert_can_go_red(
        _score,
        green=False,  # the control did fail; the correct label is passed=False
        red=True,  # a wrong label (passed=True) scores 0
        threshold=0.9,
        metric="effectiveness_accuracy",
    )


def test_groundedness_can_go_red() -> None:
    """A narration that introduces a figure the engine never produced goes red."""

    def _score(text: str) -> float:
        return 1.0 if is_grounded(text, _FAIL) else 0.0

    assert_can_go_red(
        _score,
        green="one config drift was found",  # no ungrounded number
        red="there were 4242 drifts",  # 4242 is not an engine figure
        threshold=0.99,
        metric="groundedness",
    )


def test_pack_schema_validity_can_go_red() -> None:
    """A pack with an internal inconsistency scores below 1.0."""

    def _score(pack: ControlTestPack) -> float:
        return 1.0 if not validate_pack(pack) else 0.0

    broken = ControlTestPack(
        pack_id="p",
        control_id="C1",
        title="t",
        test_kind=TestKind.THRESHOLD,
        evidence_source="src",
        cadence="daily",
        dimensions=(Dimension.OPERATING,),
        severity=Severity.HIGH,
        criteria=PassCriteria(threshold_value=None),
    )
    assert_can_go_red(
        _score,
        green=DEFAULT_PACKS[0],
        red=broken,
        threshold=1.0,
        metric="pack_schema_validity",
    )
