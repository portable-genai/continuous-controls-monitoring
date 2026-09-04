# Adoption FAQ

For an engineering lead forking this repo as their institution's continuous control-testing
service. The step-by-step is [`../ADOPTING.md`](../ADOPTING.md); this answers the "will it hurt
later?" questions.

### How do I rebrand it for my organisation?

`scripts/rename_fork.py` rewrites the package name (`continuous_controls_monitoring`, which is
also the console script), the `CCM_` env prefix (including the bare token that
`infra/terraform/render.tf.json` carries, so Terraform sets the same variable names on the
service), the Terraform `name_prefix` resource stem (`aud2-svc`) and the distribution / git id in
one pass. Preview with `--dry-run`, apply with `--yes`, then recreate the venv, `make install`,
and run `make gate`. The catalog id `continuous-controls-monitoring` is left alone unless you pass `--catalog-id`, so a fork
stays traceable to the entry it descends from. The script does the mechanical rename; the human
decisions (region, IdP, your packs, the evidence sources, the eval golden set) are the checklist
in `ADOPTING.md`.

### If several institutions fork this, how does each take upstream fixes?

Track upstream via **git tags**. The repo declares a core-vs-adopter-owned boundary
(`ADOPTING.md` section 2): upstream owns `domain/kernel.py`, `domain/testing.py`, `ports/`,
`tests/contract/`, the eval harness mechanics, CI and the Terraform stack; you own the `policy:`
block and the rest of `config/settings.yaml`, the fixtures and golden set, `adapters/onprem/*`
and `terraform.tfvars`. Because your packs live in configuration rather than in code, the usual
source of merge pain is already outside the merge.

### Can I write my own control tests without touching engine code?

Yes, and this is the repo's best property. A control-test pack is DATA: the test kind, the
evidence source, the cadence, the `PassCriteria` numbers and the gate severity. `load_packs` reads
them from the optional `policy:` block in `config/settings.yaml`, and when that block is absent
the shipped `default_packs()` apply as the reference. `validate_pack` and the
`pack_schema_validity` eval metric hold your packs to the schema, so a malformed pack fails a
build rather than silently grading nothing.

What you cannot do in configuration is add a new test KIND: a kind is a detector in
`domain/testing.py`, so a genuinely new way of testing a control is a small code change plus a
test, not a config edit.

### What do we have to supply that is not in this repo?

Four things, and none of them is code here:

1. **Your packs**, in the `policy:` block.
2. **The evidence sources.** `EvidenceScannerPort` needs credentials to read live configuration,
   access and transaction evidence in your estate. This is the widest privilege in the system and
   it is yours to scope.
3. **The `obligations-control-mapping` endpoints.** A control inventory to read, and somewhere to write effectiveness
   results back as evidence nodes. This repo keeps no parallel catalog by design.
4. **The review console.** An `human-review-console` deployment reachable at `HUMAN_REVIEW_URL`. The managed
   router REFUSES to swallow an escalation when this is empty, so a fork cannot ship rule R8
   unwired and green.

### How do I add a new outbound dependency (a new port)?

There is a fixed touch list and a contract test that enforces it. A port must be registered in
FIVE places or it runs with no enforcement at all: `ports/__init__.py` (`PORT_PROTOCOLS`),
`config.DEFAULT_BINDINGS`, a `Container` accessor, `config/settings.yaml`, and a `PortCase` in
`tests/contract/canonical.py`. Then bind it in all three families.
`tests/contract/test_port_parity.py` asserts set equality across the five. See
[`../../CONTRIBUTING.md`](../../CONTRIBUTING.md).

### Why is there no UI?

Because this is a control plane, not a screen. `make drop-ui` has been run, which is the one step
that removes `ui/` together with its npm dependabot ecosystem and its CI job consistently;
deleting the directory by hand would leave a dependabot ecosystem pointing at nothing and a CI job
with no work. Exceptions are reviewed in the `human-review-console`, which is where a reviewer already
works. If your fork needs its own screen, add it deliberately rather than reviving the template's.

### Does the gate run for my fork out of the box?

Yes. `make gate` is offline, credential-free and network-free (ruff, ruff format, mypy strict, the
whole suite except integration, and the eval), and the CI workflow references no `secrets.`, so a
fork's build is green immediately. You add secrets only when you wire the `gcp` profile. Note the
eval measures the REFERENCE packs and golden cases until you rebuild them for your own controls;
that is an explicit adoption step, not a silent pass.

### The eval reports high scores. Should we believe them?

Only because each metric is proved able to report something else.
`tests/unit/test_not_falsely_green.py` hands the metrics planted mutants and fails the build if
they still pass, and `tests/unit/test_eval_metrics.py` exercises the scorers directly. The
groundedness metric in particular scores the raw narration through the same validator the service
enforces, so it can actually go red.

### Will the demo rot after I diverge?

It is guarded, and the guard is inside the gate. A demo step lives in `demo.STEPS` and in
`walkthrough.CHECKS`, and `tests/unit/test_demo_surface.py` holds the two equal, so a claim the
demo makes but nobody verifies cannot exist. `make demo-selftest` runs the whole arc headless over
the real loopback server and exits non-zero when a claim stops being true. If you diverge, keep
the step keys and the `facts` dict the checks read.

### What is still open?

[`../practices-audit.md`](../practices-audit.md) carries the per-check verdict and the work list.
The two that matter most before production: binding the `agent-guardrail-gateway`, which matters more
here than in most repos because evidence records can carry operator-written text that reaches the
narrator, and registering this repo's metric bundle with `model-quality-gate` so `eval/run_eval.py --mode gate`
has an authority to ask. The Terraform stack is written, validated and tested against a mocked
provider; it has never been applied.
