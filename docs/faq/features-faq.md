# Features FAQ

For a product owner, an internal-audit lead or a delivery manager deciding what this system does,
what it refuses to do, and where its responsibility ends.

### What does it actually do?

It tests key controls continuously and grades them, rather than sampling them once a year. For
each control:

1. **Gather** the live evidence (`EvidenceScannerPort` for configuration, access and transaction
   evidence; `ControlEvidencePort` for Rsk1's cloud control-evidence packs).
2. **Grade** it (`domain/testing.py`): per-kind detectors emit `ControlFinding`s, each dimension
   (design, operating) is scored separately, and `compute_verdict` turns the findings into a PASS
   or FAIL against the pack's gate severity.
3. **Narrate** the exception (`domain/narration.py`): the model turns the engine's figures into an
   auditor-ready paragraph, and nothing else.
4. **Route and record**: a consequential result goes to the Hrz7 console (rule R8), the
   effectiveness result is written back to Rgc7 as an evidence node, and the score is appended to
   the effectiveness time series (BigQuery under the managed profile).

### What makes an effectiveness rating defensible?

Two rules in the engine, and one property:

- **A control fails when ANY finding reaches the gate severity.** The gate severity is per pack,
  so the bar is your policy rather than the engine's opinion.
- **A dimension with no evidence to test is DEFICIENT, never quietly EFFECTIVE.** Absence of
  evidence of a problem is not evidence of its absence, and an always-on test that graded a silent
  control green would be worse than no test at all.
- **The engine has no LLM, no network and no clock.** It takes an explicit `as_of`, so the same
  inputs always grade the same way and a rating can be replayed from the audit record months
  later.

### What is the model allowed to say?

Only the exception write-up, and only in terms of figures the engine produced.
`domain/narration.py` splits this into three pure functions: `narration_facts` extracts the
grounding set from the result, `build_prompt` assembles the instruction and the facts with the
DATA kept separate from the INSTRUCTION so retrieved text cannot escalate the model's authority,
and `validate_narration` parses the JSON reply, checks it against the declared schema and rejects
it if it introduces any figure not in the grounding set. A narration that fails validation is
DISCARDED and the caller falls back to the engine summary. See
[`../model-card.md`](../model-card.md).

### What will it refuse to do?

- **It will not grade a dimension it has no evidence for as effective.**
- **It will not let a narrated paragraph introduce a number.**
- **It will not auto-execute a consequential result.** An exception sets `requires_human_review`
  and is ROUTED to Hrz7 in the same call that produced it.
- **It will not keep a second control catalog.** The inventory is Rgc7's.

### Which surfaces expose it?

The FastAPI app (`POST /v1/controls/test` for one control, `POST /v1/run` for the whole set), the
argparse CLI (`test` and `run`), the agent tools (`test_control`, `run_monitoring`, advertised on
the A2A card at `/.well-known/agent-card.json`), and the eval harness. There is deliberately no
UI: this is a control-plane service and `make drop-ui` has been run.

### What does this repo own, and what does it integrate?

| Concern | Owner | How this repo touches it |
|---|---|---|
| Continuous control testing and effectiveness grading | **this repo (Aud2)** | it IS the engine. |
| The control inventory | **Rgc7** obligations and control mapping | READ through `ControlInventoryPort`. This repo keeps no parallel catalog. |
| Coverage and evidence in the obligation graph | **Rgc7** | WRITTEN BACK through `EffectivenessWritebackPort` as evidence nodes, so a coverage figure there reflects what was actually tested. |
| Cloud control-evidence packs | **Rsk1** compliance assistant (the former Rsk2 module) | READ through `ControlEvidencePort`. |
| Agent discovery and entitlements | **Hrz3** agent registry | this agent publishes a card; the registry owns discovery. |
| Model and agent promotion | **Hrz4** AI quality and model risk | `eval/run_eval.py --mode gate` asks Hrz4; the offline smoke mode never promotes. |
| Traces and the immutable audit sink | **Hrz5** agent observability | `AuditSinkPort` and `ObservabilityTracerPort`. |
| Human review and maker-checker | **Hrz7** human review console | `ReviewRouterPort` over the shared `review-kit`. This repo produces exceptions; it does not render a queue. |
| Prompt-injection defence and output filtering | **Hrz1** agent guardrail gateway | **not wired today.** It becomes mandatory the moment untrusted free text (an operator note on an evidence record) reaches the narrator (rule R1). |
| Grounded retrieval over an enterprise corpus | **Hrz2** enterprise knowledge base | not wired; this service reasons over evidence records, not documents. |
| Issue and CAPA lifecycle after an exception | **Aud3** issue remediation and CAPA | this repo raises the exception; the remediation lifecycle belongs there. |

### Can I demo it without a cloud project?

Yes, and the demo is code rather than a deck. `make demo` runs a presenter-paced walkthrough over
eight steps (opened, routine, escalation, redaction, review queue, audit, tamper, portability) on
its own loopback server; `make demo-selftest` runs the same arc headless and asserts every
narrated claim, so a claim that stops being true fails a build rather than a meeting;
`make demo-static` renders the same audit-first panels to static HTML for screenshots.

### What is not built yet?

The honest list is [`../practices-audit.md`](../practices-audit.md) and the `TODO (repo owner)`
rows in [`../../COMPLIANCE.md`](../../COMPLIANCE.md). The two that matter most for a production
decision: the Hrz1 guardrail binding before untrusted text reaches the narrator, and registering
this repo's metric bundle with Hrz4 so `--mode gate` has an authority to ask.
