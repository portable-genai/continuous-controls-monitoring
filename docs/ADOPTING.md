# Adopting this repo as your base

This repository (Aud2, Continuous Controls Monitoring) is a **common base** that a bank or other
regulated institution forks to build its own **always-on control-testing service**: it gathers
live evidence for each key control, grades design and operating effectiveness deterministically,
narrates an auditor-ready exception write-up, routes the consequential ones to a human, and writes
the result back as evidence. It ships a reusable hexagonal core (a pure-stdlib domain, typed
ports, three swappable adapter profiles, a green offline gate) plus a fully worked control-testing
vertical you can keep, reseed, or retune.

This guide is the step-by-step for making it yours. It has two halves: a **mechanical rebrand**
(one script) and the **human decisions** the script cannot make for you.

> Related reading: [`ARCHITECTURE.md`](../ARCHITECTURE.md) (the port table and topology),
> [`CONTRIBUTING.md`](../CONTRIBUTING.md) (adding an adapter, adding a port), the
> [`faq/`](faq/) directory, [`model-card.md`](model-card.md) (the model boundary),
> [`practices-audit.md`](practices-audit.md) (the per-check verdict).

This is a **control-plane service with no end-user screen**: `make drop-ui` has been run, so
there is no `ui/` directory to theme and the UI-shaped adoption steps do not apply.

---

## 1. What you keep vs what you rewrite

The core is hexagonal, and the boundary between reusable machinery and the control-testing
vertical is a physical module split with an enforced dependency direction (practices-audit check
A7). `domain/kernel.py` owns the vertical-neutral contracts; `domain/models.py` holds this
vertical's artifacts.

| Layer | Where | For your control library |
|---|---|---|
| **Vertical-neutral machinery** | `domain/kernel.py` (`Citation`, `AuditEvent`, `Severity`, `Decision`), every Protocol in `ports/`, the container wiring in `config.py` | keep untouched |
| **The grading engine** | `domain/testing.py`: per-kind detectors emitting `ControlFinding`s, `compute_verdict` against the pack's gate severity, each dimension scored separately, no LLM and no clock (it takes an explicit `as_of`) | keep untouched; it is what makes an always-on test replayable |
| **Policy (your numbers)** | the control-test packs, which are DATA: kind, evidence source, cadence, `PassCriteria` and gate severity. Defaults live in `domain/packs.py:default_packs()`; a deployment overrides them from the optional `policy:` block in `config/settings.yaml` via `load_packs`. Plus the jurisdiction list in `domain/pii.py` and the thresholds in `eval/run_eval.py` | change by configuration, not engine code |
| **Vertical (the artifacts)** | `domain/models.py` (`ControlTestPack`, `ControlTestResult`, `ControlFinding`, `Dimension`, `EffectivenessRating`, `EvidenceRecord`, `InventoryControl`), `domain/narration.py`, `domain/monitoring_service.py`, the fixtures and the eval golden set | rewrite for your control taxonomy |

If your product is another *evidence in, verdict out* testing engine, the hexagon, the three
profiles, the packs-as-data mechanism, the eval gate and the Hrz7 review routing transfer
directly; you replace the pack definitions and the evidence sources.

## 2. Core-vs-adopter-owned files (so upstream merges stay mechanical)

Upstream keeps evolving these; avoid diverging from them so you can pull fixes cleanly:

- **Upstream-owned** (take our changes): `domain/kernel.py`, `domain/testing.py`, `ports/`,
  `tests/contract/`, the eval harness mechanics (`eval/run_eval.py`), the CI workflows, the
  hexagon wiring (`config.py` `Container`) and the deploy stack in `infra/terraform/`.
- **Adopter-owned** (yours; expect to edit): the `policy:` block in `config/settings.yaml` and
  every other value there, the default packs if you replace rather than override them, the
  fixtures and the golden eval dataset, `adapters/onprem/*`,
  `infra/terraform/terraform.tfvars`, and the regulator crosswalk section of `COMPLIANCE.md`.

Track upstream via git tags; rebase your adopter-owned changes onto each release rather than
merging `main` continuously.

## 3. The mechanical rebrand (one script)

`scripts/rename_fork.py` rewrites the package name (`continuous_controls_monitoring`, which is
also the console script), the `CCM_` env prefix (including the bare token that
`infra/terraform/render.tf.json` carries so Terraform sets the same variable names on the
service), the cloud resource stem (`aud2-svc`, the Terraform `name_prefix`) and the distribution /
git id in one pass. Preview first, then apply:

```bash
# Preview (writes nothing):
python scripts/rename_fork.py --package acme_controls_monitor --env-prefix ACME \
    --resource acme-ccm --dry-run

# Apply:
python scripts/rename_fork.py --package acme_controls_monitor --env-prefix ACME \
    --resource acme-ccm --yes

# Then recreate the environment (the distribution name changed) and prove it is green:
python3.12 -m venv .venv && source .venv/bin/activate
make install
make gate
```

`--dist` defaults to the `--resource` value; pass it explicitly when your git id differs from your
resource stem. `--resource` is validated against the same regex the Terraform `name_prefix`
variable enforces, so a stem the stack would refuse fails here instead of at plan time. Add
`--include-docs` to sweep Markdown prose too. The catalog id `Aud2` is left alone unless you pass
`--catalog-id`, so a fork stays traceable to the entry it descends from. The script deliberately
does NOT touch the human decisions below.

## 4. The human decisions (the script can't make these)

1. **Region / residency.** The build defaults to `asia-southeast1` (MAS / Singapore), chosen once
   and shared: `config/settings.yaml:region`, `infra/terraform/render.tf.json:render_region` and
   the Terraform `region` / `allowed_regions` pair. Set all of them to your in-country region and
   re-run `infra/terraform/production_edge.tftest.hcl`, which refuses a region outside the
   allowlist at plan time. The effectiveness time series lands in `CCM_BIGQUERY_DATASET`: put that
   dataset in the same region, because the stack cannot pin a dataset it did not create.
2. **Identity / IdP.** This repo owns no login flow: the `gcp` profile verifies the IAP-injected
   assertion at the edge, `local` uses seeded dev personas, and `onprem` is a client IdP
   placeholder. Wire your issuer on the deployed service and set `CCM_IAP_AUDIENCE`. An unset or
   emptied audience refuses every caller rather than verifying without one.
3. **The control-test packs, which are the policy.** This is the main adoption task. Each pack
   says how one control is tested (kind, evidence source, cadence), what passes (`PassCriteria`:
   the gate severity, `max_recert_age_days`, `max_exceptions`, and the rest), and how severe a
   violation is. The shipped `default_packs()` are a REFERENCE. Put your own in the `policy:`
   block of `config/settings.yaml`: `load_packs` reads it, and when the block is absent the
   defaults apply. `validate_pack` and the `pack_schema_validity` eval metric hold your packs to
   the schema.
4. **Keep the two honesty rules.** A control fails when ANY finding reaches the gate severity, and
   a dimension with no evidence to test is DEFICIENT, never quietly EFFECTIVE. Absence of evidence
   of a problem is not evidence of its absence, and an always-on test that graded a silent control
   green would be worse than no test.
5. **The evidence sources.** `EvidenceScannerPort` gathers live configuration, access and
   transaction evidence, and `ControlEvidencePort` reads Rsk1's cloud control-evidence packs.
   Wiring those to your real estate is yours, and it is where the residency and least-privilege
   questions actually bite.
6. **Reference data is fictional.** Every fixture and the seeded evidence use obviously fake
   systems and `.example` domains. Replace them with your own synthetic data. **Do not point the
   scanner at production without your own security sign-off.**
7. **Eval golden set.** Rebuild the golden dataset for your packs: a fork inherits a green gate
   that measures the WRONG controls until you do. The four metrics
   (`effectiveness_accuracy`, `groundedness`, `pii_safety`, `pack_schema_validity`) and their
   thresholds are generic; the golden cases are yours.
8. **Deployment posture.** Review the Dockerfile (digest-pinned base, non-root uid 10001),
   `infra/terraform/` (Org Policy, CMEK, a dry-run-first VPC-SC perimeter, the locked WORM log
   bucket) and the loopback-by-default binding before you expose anything. The WORM lock is
   irreversible: confirm `retention_days` before the first apply.

## 5. Do not duplicate the platform

This repo is one system in a catalog of composable GRC systems, and its boundaries are unusually
sharp because it both reads from and writes back to a sibling (see
[`faq/features-faq.md`](faq/features-faq.md) for the full map):

- **Rgc7** obligations and control mapping owns the control inventory. `ControlInventoryPort`
  READS it, and this repo keeps no parallel catalog. `EffectivenessWritebackPort` WRITES results
  back to Rgc7 as evidence nodes, so a coverage figure there reflects what was actually tested.
- **Rsk1** compliance assistant owns the cloud control-evidence packs (the former Rsk2 module),
  read through `ControlEvidencePort`.
- **Hrz7** human-review / maker-checker console: every `requires_human_review` exception is routed
  to it over the shared `review-kit` (rule R8); you wire your endpoint
  (`HUMAN_REVIEW_URL`), you do not re-implement the console.
- **Hrz5** observability plus immutable WORM audit: audit events and trace spans go to it.
- **Hrz4** AI-quality / model-risk gate: owns promotion. `eval/run_eval.py --mode gate` is the
  client half and refuses to run off the managed profile.
- **Hrz3** agent registry: this agent publishes its A2A card at
  `/.well-known/agent-card.json`; register it rather than inventing a discovery mechanism.

The guardrail gateway (Hrz1) is **not** integrated today. It becomes mandatory the moment
untrusted free text (an evidence record's operator note, say) reaches the narrator: see rule R1 in
[`../COMPLIANCE.md`](../COMPLIANCE.md).

## 6. Adoption checklist

- [ ] Ran `scripts/rename_fork.py`, recreated the venv, `make gate` green.
- [ ] Set the region in all three places (settings, `render.tf.json`, tfvars), put the BigQuery
      dataset in that region, and re-ran the Terraform residency tests.
- [ ] Wired your IdP audience on the deployed service (this repo owns no login flow).
- [ ] Wrote your control-test packs into the `policy:` block and validated them.
- [ ] Kept the gate-severity rule and the no-evidence-is-DEFICIENT rule.
- [ ] Wired `EvidenceScannerPort` and `ControlEvidencePort` to your real estate, with the
      least-privilege credentials that implies.
- [ ] Pointed `ControlInventoryPort` at Rgc7 and wired the effectiveness write-back.
- [ ] Replaced every synthetic fixture.
- [ ] Rebuilt the eval golden set for your packs.
- [ ] Reviewed the deploy posture (Dockerfile, Terraform, `retention_days`, bind address).
- [ ] Wired your Hrz7 review endpoint and decided which sibling services you integrate vs stub.
- [ ] Read [`model-card.md`](model-card.md) and closed its remaining controls before enabling the
      managed narrator.
- [ ] Recorded your baseline upstream tag so you can take future fixes.
