"""Canonical synthetic control-test fixtures, shared by the unit and contract suites.

Every party is obviously fictional and every host is a ``.example`` domain. One canonical
failing control (an egress config drift) and one canonical passing control are enough for the
contract suite: parity means the SAME request through every implementation, so the request has
one home rather than being retyped per test. A planted identifier gives the redaction proofs an
independent literal to look for.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from continuous_controls_monitoring.domain.kernel import Citation, Severity
from continuous_controls_monitoring.domain.models import (
    ControlTestPack,
    ControlTestResult,
    Dimension,
    EvidenceRecord,
    InventoryControl,
    PassCriteria,
    TestKind,
)
from continuous_controls_monitoring.domain.testing import ControlTestEngine

#: The verified principal the tests attribute work to (never a client-asserted actor).
ACTOR = "auditor@bank.example"

#: The tenant partition, matching the offline inventory fixture so reads and write-backs align.
TENANT = "demo-bank"

#: A fixed ``as_of`` so every result is replayable (the engine reads no clock).
AS_OF = date(2026, 8, 1)

#: A planted identifier, so a redaction assertion has an independent literal to look for rather
#: than trusting the pattern pack to agree with itself.
PLANTED_NRIC = "S1234567D"

#: A planted address, so the universal rows have an independent literal of their own. Two rows
#: from two families, because a single pattern agreeing with itself proves less than two.
PLANTED_EMAIL = "kai.tan@delta.example"

_ENGINE = ControlTestEngine()

#: The control the canonical failing result is about: a real id from the offline inventory, so a
#: write-back naming it is accepted rather than rejected as unknown.
CONTROL = InventoryControl(
    control_id="SC-7-egress",
    title="Data services enforce private egress",
    owner="sc7-owner@bank.example",
    framework="NIST 800-53",
    sox_significant=True,
)

#: The canonical config-scan pack (gate HIGH), matching the shipped default pack for SC-7.
PACK = ControlTestPack(
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
)

#: Drifting evidence: one bucket is not enforced, so the engine emits a HIGH config-drift finding
#: and the control FAILS (an exception that routes to a human).
DRIFTING_EVIDENCE: tuple[EvidenceRecord, ...] = (
    EvidenceRecord(
        control_id="SC-7-egress",
        kind=TestKind.CONFIG_SCAN,
        source="cloud_asset_inventory",
        identifier="bucket-scratch-exports",
        attributes={"public_access_prevention": "inherited"},
        source_ref="//storage.googleapis.com/bucket-scratch-exports",
    ),
)

#: Clean evidence: the control PASSES, so a router that manufactured a review here would be lying.
CLEAN_EVIDENCE: tuple[EvidenceRecord, ...] = (
    EvidenceRecord(
        control_id="SC-7-egress",
        kind=TestKind.CONFIG_SCAN,
        source="cloud_asset_inventory",
        identifier="bucket-kyc-archive",
        attributes={"public_access_prevention": "enforced"},
        source_ref="//storage.googleapis.com/bucket-kyc-archive",
    ),
)

#: The canonical escalating result: SC-7 fails its config scan. Used by the review-router,
#: write-back and time-series contract cases (all need a real result for a known control).
ESCALATING_RESULT: ControlTestResult = _ENGINE.evaluate(
    PACK, CONTROL, DRIFTING_EVIDENCE, as_of=AS_OF
)

#: The canonical passing result: SC-7 clean. A router handed this must NOT manufacture a review.
PASSING_RESULT: ControlTestResult = _ENGINE.evaluate(PACK, CONTROL, CLEAN_EVIDENCE, as_of=AS_OF)

#: An escalating result whose finding carries planted personal data, for the redaction proofs.
#: The identifier lands in ``ControlFinding.detail`` (the engine writes ``f"{record.identifier}:
#: ..."``) and the address lands in ``ControlFinding.evidence_ref`` (``record.source_ref``), so
#: this one record covers both of the finding fields that carry raw upstream text.
PII_EVIDENCE: tuple[EvidenceRecord, ...] = (
    EvidenceRecord(
        control_id="SC-7-egress",
        kind=TestKind.CONFIG_SCAN,
        source="cloud_asset_inventory",
        identifier=f"bucket-owned-by-{PLANTED_NRIC}",
        attributes={"public_access_prevention": "inherited"},
        source_ref=f"//storage.googleapis.com/escalate-to-{PLANTED_EMAIL}",
    ),
)
#: The engine summary never contains an identifier, so plant one on the summary that the review
#: payload carries, to prove the payload is redacted on the wire (the finding detail, which also
#: carries the identifier, is redacted separately on the audit path).
PII_RESULT: ControlTestResult = replace(
    _ENGINE.evaluate(PACK, CONTROL, PII_EVIDENCE, as_of=AS_OF),
    summary=f"SC-7-egress owner NRIC {PLANTED_NRIC} config drift",
)

#: A pack citation whose LOCATOR and TITLE are built from the asset the pack was written against.
#: The engine copies a pack's citations onto every result and every finding it emits, and those
#: travel into the WORM record and out to the shared review console. Today's ``load_packs``
#: attaches one fixed policy citation, so no shipped configuration produces this; the TYPE
#: permits it, the managed inventory adapter already builds a locator out of remote text
#: (``adapters/gcp/control_inventory.py``), and a boundary that only holds for the citations
#: currently in the tree is a convention rather than a boundary.
PII_CITATION = Citation(
    source_id=f"asset:bucket-owned-by-{PLANTED_NRIC}",
    title=f"Private egress exception, raised by {PLANTED_EMAIL}",
    snippet=f"bucket-owned-by-{PLANTED_NRIC} inherits public access",
)

#: The canonical pack for the redaction proofs: the SC-7 config scan, cited as above. Same
#: control id, so the Rgc7 write-back accepts the result rather than rejecting an unknown id.
PII_CITATION_PACK: ControlTestPack = replace(
    PACK, pack_id="pack-egress-config-cited", citations=(PII_CITATION,)
)
