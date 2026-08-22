"""Vertical artifact models: the continuous-controls-monitoring types.

The artifacts THIS vertical produces, as opposed to the vertical-neutral machinery in
``kernel.py``. The service's own name is deliberately not substituted into this docstring: a
rendered line whose length depends on ``friendly_name`` fails the repo's own format check for
no reason but the length of its name.

The heart of Aud2: a control READ from the Rgc7 inventory (this repo keeps no parallel
catalog), a test PACK that says how that control is tested, the EVIDENCE a scanner or an
Rsk1 evidence pack produces, the FINDINGS the deterministic engine emits, and the per-control
RESULT that scores design and operating effectiveness. Every consequential figure on these
types is produced by pure stdlib code in ``testing.py``; a model only narrates them.

A fork building a different vertical rewrites this module and keeps ``kernel.py`` untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from hex_service_kit.enums import LenientStrEnum

from .kernel import Citation, Decision, Severity


class TestKind(LenientStrEnum):
    """How a control is tested. The engine has one deterministic rule set per kind."""

    CONFIG_SCAN = "config_scan"  # inspect resource/config attributes for drift
    ACCESS_RECERT = "access_recert"  # entitlements recertified within a max age
    TRANSACTION_SAMPLE = "transaction_sample"  # a sample of transactions, count exceptions
    THRESHOLD = "threshold"  # a measured value against a numeric threshold


class Dimension(LenientStrEnum):
    """The two effectiveness dimensions SOX/ICFR testing scores separately."""

    DESIGN = "design"  # is the control properly designed and defined?
    OPERATING = "operating"  # does it actually operate over the evidence period?


class EffectivenessRating(LenientStrEnum):
    """The per-dimension verdict. ``NOT_TESTED`` is distinct from ``EFFECTIVE``."""

    EFFECTIVE = "effective"
    DEFICIENT = "deficient"
    NOT_TESTED = "not_tested"


class FindingKind(LenientStrEnum):
    """The kinds of control-test exception the deterministic engine detects."""

    CONTROL_NOT_IN_INVENTORY = "control_not_in_inventory"  # design: not in Rgc7 SoR
    DESIGN_INCOMPLETE = "design_incomplete"  # design: pack under-specified
    NO_EVIDENCE = "no_evidence"  # operating: nothing to test (escalates)
    CONFIG_DRIFT = "config_drift"  # operating: an attribute drifted from expected
    STALE_RECERTIFICATION = "stale_recertification"  # operating: recert older than max age
    SAMPLE_EXCEPTION = "sample_exception"  # operating: too many sampled exceptions
    THRESHOLD_BREACH = "threshold_breach"  # operating: a measured value breached a threshold


@dataclass(frozen=True, slots=True)
class InventoryControl:
    """One control READ from the Rgc7 inventory (the system of record).

    This repo never mints a control id; every id it names originated from a read. ``owner`` is
    who an exception routes to; ``sox_significant`` carries the ICFR documentation scope the
    CSV row subsumes.
    """

    control_id: str
    title: str
    owner: str = ""
    framework: str = ""
    sox_significant: bool = False
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """One normalised evidence item, whatever port produced it.

    ``attributes`` carries the raw, string-valued facts the detector inspects (read
    defensively, so a missing key is a finding, not a crash); ``source_ref`` is the asset name,
    the access-review id or the transaction reference the reviewer traces back to.
    """

    control_id: str
    kind: TestKind
    source: str  # the producing system: "cloud_asset_inventory", "rsk1_evidence_pack", ...
    identifier: str  # the asset / account / transaction id this record is about
    attributes: dict[str, str] = field(default_factory=dict)
    source_ref: str = ""


@dataclass(frozen=True, slots=True)
class PassCriteria:
    """The bank-owned numbers a pack is graded against (pure, testable, config-sourced).

    Lifted out of the engine so the policy values live in ``config/settings.yaml`` and the
    engine stays code: a control fails when any finding reaches ``gate_severity``.
    """

    gate_severity: Severity = Severity.HIGH
    max_exceptions: int = 0  # transaction sample: exceptions strictly above this fail
    max_recert_age_days: int = 90  # access recert: older than this is stale
    threshold_value: float | None = None  # threshold test: the numeric limit
    threshold_direction: str = "max"  # "max" -> value must be <= limit; "min" -> >=
    expected_attributes: tuple[tuple[str, str], ...] = ()  # config scan: key must equal value
    required_design_attributes: tuple[str, ...] = ()  # design: control must declare these


@dataclass(frozen=True, slots=True)
class ControlTestPack:
    """A per-control test definition: how, how often, and what passes. Config-owned data."""

    pack_id: str
    control_id: str
    title: str
    test_kind: TestKind
    evidence_source: str
    cadence: str  # "daily" / "weekly" / "monthly" / "quarterly" (documentation only)
    dimensions: tuple[Dimension, ...]
    severity: Severity  # the severity a violation of THIS pack carries
    criteria: PassCriteria
    sox_significant: bool = False
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class ControlFinding:
    """A single control-test exception against one control. Carries its own provenance."""

    control_id: str
    pack_id: str
    kind: FindingKind
    dimension: Dimension
    severity: Severity
    rule_id: str
    detail: str
    evidence_ref: str
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class EffectivenessScore:
    """The score for one dimension: a rating, an integer 0..100, and the finding count."""

    dimension: Dimension
    rating: EffectivenessRating
    score: int
    finding_count: int


@dataclass(frozen=True, slots=True)
class ControlTestResult:
    """The per-control result: design and operating effectiveness, findings, and the verdict.

    ``requires_human_review`` is set for every FAIL (an exception), which routes to the control
    owner via Hrz7 and never auto-closes. ``as_of`` makes the result replayable: the engine
    reads no clock.
    """

    control_id: str
    pack_id: str
    test_kind: TestKind
    as_of: date
    owner: str
    passed: bool
    design: EffectivenessScore
    operating: EffectivenessScore
    findings: tuple[ControlFinding, ...]
    decision: Decision
    requires_human_review: bool
    summary: str
    evidence_count: int
    citations: tuple[Citation, ...] = ()

    @property
    def subject(self) -> str:
        """The control id, so the review payload and the audit record have one subject."""
        return self.control_id

    @property
    def severity(self) -> Severity:
        """The highest finding severity, or ``LOW`` when the control passed clean."""
        if not self.findings:
            return Severity.LOW
        return max((f.severity for f in self.findings), key=lambda s: _SEVERITY_ORDER[s])


@dataclass(frozen=True, slots=True)
class MonitoredControl:
    """One control's result plus what the pipeline did with it: routed, written back, narrated.

    The engine produces ``result``; the service records where the escalation WENT (``review_ref``,
    rule R8), where the effectiveness evidence landed in Rgc7 (``writeback_ref``), and the
    validated exception narration (empty when the control passed or the narration was discarded).
    """

    result: ControlTestResult
    review_ref: str = ""
    writeback_ref: str = ""
    narration_headline: str = ""
    narration_body: str = ""


@dataclass(frozen=True, slots=True)
class MonitoringRun:
    """A batch result across many packs for one ``as_of``. The audit-view root."""

    as_of: date
    monitored: tuple[MonitoredControl, ...]

    @property
    def results(self) -> tuple[ControlTestResult, ...]:
        return tuple(m.result for m in self.monitored)

    @property
    def exceptions(self) -> tuple[MonitoredControl, ...]:
        """The failing controls, most severe first: the ones that route to a human."""
        return tuple(
            sorted(
                (m for m in self.monitored if not m.result.passed),
                key=lambda m: _SEVERITY_ORDER[m.result.severity],
                reverse=True,
            )
        )

    @property
    def passed_count(self) -> int:
        return sum(1 for m in self.monitored if m.result.passed)


#: Severity ordering, used for ranking findings and results. Kept here (not imported from the
#: commons) so the domain has one ordering it owns; higher number is more severe.
_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}
