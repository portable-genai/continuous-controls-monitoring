# Compliance FAQ

For compliance, internal audit and the second line. The mapping table with a file reference on
every row is [`../../COMPLIANCE.md`](../../COMPLIANCE.md); this page answers the questions that
come back after reading it.

### Is an effectiveness rating from this system defensible?

That is the reason the grading is pure code. `domain/testing.py` takes the evidence and an
explicit `as_of`, emits `ControlFinding`s from per-kind detectors, scores each dimension
separately and computes a verdict against the pack's gate severity. No LLM, no network, no clock,
so the same inputs always grade the same way and a rating quoted in a report can be replayed from
the audit record.

Two rules make the rating mean something:

- **A control fails when ANY finding reaches the gate severity**, and the gate severity is set in
  YOUR pack rather than by the engine.
- **A dimension with no evidence to test is DEFICIENT, never quietly EFFECTIVE.** Absence of
  evidence of a problem is not evidence of its absence. This is the rule that separates a real
  continuous-monitoring claim from a dashboard that goes green when a feed stops.

### Who signs off an exception?

A human, always, for anything consequential. `requires_human_review` and the call to
`ReviewRouterPort.route` are one act, not a flag plus an intention: the API, the CLI and the agent
tools all route in the same call that produced the result, and `tests/unit/test_review_routing.py`
asserts the routing rather than the flag. Under the managed profile the router REFUSES when no
console is configured, so a deployment cannot swallow an exception silently. The remediation that
follows belongs to `issue-remediation-capa`, not here.

### Does the evidence trail close the loop back to the control library?

Yes, and deliberately in one direction only. The control inventory is READ from `obligations-control-mapping`
(`ControlInventoryPort`), so this repo keeps no parallel catalog that could disagree with it, and
the effectiveness result is WRITTEN BACK to `obligations-control-mapping` as an evidence node
(`EffectivenessWritebackPort`), so a coverage figure there reflects what was actually tested
rather than what was mapped. The result is also appended to an effectiveness time series, which is
what lets a trend rather than a snapshot be shown.

### Where does the data live, and is residency enforced or just documented?

Enforced at deploy time, with one named exception. The region is chosen once (`asia-southeast1`)
and shared by the runtime and Terraform: `infra/terraform/variables.tf` validates the region
against the residency allowlist at plan, `org_policy.tf` pins `gcp.resourceLocations` to that
region's location group, and every regional resource (the CMEK key ring, the WORM log bucket, the
Cloud Run service) is created in it. `infra/terraform/production_edge.tftest.hcl` is the standing
proof, running against a mocked provider so it needs no project and no credentials.

The exception is the BigQuery dataset named by `CCM_BIGQUERY_DATASET`. This stack does not create
it, so it cannot pin its location or its CMEK binding. Putting it in the same region is an adopter
step, and it is called out in `ADOPTING.md` rather than left to be discovered.

### What about key management and least privilege?

One REGIONAL CMEK key with a 90-day rotation, and an explicit key binding for EACH service agent
that encrypts under it, because CMEK does not cascade (`infra/terraform/kms.tf`). One serving
identity holding only the roles a request needs, each traceable to a bound adapter, with
`logging.logWriter` write only so the process cannot read back the WORM trail it writes
(`iam.tf`). Exportable service-account keys are forbidden by org policy rather than merely
avoided, and a key creation raises an alert if one happens anyway.

The privilege that is NOT in the Terraform is the evidence scanner's read grant across your
estate. That is the widest permission this system needs and it is scoped by the adopter.

### How long is the audit trail kept, and can it be edited?

180 days by default, and the variable refuses anything below 180. The Cloud Logging bucket is
LOCKED by default, which is irreversible: once applied, retention cannot be reduced and the bucket
cannot be deleted for the full window, not even with project-owner rights. Confirm
`retention_days` before the first apply, and note that an audit function usually needs longer than
180 days: set your own standard first, because the lock cannot be loosened afterwards. DATA_READ
audit logging is enabled too, so a read of the evidence is itself recorded.

Offline the same guarantee is earned differently: the log is hash-chained AND externally anchored,
because a truncated tail leaves a shorter chain that verifies perfectly.

### What personal data does this system process?

Whatever the evidence records carry, which is why redaction runs before every boundary rather than
once at the end: before the audit write, before the outbound review payload, and before any tool
result returns. The jurisdiction rows and their ORDER are chosen in `domain/pii.py`. The
`pii_safety` metric holds this at `>= 0.99` and is proved able to go red.

### What model-risk evidence exists?

[`../model-card.md`](../model-card.md) records the model boundary as built: the model writes the
exception paragraph and nothing else, the prompt keeps data separate from instruction, and the
reply is schema-checked and rejected if it introduces any figure the engine did not produce, with
the engine summary as the fallback. The offline eval scores `effectiveness_accuracy`,
`groundedness`, `pii_safety` and `pack_schema_validity` on every change. What is NOT yet in place:
the managed model is not pinned to a confirmed model id and version, there is no token budget,
rate limit or kill switch, no live-model eval run has been registered with the `model-quality-gate` promotion
gate, and prompt-injection screening through `agent-guardrail-gateway` is not bound. That last one matters more here
than in most repos, because evidence records can carry operator-written text.

### Which regulations does this claim to satisfy?

None, on your behalf. The mapping in `COMPLIANCE.md` is to the CATALOG's own principles (P-01 to
P-13) and platform rules (R1 to R8). The crosswalk from those to MAS TRM, CPS 234, CPS 230, HKMA
or your own control standard, and the judgement that a control is SUFFICIENT, is explicitly
adopter-owned. No row should be quoted as regulatory assurance, and the second-line review of the
packs is bank-owned policy rather than a vendor default to inherit unexamined.

### What is still open at go-live?

The `Partial` and `TODO (repo owner)` rows in `COMPLIANCE.md`, each of which names exactly what is
missing. The ones that need a risk acceptance if you go live without them: rule R1 (the `agent-guardrail-gateway` binding), rule R5 and P-08 (the `model-quality-gate` metric bundle), P-10 (timeouts, circuit breaker and
a documented kill switch for the scanner and the outbound calls), the BigQuery dataset's region
and encryption, and P-01's private-egress rule, which depends on your own network.
