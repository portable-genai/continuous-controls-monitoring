# ARCHITECTURE: Continuous Controls Monitoring (Aud2)

Hexagonal ports-and-adapters. A pure-stdlib domain core speaks only to ports (`typing.Protocol`s);
adapter families implement them; one env var (`CCM_PROFILE`) swaps the
whole stack with no domain edits.

Profile selection is an exact lookup. Every declared profile has an entry for every port; when
two profiles intentionally reuse one adapter, both entries name it. A missing local or exit
binding never inherits `gcp`, so it cannot import a managed SDK or change data custody silently.

`local` runs the real API, orchestration and deterministic domain with local or synthetic edges.
It may reduce OCR/narration quality, throughput, durability, enterprise identity, managed safety
and telemetry, but it does not change figures, evidence links, escalation rules or schemas.
`make portability` executes this boundary. If a primary managed operation is ever added as a
construction-only seam, the same change must name it in `managed_readiness.py` and refuse both API
startup and Terraform serving authorization until its live integration test exists.

## Layout (`src/continuous_controls_monitoring/`)
- `domain/` : pure stdlib, no cloud/framework imports. `kernel.py` (vertical-neutral types,
  `StrEnum` taxonomies from the commons), `models.py` (the control-monitoring artifacts:
  controls, packs, evidence, findings, results), `testing.py` (the pure `ControlTestEngine`),
  `packs.py` (config-owned test packs + schema validation), `narration.py` (the model-narration
  boundary, schema-validated and groundedness-checked), `monitoring_service.py` (the orchestration
  around the engine), `pii.py` (the jurisdiction pattern selection + order).
- `ports/` : `@runtime_checkable` Protocols (`AuditSinkPort`, `ReviewRouterPort`,
  `ControlInventoryPort`, `EvidenceScannerPort`, `ControlEvidencePort`, `EffectivenessWritebackPort`,
  `TimeSeriesExportPort`, `GenerationPort`; identity uses the commons `IdentityPort`), re-exported
  once with the `PORT_PROTOCOLS` map. `identity.py` adds
  this service's own identity vocabulary: what an adapter DECLARES about the end-user
  authentication it provides (`VERIFIED` / `CLIENT_ASSERTED` / `UNIMPLEMENTED`), which is what the
  loopback exposure guard reads, plus the refusal type that carries a status and a reason when no
  end user can be authenticated at all.
- `adapters/{local,gcp,onprem}/` : one adapter per port per profile. GCP imports are lazy.
  `adapters/_review_payload.py` is the shared, redacted conversion to the review kit's wire shape.
- `config.py` : `Settings` + `Container` (lazy DI, dotted `module:Class` bindings loaded from
  `config/settings.yaml`).
- `api/` : FastAPI app wired with the commons identity / S2S / fail-closed helpers.
- `cli/` : a stdlib argparse CLI.
- `agent/` : the optional-but-scaffolded agent surface. `tools.py` holds plain Python callables
  that delegate to the domain services (no business logic of their own) and route escalations
  like every other surface; `agent_card.py` builds the A2A discovery card served at
  `/.well-known/agent-card.json`. Nothing here needs ADK or a cloud SDK to import or test:
  `build_function_tools()` is the single lazily-imported runtime seam.

## Surfaces outside `src/`
- `scripts/` : the demo surface. `demo.py` holds the scripted arc and drives the REAL services;
  `render_ui.py` paints its panels as dependency-free static HTML; `demo_server.py` serves the
  same panels live, one real step per click; `walkthrough.py` drives that server over loopback
  HTTP and asserts every step, which is what lets the presenter tool double as the unattended
  self-test. `portability_demo.py` and `check_docs_links.py` are standalone checks. Nothing here
  is imported by `src/`, and `.dockerignore` keeps all of it out of the serving image.
- `ui/` : REMOVED. Aud2 has no user-facing panel slice in its build plan, so `make drop-ui`
  removed the micro-frontend, its npm dependabot ecosystem and its CI job together. An embeddable
  effectiveness dashboard is a recorded remaining gap, not a shipped surface.

## Test layout (`tests/`)
`unit/` (one module or service, driven by the REAL local adapters), `contract/` (the boundary
claims: conformance, the five-way port drift guard, behavioural parity), `integration/` (needs a
live service; marked so the offline gate deselects the whole directory) and `fixtures/` (shared
data only). `contract/canonical.py` holds ONE canonical request per port, so the structural and
behavioural suites cannot quietly assert different things.

## Request pipeline (`MonitoringService.evaluate_pack`, then the caller)
read the control from Rgc7 (never a parallel catalog) -> gather evidence (scanner + Rsk1 packs)
-> deterministic `ControlTestEngine` scores design and operating effectiveness with an explicit
`as_of` -> redact-before-audit (P-04) already-redacted WORM write -> write the result back to
Rgc7 as an evidence node and export the time-series row -> narrate an exception (schema-validated,
discarded unless grounded) -> **route every exception to the control owner via Hrz7 (R8)**. The
audit actor and the review maker are both the verified `Principal`, never the request body.
Routing happens in the same call that produced the result, on the API, CLI and agent surfaces
alike, so an exception never depends on a later job that may not exist. A control fails when any
finding reaches the pack's gate severity, and a dimension with no evidence is deficient, never a
silent pass.

## The port table
| Port | local | gcp | onprem |
|---|---|---|---|
| `AuditSinkPort` | hash-chained SQLite WORM (commons) | Cloud Logging WORM (lazy) | placeholder |
| `IdentityPort` | seeded personas (commons) | IAP assertion (lazy) | placeholder |
| `ReviewRouterPort` | review-kit outbox (offline, inspectable) | Hrz7 service intake over S2S | placeholder |
| `ControlInventoryPort` | fixture estate (tenant-scoped) | Rgc7 read API over S2S (lazy) | placeholder |
| `EvidenceScannerPort` | fixture snapshots | Cloud Asset Inventory + SCC (lazy) | placeholder |
| `ControlEvidencePort` | canned Rsk1 packs | Rsk1 evidence surface over S2S (lazy) | placeholder |
| `EffectivenessWritebackPort` | in-memory Rgc7 graph (inspectable) | Rgc7 write-back over S2S (lazy) | placeholder |
| `TimeSeriesExportPort` | in-memory rows (inspectable) | BigQuery (lazy) | placeholder |
| `GenerationPort` | deterministic grounded narrator | Gemini (lazy) | placeholder |

The on-prem placeholders RAISE. A review router that silently returned would convert every
consequential result into an unreviewed one, which is worse than a missing feature.

A port is registered in FIVE places: `ports/__init__.py` (`PORT_PROTOCOLS`), `config.py`
(`DEFAULT_BINDINGS` and a `Container` accessor), `config/settings.yaml` and
`tests/contract/canonical.py`. `tests/contract/test_port_parity.py` asserts set equality across
all five, so a port that is bound but unregistered (or registered but unbound) fails the build
instead of running with no enforcement. The full touch list is in `CONTRIBUTING.md`.

## Audit integrity
The local WORM log is hash-chained AND anchored: `audit_anchor_path` points at an external file,
on a different volume, that every append writes the chain head to. The chain alone catches an
edit, a deletion or a reorder; only the anchor catches a truncated tail, because a truncated
chain still verifies. `tests/unit/test_audit_anchor.py` proves both halves, including the
control case where the same truncation goes undetected without an anchor.
