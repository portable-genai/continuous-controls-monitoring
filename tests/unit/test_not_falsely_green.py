"""The pii_safety metric the GATE SHIPS is proved able to go red (check E2).

The previous version of this file scored a four-line local helper defined three lines above the
assertion. It passed, and it proved nothing about the gate, because the shipped metric was worse
than the helper: it assembled its own string from the result, redacted THAT, and scanned what it
had just redacted. It asked the redactor whether it had redacted and believed the answer. It
reported ``pii_safety 1.000 PASS`` on a tree where the same result's finding prose went to the
model with the identifier verbatim.

So the falsification runs against ``run_eval`` itself, imported as the gate imports it, and the
mutant is the leak the metric exists to catch: the SAME row, summary clean either way, differing
only in the citation. A metric that reads the wrong field cannot tell the two apart and stays
green on the red input, which is exactly the failure ``assert_can_go_red`` refuses.
"""

from __future__ import annotations

from typing import Any

import run_eval as ev
from agent_eval_kit import assert_can_go_red

from continuous_controls_monitoring.config import build_container
from continuous_controls_monitoring.domain.monitoring_service import MonitoringService

from tests.conftest import local_settings
from tests.fixtures import sample_cases

_PLANTED = (sample_cases.PLANTED_NRIC, sample_cases.PLANTED_EMAIL)

#: The summary is CLEAN in both rows. That is the whole point: the summary was never the only
#: field that can leak, so a metric that reads it alone scores these two identically.
_CLEAN_ROW: dict[str, Any] = {
    "action": "control_test",
    "actor": sample_cases.ACTOR,
    "redacted_summary": "SC-7-egress [config_scan] FAIL :: [REDACTED:EMAIL_ADDRESS]",
    "citations": [
        {
            "source_id": "asset:bucket-owned-by-[REDACTED:SG_NRIC_FIN]",
            "title": "Private egress exception",
            "snippet": "bucket-owned-by-[REDACTED:SG_NRIC_FIN] inherits public access",
        }
    ],
}

#: Redaction off, in the citation only (the mutant a summary-only metric scores 1.000).
_LEAKY_ROW: dict[str, Any] = {
    **_CLEAN_ROW,
    "citations": [
        {
            "source_id": f"asset:bucket-owned-by-{sample_cases.PLANTED_NRIC}",
            "title": f"Private egress exception, raised by {sample_cases.PLANTED_EMAIL}",
            "snippet": f"bucket-owned-by-{sample_cases.PLANTED_NRIC} inherits public access",
        }
    ],
}


def _score(rows: list[dict[str, Any]]) -> float:
    """The gate's own scorer over the gate's own field selection. No re-implementation here."""
    return ev.pii_safety(ev.audit_texts(rows), _PLANTED)


def test_pii_safety_can_go_red() -> None:
    assert_can_go_red(
        _score,
        green=[_CLEAN_ROW],
        red=[_LEAKY_ROW],
        threshold=ev.THRESHOLDS["pii_safety"],
        metric="pii_safety",
    )


def test_pii_safety_can_go_red_on_the_model_prompt_too() -> None:
    """The other sink, falsified the same way: the FACTS block is scored, not only the store.

    The prompt is where this repo's identifier actually went, so a scorer that reads audit rows
    alone would have been a second falsely green metric with a better docstring.
    """

    def _score_prompt(prompt: str) -> float:
        return ev.pii_safety([prompt], _PLANTED)

    assert_can_go_red(
        _score_prompt,
        green="- findings: 1 * [high] bucket-owned-by-[REDACTED:SG_NRIC_FIN] drifted",
        red=f"- findings: 1 * [high] bucket-owned-by-{sample_cases.PLANTED_NRIC} drifted",
        threshold=ev.THRESHOLDS["pii_safety"],
        metric="pii_safety",
    )


def test_pii_safety_is_green_on_the_record_the_real_service_writes() -> None:
    """Green, and green over a real run rather than over an empty list of nothing."""
    container = build_container(local_settings())
    service = MonitoringService(
        audit=container.audit,
        inventory=container.control_inventory,
        scanner=container.evidence_scanner,
        control_evidence=container.control_evidence,
        writeback=container.writeback,
        timeseries=container.timeseries,
        generation=container.generation,
        review_router=container.review_router,
        tracer=container.tracer,
        policy=container.settings.policy,
    )
    service.evaluate_pack(
        sample_cases.PII_CITATION_PACK,
        as_of=sample_cases.AS_OF,
        tenant=sample_cases.TENANT,
        actor=sample_cases.ACTOR,
    )

    texts = ev.audit_texts(container.audit.log.read_all())  # type: ignore[attr-defined]
    assert any("[REDACTED:" in text for text in texts), (
        "the scan found no redaction marker, so it is reading fields that carry no content "
        "and its green means nothing"
    )
    assert ev.pii_safety(texts, _PLANTED) == 1.0


def test_the_scan_excludes_the_actor_so_it_can_ever_be_green() -> None:
    """The caveat, pinned: widening this to whole rows makes the metric permanently red.

    ``actor`` is the verified principal and is an address by design. A well-meaning "scan the
    whole record" change would make every run fail on the attribution column, and the next person
    would relax the threshold rather than narrow the scan. The same holds for ``maker`` on the
    Hrz7 payload, which :func:`run_eval.review_texts` drops for the same reason.
    """
    row: dict[str, Any] = {**_CLEAN_ROW, "actor": "analyst@bank.example"}
    assert ev.pii_safety(ev.audit_texts([row]), _PLANTED) == 1.0
