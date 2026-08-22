# Portability FAQ

For architecture, cloud governance and exit planning. The question underneath all of these is
"how do we leave, and how do we know the answer is true today rather than on the day it was
written?"

### What is the lock-in surface?

Every outbound dependency is a `@runtime_checkable` Protocol in `ports/`: audit, control evidence,
control inventory, evidence scanner, generation, identity, observability, review router, time
series and write-back. Each is bound per profile from `config/settings.yaml`. There is no cloud
SDK import anywhere in `domain/`, and the managed adapters import their SDK LAZILY inside the
method, so the other two families import with no SDK installed at all.

The one binding worth naming separately is `TimeSeriesExportPort`, which is BigQuery under the
managed profile. It is a port like any other, so the exit is an adapter rather than a migration,
but the historical series it holds is the thing you would actually need to move.

### What are the three profiles?

| Profile | What it is | Who it is for |
|---|---|---|
| `local` | SDK-free offline stack: seeded dev personas, a hash-chained SQLite WORM audit log, seeded evidence and inventory, a deterministic stub narrator | dev, test, CI, and the offline demo |
| `gcp` | the managed stack: IAP identity, Cloud Logging WORM, Gemini narration, BigQuery time series, HTTP clients to the sibling services | a managed deployment |
| `onprem` | fail-fast `NotImplementedError` placeholders | the sovereign exit: a client binds its own in-country implementations here |

`CCM_PROFILE` selects the family. Unset means the offline adapters bind but nobody chose them,
which withdraws every relaxation rather than granting one.

### Is the portability claim tested, or just documented?

Tested, three ways, all in the offline gate or one command:

- `tests/contract/test_port_parity.py` asserts set equality across all five homes of a port (the
  `PORT_PROTOCOLS` map, `config.DEFAULT_BINDINGS`, the `Container` accessor, `settings.yaml` and
  the canonical-call table), so a port cannot be added in four places and run unenforced. With ten
  ports here, that guard is doing real work.
- `tests/contract/test_behavioral_parity.py` proves the offline family ANSWERS, the on-premises
  family RAISES and the managed family REFUSES rather than silently succeeding. It matters most on
  the write-back and time-series seams, where a placeholder that quietly returned success would
  make the evidence trail look complete while writing nothing.
- `make portability` is the executable claim: named checks with a pass or fail each, exiting
  non-zero on any failure. The stronger SDK-free proof lives in
  `tests/contract/_sdk_free_probe.py`, which BLOCKS the `google` import in a fresh interpreter
  rather than hoping the machine has none installed.

### How do we actually exit?

[`../onprem-migration.md`](../onprem-migration.md) is the path. The short version: the domain is
pure stdlib and moves unchanged; the audit trail exports to and restores from JSON Lines; what you
implement is one adapter per port under `adapters/onprem/`, each of which currently raises with a
message naming what to bind. Nothing in `domain/` has to change, which is the point of the split.
Plan the time-series migration separately: the port makes the code portable, but the accumulated
history is data you have to move.

### Can it run with no model at all?

Yes, and that is the load-bearing property rather than a convenience. Every effectiveness rating,
finding and verdict is produced by `domain/testing.py`, which has no LLM, no network and no clock.
With the stub narrator bound, every consequential field is identical and only the exception
paragraph changes. Even that has a fallback: a narration that fails validation is discarded and
the engine summary is used. See [`../model-card.md`](../model-card.md).

### Is the data residency claim portable too?

Mostly. The region is chosen once and shared by the runtime and Terraform:
`config/settings.yaml:region`, `infra/terraform/render.tf.json:render_region`, and the Terraform
`region` / `allowed_regions` pair, which refuses an unapproved region at plan time. The honest
exception is the BigQuery dataset named by `CCM_BIGQUERY_DATASET`: this stack does not create it,
so it cannot pin its location, and putting it in the same region is an adopter step rather than an
enforced one.
