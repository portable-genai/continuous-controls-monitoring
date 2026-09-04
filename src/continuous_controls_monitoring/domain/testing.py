"""The deterministic control-test engine: evidence in, effectiveness out. PURE stdlib.

Cribbed from architecture-validator's residency module (the closest built thing to continuous
control testing): a per-kind detector emits :class:`ControlFinding` objects, a
:func:`compute_verdict` turns them into a PASS/FAIL against the pack's gate severity, and each
dimension is scored separately. No LLM, no network, no clock: the engine takes an explicit ``as_of``
and the same inputs always grade the same way, which is what makes an always-on control test
trustworthy.

The rule the whole thing rests on: **a control fails when any finding reaches the gate
severity**, and a dimension with no evidence to test is DEFICIENT, never quietly EFFECTIVE.
Absence of evidence of a problem is not evidence of its absence.
"""

from __future__ import annotations

from datetime import date

from .kernel import Citation, Decision, Severity
from .models import (
    ControlFinding,
    ControlTestPack,
    ControlTestResult,
    Dimension,
    EffectivenessRating,
    EffectivenessScore,
    EvidenceRecord,
    FindingKind,
    InventoryControl,
    TestKind,
)

# Higher number is more severe. Owned here so the engine's ordering is not a remote import.
_SEVERITY_RANK: dict[Severity, int] = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}

#: Per-rating dimension score. DEFICIENT is graded by the worst finding severity so a dashboard
#: can rank two deficient controls; the RATING is the consequential verdict, the score is colour.
_DEFICIENT_SCORE_BY_SEVERITY: dict[Severity, int] = {
    Severity.LOW: 75,
    Severity.MEDIUM: 50,
    Severity.HIGH: 25,
    Severity.CRITICAL: 0,
}


def severity_at_or_above(findings: tuple[ControlFinding, ...], floor: Severity) -> bool:
    """True when any finding is at or above ``floor`` (the gate rule, one place)."""
    threshold = _SEVERITY_RANK[floor]
    return any(_SEVERITY_RANK[f.severity] >= threshold for f in findings)


def compute_verdict(findings: tuple[ControlFinding, ...], gate_severity: Severity) -> bool:
    """PASS iff there is no finding at or above ``gate_severity``. Sub-gate findings report but
    do not fail the control, exactly the residency ``compute_verdict`` shape."""
    return not severity_at_or_above(findings, gate_severity)


class ControlTestEngine:
    """Grade one control against one pack over its evidence. Pure and replayable."""

    #: The residency citation this engine attaches to every finding: continuous control testing
    #: is the SOX/ICFR assurance obligation the CSV row subsumes.
    _ICFR = Citation(
        source_id="sox-404-icfr",
        title="SOX 404 / ICFR control effectiveness (design and operating)",
        snippet="continuous testing of key controls",
    )

    def evaluate(
        self,
        pack: ControlTestPack,
        control: InventoryControl | None,
        evidence: tuple[EvidenceRecord, ...],
        *,
        as_of: date,
    ) -> ControlTestResult:
        """Grade ``control`` against ``pack`` over ``evidence`` as of ``as_of``."""
        design_findings = self._design_findings(pack, control)
        operating_findings = self._operating_findings(pack, evidence)
        findings = design_findings + operating_findings

        design = self._score(Dimension.DESIGN, pack, design_findings, has_evidence=True)
        operating = self._score(
            Dimension.OPERATING, pack, operating_findings, has_evidence=bool(evidence)
        )

        passed = compute_verdict(findings, pack.criteria.gate_severity)
        decision = Decision.ALLOWED if passed else Decision.ESCALATED
        owner = control.owner if control is not None else ""
        summary = self._summary(pack, passed, design, operating, len(findings))
        citations = (self._ICFR, *pack.citations)
        return ControlTestResult(
            control_id=pack.control_id,
            pack_id=pack.pack_id,
            test_kind=pack.test_kind,
            as_of=as_of,
            owner=owner,
            passed=passed,
            design=design,
            operating=operating,
            findings=findings,
            decision=decision,
            requires_human_review=not passed,
            summary=summary,
            evidence_count=len(evidence),
            citations=citations,
        )

    # ------------------------------------------------------------------ #
    # Design effectiveness: is the control in the SoR and properly defined?
    # ------------------------------------------------------------------ #
    def _design_findings(
        self, pack: ControlTestPack, control: InventoryControl | None
    ) -> tuple[ControlFinding, ...]:
        out: list[ControlFinding] = []
        if control is None:
            out.append(
                self._finding(
                    pack,
                    FindingKind.CONTROL_NOT_IN_INVENTORY,
                    Dimension.DESIGN,
                    pack.severity,
                    "control-not-in-inventory",
                    (
                        f"{pack.control_id} is tested by pack {pack.pack_id} but is not present "
                        "in the obligations-control-mapping control inventory (the system of "
                        "record); a test with no "
                        "control of record cannot evidence design."
                    ),
                    pack.control_id,
                )
            )
            return tuple(out)
        if not pack.evidence_source.strip():
            out.append(
                self._finding(
                    pack,
                    FindingKind.DESIGN_INCOMPLETE,
                    Dimension.DESIGN,
                    pack.severity,
                    "design-no-evidence-source",
                    f"pack {pack.pack_id} names no evidence source, so the control is untestable.",
                    pack.control_id,
                )
            )
        return tuple(out)

    # ------------------------------------------------------------------ #
    # Operating effectiveness: does it actually operate over the evidence?
    # ------------------------------------------------------------------ #
    def _operating_findings(
        self, pack: ControlTestPack, evidence: tuple[EvidenceRecord, ...]
    ) -> tuple[ControlFinding, ...]:
        if not evidence:
            # Escalate rather than pass: a control with nothing to test is not a control that
            # passed. This is the fail-closed default the skill mandates.
            return (
                self._finding(
                    pack,
                    FindingKind.NO_EVIDENCE,
                    Dimension.OPERATING,
                    pack.severity,
                    "no-operating-evidence",
                    (
                        f"no evidence was gathered for {pack.control_id} from "
                        f"{pack.evidence_source or 'its evidence source'}; operating "
                        "effectiveness cannot be asserted, so the control is deficient."
                    ),
                    pack.control_id,
                ),
            )
        kind = pack.test_kind
        if kind is TestKind.CONFIG_SCAN:
            return self._config_scan(pack, evidence)
        if kind is TestKind.ACCESS_RECERT:
            return self._access_recert(pack, evidence)
        if kind is TestKind.TRANSACTION_SAMPLE:
            return self._transaction_sample(pack, evidence)
        if kind is TestKind.THRESHOLD:
            return self._threshold(pack, evidence)
        # Unknown kind: escalate, never silently pass. (Unreachable while TestKind is closed.)
        return (  # pragma: no cover - defensive, TestKind is exhaustive above
            self._finding(
                pack,
                FindingKind.NO_EVIDENCE,
                Dimension.OPERATING,
                pack.severity,
                "unknown-test-kind",
                f"pack {pack.pack_id} has an unhandled test kind {kind.value!r}.",
                pack.control_id,
            ),
        )

    def _config_scan(
        self, pack: ControlTestPack, evidence: tuple[EvidenceRecord, ...]
    ) -> tuple[ControlFinding, ...]:
        out: list[ControlFinding] = []
        expected = pack.criteria.expected_attributes
        for record in evidence:
            for key, want in expected:
                got = str(record.attributes.get(key, "")).strip()
                if got != want:
                    out.append(
                        self._finding(
                            pack,
                            FindingKind.CONFIG_DRIFT,
                            Dimension.OPERATING,
                            pack.severity,
                            f"config-drift-{key}",
                            (
                                f"{record.identifier}: {key} is {got or 'unset'!r}, expected "
                                f"{want!r} (pack {pack.pack_id})."
                            ),
                            record.source_ref or record.identifier,
                        )
                    )
        return tuple(out)

    def _access_recert(
        self, pack: ControlTestPack, evidence: tuple[EvidenceRecord, ...]
    ) -> tuple[ControlFinding, ...]:
        out: list[ControlFinding] = []
        max_age = pack.criteria.max_recert_age_days
        for record in evidence:
            age = _int_attr(record, "recertified_days_ago")
            if age is None or age > max_age:
                shown = "unknown" if age is None else str(age)
                out.append(
                    self._finding(
                        pack,
                        FindingKind.STALE_RECERTIFICATION,
                        Dimension.OPERATING,
                        pack.severity,
                        "stale-recertification",
                        (
                            f"{record.identifier}: last recertified {shown} days ago, limit is "
                            f"{max_age} (pack {pack.pack_id})."
                        ),
                        record.source_ref or record.identifier,
                    )
                )
        return tuple(out)

    def _transaction_sample(
        self, pack: ControlTestPack, evidence: tuple[EvidenceRecord, ...]
    ) -> tuple[ControlFinding, ...]:
        exceptions = [
            r for r in evidence if str(r.attributes.get("outcome", "")).strip() == "exception"
        ]
        if len(exceptions) <= pack.criteria.max_exceptions:
            return ()
        refs = ", ".join(r.identifier for r in exceptions[:5])
        return (
            self._finding(
                pack,
                FindingKind.SAMPLE_EXCEPTION,
                Dimension.OPERATING,
                pack.severity,
                "sample-exceptions-over-limit",
                (
                    f"{len(exceptions)} of {len(evidence)} sampled transactions were exceptions "
                    f"(limit {pack.criteria.max_exceptions}); e.g. {refs} (pack {pack.pack_id})."
                ),
                refs or pack.control_id,
            ),
        )

    def _threshold(
        self, pack: ControlTestPack, evidence: tuple[EvidenceRecord, ...]
    ) -> tuple[ControlFinding, ...]:
        limit = pack.criteria.threshold_value
        if limit is None:
            return (
                self._finding(
                    pack,
                    FindingKind.DESIGN_INCOMPLETE,
                    Dimension.OPERATING,
                    pack.severity,
                    "threshold-not-configured",
                    f"pack {pack.pack_id} is a threshold test with no threshold_value configured.",
                    pack.control_id,
                ),
            )
        out: list[ControlFinding] = []
        for record in evidence:
            value = _float_attr(record, "value")
            if value is None:
                out.append(
                    self._finding(
                        pack,
                        FindingKind.THRESHOLD_BREACH,
                        Dimension.OPERATING,
                        pack.severity,
                        "threshold-value-missing",
                        f"{record.identifier}: no measured 'value' to test (pack {pack.pack_id}).",
                        record.source_ref or record.identifier,
                    )
                )
                continue
            if pack.criteria.threshold_direction == "max":
                breached = value > limit
            else:
                breached = value < limit
            if breached:
                out.append(
                    self._finding(
                        pack,
                        FindingKind.THRESHOLD_BREACH,
                        Dimension.OPERATING,
                        pack.severity,
                        "threshold-breach",
                        (
                            f"{record.identifier}: value {value} breached the "
                            f"{pack.criteria.threshold_direction} limit {limit} (pack "
                            f"{pack.pack_id})."
                        ),
                        record.source_ref or record.identifier,
                    )
                )
        return tuple(out)

    # ------------------------------------------------------------------ #
    # Scoring and helpers
    # ------------------------------------------------------------------ #
    def _score(
        self,
        dimension: Dimension,
        pack: ControlTestPack,
        findings: tuple[ControlFinding, ...],
        *,
        has_evidence: bool,
    ) -> EffectivenessScore:
        if dimension not in pack.dimensions:
            return EffectivenessScore(dimension, EffectivenessRating.NOT_TESTED, 0, 0)
        if dimension is Dimension.OPERATING and not has_evidence:
            return EffectivenessScore(dimension, EffectivenessRating.DEFICIENT, 0, len(findings))
        gating = severity_at_or_above(findings, pack.criteria.gate_severity)
        if not gating:
            # No gating finding: effective. Sub-gate observations still count but do not fail.
            score = 100 if not findings else 90
            return EffectivenessScore(
                dimension, EffectivenessRating.EFFECTIVE, score, len(findings)
            )
        worst = max((f.severity for f in findings), key=lambda s: _SEVERITY_RANK[s])
        return EffectivenessScore(
            dimension,
            EffectivenessRating.DEFICIENT,
            _DEFICIENT_SCORE_BY_SEVERITY[worst],
            len(findings),
        )

    def _finding(
        self,
        pack: ControlTestPack,
        kind: FindingKind,
        dimension: Dimension,
        severity: Severity,
        rule_id: str,
        detail: str,
        evidence_ref: str,
    ) -> ControlFinding:
        return ControlFinding(
            control_id=pack.control_id,
            pack_id=pack.pack_id,
            kind=kind,
            dimension=dimension,
            severity=severity,
            rule_id=rule_id,
            detail=detail,
            evidence_ref=evidence_ref,
            citations=(self._ICFR, *pack.citations),
        )

    @staticmethod
    def _summary(
        pack: ControlTestPack,
        passed: bool,
        design: EffectivenessScore,
        operating: EffectivenessScore,
        finding_count: int,
    ) -> str:
        verdict = "PASS" if passed else "FAIL"
        return (
            f"{pack.control_id} [{pack.test_kind.value}] {verdict}: "
            f"design {design.rating.value}, operating {operating.rating.value}, "
            f"{finding_count} finding(s)"
        )


def _int_attr(record: EvidenceRecord, key: str) -> int | None:
    raw = str(record.attributes.get(key, "")).strip()
    try:
        return int(raw)
    except ValueError:
        return None


def _float_attr(record: EvidenceRecord, key: str) -> float | None:
    raw = str(record.attributes.get(key, "")).strip()
    try:
        return float(raw)
    except ValueError:
        return None
