"""API request/response schemas (Pydantic) mapped to/from the pure-domain models."""

from __future__ import annotations

from pydantic import BaseModel

from ..domain.models import ControlTestResult, MonitoredControl, MonitoringRun


class TestControlRequest(BaseModel):
    """Ask for one control's test to run now, by its pack id."""

    pack_id: str


class RunRequest(BaseModel):
    """Ask for a full monitoring run over every configured pack."""

    as_of: str = ""  # ISO date; empty means today (the surface fills it in)


class CitationModel(BaseModel):
    source_id: str
    title: str
    snippet: str = ""


class FindingModel(BaseModel):
    kind: str
    dimension: str
    severity: str
    detail: str
    evidence_ref: str


class EffectivenessModel(BaseModel):
    dimension: str
    rating: str
    score: int
    finding_count: int


class ControlTestResponse(BaseModel):
    control_id: str
    pack_id: str
    test_kind: str
    as_of: str
    owner: str
    passed: bool
    design: EffectivenessModel
    operating: EffectivenessModel
    severity: str
    decision: str
    requires_human_review: bool
    summary: str
    evidence_count: int
    findings: list[FindingModel] = []
    citations: list[CitationModel] = []
    #: Where the escalation WENT (rule R8): the Hrz7 review id, or the local queue reference.
    #: Empty only when the control passed.
    review_ref: str = ""
    #: Where the effectiveness evidence landed in Rgc7's graph, attached to the control.
    writeback_ref: str = ""
    #: The validated exception narration (empty when the control passed or narration failed).
    narration_headline: str = ""
    narration_body: str = ""

    @classmethod
    def from_monitored(cls, monitored: MonitoredControl) -> ControlTestResponse:
        result = monitored.result
        return cls(
            control_id=result.control_id,
            pack_id=result.pack_id,
            test_kind=result.test_kind.value,
            as_of=result.as_of.isoformat(),
            owner=result.owner,
            passed=result.passed,
            design=_effectiveness(result, dimension="design"),
            operating=_effectiveness(result, dimension="operating"),
            severity=result.severity.value,
            decision=result.decision.value,
            requires_human_review=result.requires_human_review,
            summary=result.summary,
            evidence_count=result.evidence_count,
            findings=[
                FindingModel(
                    kind=f.kind.value,
                    dimension=f.dimension.value,
                    severity=f.severity.value,
                    detail=f.detail,
                    evidence_ref=f.evidence_ref,
                )
                for f in result.findings
            ],
            citations=[
                CitationModel(source_id=c.source_id, title=c.title, snippet=c.snippet)
                for c in result.citations
            ],
            review_ref=monitored.review_ref,
            writeback_ref=monitored.writeback_ref,
            narration_headline=monitored.narration_headline,
            narration_body=monitored.narration_body,
        )


class RunResponse(BaseModel):
    as_of: str
    total: int
    passed: int
    exceptions: int
    results: list[ControlTestResponse] = []

    @classmethod
    def from_run(cls, run: MonitoringRun) -> RunResponse:
        return cls(
            as_of=run.as_of.isoformat(),
            total=len(run.monitored),
            passed=run.passed_count,
            exceptions=len(run.exceptions),
            results=[ControlTestResponse.from_monitored(m) for m in run.monitored],
        )


def _effectiveness(result: ControlTestResult, *, dimension: str) -> EffectivenessModel:
    score = result.design if dimension == "design" else result.operating
    return EffectivenessModel(
        dimension=score.dimension.value,
        rating=score.rating.value,
        score=score.score,
        finding_count=score.finding_count,
    )


class HealthResponse(BaseModel):
    status: str
    profile: str
    region: str
