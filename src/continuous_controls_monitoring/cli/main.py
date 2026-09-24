"""Minimal stdlib CLI: run a control test, or a full monitoring run (argparse, no extra deps).

The offline CLI runner is the scheduling seam for the ``local`` profile: under ``gcp`` the run
is driven by Cloud Scheduler / Workflows, so the hard gate stays SDK-free. Rule R8 applies on
this path too: an exception is routed from inside the service, in the same call that produced it.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from hex_service_kit.logging import configure_logging

from ..adapters.controls import RecordingReviewRouter
from ..config import Container, build_container
from ..domain.models import MonitoredControl
from ..domain.monitoring_service import MonitoringService


def _service(
    container: Container, review_router: RecordingReviewRouter | None = None
) -> MonitoringService:
    return MonitoringService(
        audit=container.audit,
        inventory=container.control_inventory,
        scanner=container.evidence_scanner,
        control_evidence=container.control_evidence,
        writeback=container.writeback,
        timeseries=container.timeseries,
        generation=container.generation,
        review_router=review_router if review_router is not None else container.review_router,
        tracer=container.tracer,
        policy=container.settings.policy,
    )


def _print(monitored: MonitoredControl, routing: RecordingReviewRouter) -> None:
    result = monitored.result
    verdict = "PASS" if result.passed else "FAIL"
    print(f"{result.control_id} [{result.test_kind.value}] {verdict}")
    print(f"  design: {result.design.rating.value}  operating: {result.operating.rating.value}")
    print(
        f"  findings: {len(result.findings)}  requires_human_review: {result.requires_human_review}"
    )
    if monitored.writeback_ref:
        print(f"  written back: {monitored.writeback_ref}")
    outcome = routing.outcome_for(monitored.result.pack_id).value
    print(f"  human review hand-off : {outcome} {monitored.review_ref}".rstrip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="continuous_controls_monitoring")
    sub = parser.add_subparsers(dest="command", required=True)

    test_cmd = sub.add_parser("test", help="Run one control's test by pack id.")
    test_cmd.add_argument("pack_id")
    test_cmd.add_argument("--actor", default="cli-user@bank.example")
    test_cmd.add_argument("--tenant", default="demo-bank")
    test_cmd.add_argument("--as-of", default="", help="ISO date; empty means today.")

    run_cmd = sub.add_parser("run", help="Run every configured control test.")
    run_cmd.add_argument("--actor", default="cli-user@bank.example")
    run_cmd.add_argument("--tenant", default="demo-bank")
    run_cmd.add_argument("--as-of", default="", help="ISO date; empty means today.")

    args = parser.parse_args(argv)
    container = build_container()
    # Idempotent: a process that is both an API app and a CLI configures once.
    configure_logging(container.settings.profile, service="continuous-controls-monitoring")
    # Rule R8 on the CLI path too, and the same report of what happened to each hand-off.
    routing = RecordingReviewRouter(container.review_router)
    service = _service(container, routing)
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()

    if args.command == "test":
        pack = next((p for p in service.packs if p.pack_id == args.pack_id), None)
        if pack is None:
            print(f"unknown pack_id: {args.pack_id}", file=sys.stderr)
            return 2
        _print(
            service.evaluate_pack(pack, as_of=as_of, tenant=args.tenant, actor=args.actor),
            routing,
        )
        return 0

    if args.command == "run":
        result = service.run(as_of=as_of, tenant=args.tenant, actor=args.actor)
        for monitored in result.monitored:
            _print(monitored, routing)
        print(f"\n{result.passed_count} passed, {len(result.exceptions)} exception(s)")
        return 0

    return 2  # pragma: no cover - argparse requires a subcommand


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
