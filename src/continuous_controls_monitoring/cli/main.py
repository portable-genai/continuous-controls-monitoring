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

from ..config import Container, build_container
from ..domain.models import MonitoredControl
from ..domain.monitoring_service import MonitoringService


def _service(container: Container) -> MonitoringService:
    return MonitoringService(
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


def _print(monitored: MonitoredControl) -> None:
    result = monitored.result
    verdict = "PASS" if result.passed else "FAIL"
    print(f"{result.control_id} [{result.test_kind.value}] {verdict}")
    print(f"  design: {result.design.rating.value}  operating: {result.operating.rating.value}")
    print(
        f"  findings: {len(result.findings)}  requires_human_review: {result.requires_human_review}"
    )
    if monitored.writeback_ref:
        print(f"  written back: {monitored.writeback_ref}")
    if monitored.review_ref:
        print(f"  routed to human review: {monitored.review_ref}")


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
    service = _service(container)
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()

    if args.command == "test":
        pack = next((p for p in service.packs if p.pack_id == args.pack_id), None)
        if pack is None:
            print(f"unknown pack_id: {args.pack_id}", file=sys.stderr)
            return 2
        _print(service.evaluate_pack(pack, as_of=as_of, tenant=args.tenant, actor=args.actor))
        return 0

    if args.command == "run":
        result = service.run(as_of=as_of, tenant=args.tenant, actor=args.actor)
        for monitored in result.monitored:
            _print(monitored)
        print(f"\n{result.passed_count} passed, {len(result.exceptions)} exception(s)")
        return 0

    return 2  # pragma: no cover - argparse requires a subcommand


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
