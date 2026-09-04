"""The orchestration: write-back integrity, the compliance-advisory dependency, cross-tenant denial,
no catalog.

These are the slice proofs that are about the pipeline rather than the pure engine: a result is
written back to obligations-control-mapping and is readable there attached to its control; removing
the compliance-advisory evidence source flips a dependent control from pass to fail; a cross-tenant
read is refused with a 403; and this repo registers no control-catalog store of its own.
"""

from __future__ import annotations

from datetime import date

import pytest

from continuous_controls_monitoring.config import (
    DEFAULT_BINDINGS,
    build_container,
)
from continuous_controls_monitoring.domain.models import EvidenceRecord
from continuous_controls_monitoring.ports.control_inventory import CrossTenantError

from tests.conftest import build_monitoring_service, local_settings
from tests.fixtures import sample_cases

_AS_OF = date(2026, 8, 1)


def _service_and_container():
    container = build_container(local_settings())
    return build_monitoring_service(container), container


def test_a_written_result_is_readable_from_rgc7_attached_to_the_control() -> None:
    """Write-back integrity: the effectiveness evidence lands on the tested control."""
    service, container = _service_and_container()
    pack = next(p for p in service.packs if p.pack_id == "pack-egress-config")
    monitored = service.evaluate_pack(
        pack, as_of=_AS_OF, tenant=sample_cases.TENANT, actor=sample_cases.ACTOR
    )
    assert monitored.writeback_ref
    nodes = container.writeback.read_evidence("SC-7-egress")  # type: ignore[attr-defined]
    assert len(nodes) == 1
    assert nodes[0]["control_id"] == "SC-7-egress"
    assert nodes[0]["passed"] is monitored.result.passed


def test_removing_the_rsk1_evidence_source_flips_a_dependent_control_pass_to_fail() -> None:
    """AC-2 recert evidence comes only from compliance-advisory; without it the control cannot be
    evidenced.
    """
    service, container = _service_and_container()
    pack = next(p for p in service.packs if p.pack_id == "pack-access-recert")

    with_rsk1 = service.evaluate_pack(
        pack, as_of=_AS_OF, tenant=sample_cases.TENANT, actor=sample_cases.ACTOR
    )
    assert with_rsk1.result.passed is True

    # Swap the compliance-advisory evidence port for one that returns nothing: the control now
    # fails.
    class _EmptyEvidence:
        def fetch(self, control_id: str) -> tuple[EvidenceRecord, ...]:
            return ()

    starved = build_monitoring_service(container)
    starved._control_evidence = _EmptyEvidence()  # type: ignore[assignment]
    without_rsk1 = starved.evaluate_pack(
        pack, as_of=_AS_OF, tenant=sample_cases.TENANT, actor=sample_cases.ACTOR
    )
    assert without_rsk1.result.passed is False, (
        "removing the compliance-advisory source must flip pass to fail"
    )


def test_a_cross_tenant_read_is_refused_with_403_not_404() -> None:
    container = build_container(local_settings())
    inventory = container.control_inventory
    # A wholly unknown id is a 404-equivalent (None); a control in ANOTHER tenant is a 403.
    assert inventory.get_control("no-such-control", tenant=sample_cases.TENANT) is None
    with pytest.raises(CrossTenantError):
        inventory.get_control("OTHER-only-control", tenant=sample_cases.TENANT)


def test_this_repo_registers_no_control_catalog_store_port() -> None:
    """The control-triad boundary: continuous-controls-monitoring reads the inventory and writes
    results, it owns no catalog.

    Enforced structurally: the only inventory-facing ports are a READ port and a WRITE-BACK
    port. A control-catalog STORE port (one that would let this repo mint or own control
    membership) must never appear in the binding table.
    """
    ports = set(DEFAULT_BINDINGS)
    assert "control_inventory" in ports, "the read port must exist"
    assert "writeback" in ports, "the write-back port must exist"
    forbidden = {"control_catalog", "control_store", "inventory_store", "catalog_store"}
    assert not (ports & forbidden), (
        "continuous-controls-monitoring must not register a control-catalog store: "
        "obligations-control-mapping is the single system of record"
    )


def test_a_write_back_for_an_unknown_control_is_rejected() -> None:
    """continuous-controls-monitoring cannot mint a control by writing an evidence node to an id the
    inventory lacks.
    """
    from continuous_controls_monitoring.ports.writeback import UnknownControlError

    container = build_container(local_settings())
    writeback = container.writeback
    # Build a result for a control id that is not in any tenant's inventory.
    from dataclasses import replace

    orphan = replace(sample_cases.ESCALATING_RESULT, control_id="ghost-control")
    with pytest.raises(UnknownControlError):
        writeback.append_result(orphan, tenant=sample_cases.TENANT)
