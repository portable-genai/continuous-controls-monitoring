"""Deterministic offline fixtures shared by the local inventory / scanner / evidence adapters.

One consistent synthetic estate so the three offline adapters agree: the inventory names exactly the
controls the packs test, the scanner returns config/transaction/threshold evidence for the
scanner-sourced controls, and the compliance-advisory evidence pack returns the
access-recertification records for the control whose evidence source is compliance-advisory. Every
party is obviously fictional and every host is a ``.example`` domain, per the synthetic-data rule.

The estate is deliberately mixed: one control drifts (a config exception), the rest are clean, so
the demo and the service integration tests exercise both a PASS and a routed FAIL.
"""

from __future__ import annotations

from ...domain.kernel import Citation
from ...domain.models import EvidenceRecord, InventoryControl, TestKind

#: The demo tenant. A SECOND tenant carries one control, so the cross-tenant denial has a real
#: other-tenant control to refuse access to rather than a merely-absent id.
DEMO_TENANT = "demo-bank"
OTHER_TENANT = "other-bank"

_SC7 = InventoryControl(
    control_id="SC-7-egress",
    title="Data services enforce private egress",
    owner="sc7-owner@bank.example",
    framework="NIST 800-53",
    sox_significant=True,
    citations=(
        Citation(
            source_id="rgc7:SC-7-egress", title="obligations-control-mapping control inventory"
        ),
    ),
)
_AC2 = InventoryControl(
    control_id="AC-2-recert",
    title="Privileged entitlements recertified quarterly",
    owner="ac2-owner@bank.example",
    framework="NIST 800-53",
    sox_significant=True,
    citations=(
        Citation(
            source_id="rgc7:AC-2-recert", title="obligations-control-mapping control inventory"
        ),
    ),
)
_TX = InventoryControl(
    control_id="TX-settle-dualauth",
    title="High-value settlements carry dual authorisation",
    owner="tx-owner@bank.example",
    framework="COSO",
    sox_significant=True,
    citations=(
        Citation(
            source_id="rgc7:TX-settle-dualauth",
            title="obligations-control-mapping control inventory",
        ),
    ),
)
_SEC = InventoryControl(
    control_id="SEC-patch-sla",
    title="Critical security patches applied within SLA",
    owner="sec-owner@bank.example",
    framework="NIST 800-53",
    sox_significant=False,
    citations=(
        Citation(
            source_id="rgc7:SEC-patch-sla", title="obligations-control-mapping control inventory"
        ),
    ),
)
_OTHER = InventoryControl(
    control_id="OTHER-only-control",
    title="A control owned by another tenant",
    owner="owner@other.example",
    citations=(
        Citation(
            source_id="rgc7:OTHER-only-control",
            title="obligations-control-mapping control inventory",
        ),
    ),
)

#: tenant -> control id -> control. The single offline copy of what a read of
#: obligations-control-mapping returns.
CONTROLS: dict[str, dict[str, InventoryControl]] = {
    DEMO_TENANT: {
        _SC7.control_id: _SC7,
        _AC2.control_id: _AC2,
        _TX.control_id: _TX,
        _SEC.control_id: _SEC,
    },
    OTHER_TENANT: {_OTHER.control_id: _OTHER},
}

#: Scanner evidence (Cloud Asset Inventory / Security Command Center / transaction sampler
#: offline stand-ins), keyed by control id. AC-2 is absent here: its evidence comes from
#: compliance-advisory.
SCANNER_EVIDENCE: dict[str, tuple[EvidenceRecord, ...]] = {
    "SC-7-egress": (
        EvidenceRecord(
            control_id="SC-7-egress",
            kind=TestKind.CONFIG_SCAN,
            source="cloud_asset_inventory",
            identifier="bucket-kyc-archive",
            attributes={"public_access_prevention": "enforced"},
            source_ref="//storage.googleapis.com/bucket-kyc-archive",
        ),
        EvidenceRecord(
            control_id="SC-7-egress",
            kind=TestKind.CONFIG_SCAN,
            source="cloud_asset_inventory",
            identifier="bucket-scratch-exports",
            attributes={"public_access_prevention": "inherited"},
            source_ref="//storage.googleapis.com/bucket-scratch-exports",
        ),
    ),
    "TX-settle-dualauth": (
        EvidenceRecord(
            control_id="TX-settle-dualauth",
            kind=TestKind.TRANSACTION_SAMPLE,
            source="transaction_sampler",
            identifier="settle-0001",
            attributes={"outcome": "dual_authorised"},
            source_ref="ledger://settle/0001",
        ),
        EvidenceRecord(
            control_id="TX-settle-dualauth",
            kind=TestKind.TRANSACTION_SAMPLE,
            source="transaction_sampler",
            identifier="settle-0002",
            attributes={"outcome": "dual_authorised"},
            source_ref="ledger://settle/0002",
        ),
    ),
    "SEC-patch-sla": (
        EvidenceRecord(
            control_id="SEC-patch-sla",
            kind=TestKind.THRESHOLD,
            source="security_command_center",
            identifier="finding-cve-2026-0001",
            attributes={"value": "12"},
            source_ref="scc://findings/cve-2026-0001",
        ),
    ),
}

#: compliance-advisory cloud control evidence packs (the formerly the cloud control-mapping toolkit
#: surface), keyed by control id. AC-2's access
#: recertification evidence lives ONLY here, so removing this source flips AC-2 pass -> fail.
RSK1_EVIDENCE: dict[str, tuple[EvidenceRecord, ...]] = {
    "AC-2-recert": (
        EvidenceRecord(
            control_id="AC-2-recert",
            kind=TestKind.ACCESS_RECERT,
            source="rsk1_evidence_pack",
            identifier="entitlement-dba-prod",
            attributes={"recertified_days_ago": "20"},
            source_ref="rsk1://packs/AC-2-recert/dba-prod",
        ),
        EvidenceRecord(
            control_id="AC-2-recert",
            kind=TestKind.ACCESS_RECERT,
            source="rsk1_evidence_pack",
            identifier="entitlement-payments-admin",
            attributes={"recertified_days_ago": "45"},
            source_ref="rsk1://packs/AC-2-recert/payments-admin",
        ),
    ),
}
