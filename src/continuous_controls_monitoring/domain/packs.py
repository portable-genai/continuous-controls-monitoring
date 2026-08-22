"""Control-test packs as DATA: the per-control test definitions, config-owned.

A pack says how one control is tested (kind, evidence source, cadence), what passes (the
bank-owned numbers in :class:`PassCriteria`), and how severe a violation is. The numbers are
the client's, so they live in ``config/settings.yaml`` under a ``policy:`` block and are loaded
here; the engine in ``testing.py`` stays pure code. When no policy block is configured the
shipped :data:`DEFAULT_PACKS` apply, so the offline gate has a complete, deterministic set.

``validate_pack`` is the pack-schema check: a pack that is internally inconsistent (a threshold
test with no threshold, a config scan with no expected attributes, an empty control id) is
rejected before the engine ever runs it. That is the ``pack_schema_validity`` metric's oracle.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .kernel import Citation, Severity
from .models import (
    ControlTestPack,
    Dimension,
    PassCriteria,
    TestKind,
)

_POLICY_CITATION = Citation(
    source_id="ccm-control-test-policy",
    title="Continuous controls monitoring test policy (bank-owned)",
    snippet="pack thresholds and severities are client configuration",
)


def default_packs() -> tuple[ControlTestPack, ...]:
    """The shipped default packs: one per test kind, over obviously synthetic controls."""
    return (
        ControlTestPack(
            pack_id="pack-egress-config",
            control_id="SC-7-egress",
            title="Data services enforce private egress",
            test_kind=TestKind.CONFIG_SCAN,
            evidence_source="cloud_asset_inventory",
            cadence="daily",
            dimensions=(Dimension.DESIGN, Dimension.OPERATING),
            severity=Severity.HIGH,
            criteria=PassCriteria(
                gate_severity=Severity.HIGH,
                expected_attributes=(("public_access_prevention", "enforced"),),
            ),
            sox_significant=True,
            citations=(_POLICY_CITATION,),
        ),
        ControlTestPack(
            pack_id="pack-access-recert",
            control_id="AC-2-recert",
            title="Privileged entitlements recertified quarterly",
            test_kind=TestKind.ACCESS_RECERT,
            evidence_source="rsk1_evidence_pack",
            cadence="quarterly",
            dimensions=(Dimension.DESIGN, Dimension.OPERATING),
            severity=Severity.HIGH,
            criteria=PassCriteria(gate_severity=Severity.HIGH, max_recert_age_days=90),
            sox_significant=True,
            citations=(_POLICY_CITATION,),
        ),
        ControlTestPack(
            pack_id="pack-settlement-dualauth",
            control_id="TX-settle-dualauth",
            title="High-value settlements carry dual authorisation",
            test_kind=TestKind.TRANSACTION_SAMPLE,
            evidence_source="transaction_sampler",
            cadence="weekly",
            dimensions=(Dimension.DESIGN, Dimension.OPERATING),
            severity=Severity.CRITICAL,
            criteria=PassCriteria(gate_severity=Severity.HIGH, max_exceptions=0),
            sox_significant=True,
            citations=(_POLICY_CITATION,),
        ),
        ControlTestPack(
            pack_id="pack-patch-sla",
            control_id="SEC-patch-sla",
            title="Critical security patches applied within SLA",
            test_kind=TestKind.THRESHOLD,
            evidence_source="security_command_center",
            cadence="daily",
            dimensions=(Dimension.DESIGN, Dimension.OPERATING),
            severity=Severity.MEDIUM,
            criteria=PassCriteria(
                gate_severity=Severity.MEDIUM,
                threshold_value=30.0,
                threshold_direction="max",
            ),
            sox_significant=False,
            citations=(_POLICY_CITATION,),
        ),
    )


#: The shipped default set, materialised once. Loaded when no ``policy:`` block is configured.
DEFAULT_PACKS: tuple[ControlTestPack, ...] = default_packs()


def validate_pack(pack: ControlTestPack) -> tuple[str, ...]:
    """Return the reasons ``pack`` is not a valid, testable definition (empty tuple if valid).

    The pack-schema oracle: an inconsistent pack is a configuration error, caught here rather
    than as a confusing engine result.
    """
    problems: list[str] = []
    if not pack.pack_id.strip():
        problems.append("pack_id is empty")
    if not pack.control_id.strip():
        problems.append("control_id is empty")
    if not pack.evidence_source.strip():
        problems.append("evidence_source is empty")
    if not pack.dimensions:
        problems.append("no dimensions declared")
    if pack.test_kind is TestKind.CONFIG_SCAN and not pack.criteria.expected_attributes:
        problems.append("config_scan pack declares no expected_attributes")
    if pack.test_kind is TestKind.THRESHOLD and pack.criteria.threshold_value is None:
        problems.append("threshold pack declares no threshold_value")
    if pack.test_kind is TestKind.THRESHOLD and pack.criteria.threshold_direction not in (
        "max",
        "min",
    ):
        problems.append("threshold_direction must be 'max' or 'min'")
    if pack.criteria.max_exceptions < 0:
        problems.append("max_exceptions must not be negative")
    if pack.criteria.max_recert_age_days < 0:
        problems.append("max_recert_age_days must not be negative")
    return tuple(problems)


def all_valid(packs: tuple[ControlTestPack, ...]) -> bool:
    """True iff every pack passes :func:`validate_pack` (the pack_schema_validity metric)."""
    return all(not validate_pack(pack) for pack in packs)


def load_packs(policy: Mapping[str, Any] | None) -> tuple[ControlTestPack, ...]:
    """Build packs from a ``policy`` mapping, or fall back to :data:`DEFAULT_PACKS`.

    ``policy`` is the parsed ``config/settings.yaml`` ``policy:`` block. A block that is present
    but names no packs is a configuration the operator wrote, so it is honoured as an empty set
    rather than silently reverting to the shipped default; a wholly absent block (``None``) is
    the unset state and takes the default.
    """
    if policy is None:
        return DEFAULT_PACKS
    raw = policy.get("control_packs")
    if raw is None:
        return DEFAULT_PACKS
    if not isinstance(raw, list):
        raise ValueError("policy.control_packs must be a list of pack mappings")
    return tuple(_pack_from_mapping(entry) for entry in raw)


def _pack_from_mapping(entry: Mapping[str, Any]) -> ControlTestPack:
    criteria_raw = entry.get("criteria") or {}
    criteria = PassCriteria(
        gate_severity=Severity(str(criteria_raw.get("gate_severity", "high"))),
        max_exceptions=int(criteria_raw.get("max_exceptions", 0)),
        max_recert_age_days=int(criteria_raw.get("max_recert_age_days", 90)),
        threshold_value=(
            float(criteria_raw["threshold_value"])
            if criteria_raw.get("threshold_value") is not None
            else None
        ),
        threshold_direction=str(criteria_raw.get("threshold_direction", "max")),
        expected_attributes=tuple(
            (str(k), str(v)) for k, v in (criteria_raw.get("expected_attributes") or {}).items()
        ),
        required_design_attributes=tuple(
            str(a) for a in (criteria_raw.get("required_design_attributes") or [])
        ),
    )
    return ControlTestPack(
        pack_id=str(entry["pack_id"]),
        control_id=str(entry["control_id"]),
        title=str(entry.get("title", "")),
        test_kind=TestKind(str(entry["test_kind"])),
        evidence_source=str(entry.get("evidence_source", "")),
        cadence=str(entry.get("cadence", "")),
        dimensions=tuple(
            Dimension(str(d)) for d in entry.get("dimensions", ["design", "operating"])
        ),
        severity=Severity(str(entry.get("severity", "high"))),
        criteria=criteria,
        sox_significant=bool(entry.get("sox_significant", False)),
        citations=(_POLICY_CITATION,),
    )
