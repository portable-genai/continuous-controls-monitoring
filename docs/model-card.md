# Model card: Continuous Controls Monitoring (`continuous-controls-monitoring`)

This is a STARTER model card. It records the model boundary as built and the controls that must be
completed before a managed deployment. The deterministic control-test engine is the system of
record; the model is a bounded, replaceable component that writes one paragraph.

## What the model does, and does not do

- **Does**: draft the exception write-up for a control test the engine has ALREADY graded. It
  receives a prompt built by `domain/narration.build_prompt` from the engine's own figures and
  returns JSON.
- **Does NOT**: produce any effectiveness rating, finding, verdict, severity or escalation
  decision. Design and operating effectiveness, the findings and the pass or fail all come from
  `domain/testing.py`, which has no LLM, no network and no clock and takes an explicit `as_of`.
  With the local narrator bound, every consequential field is identical, so a model change cannot
  move a rating.

## Boundary and validation

- The model is reachable through exactly one port, `ports/generation.py`, whose whole surface is
  `generate(prompt: str) -> str`. There is no second model seam.
- `domain/narration.py` owns three pure functions and the discipline lives in them:
  `narration_facts` extracts the grounding set of figures the engine produced; `build_prompt`
  assembles the instruction plus those facts with the DATA kept separate from the INSTRUCTION, so
  text that arrived on an evidence record cannot escalate the model's authority; and
  `validate_narration` parses the JSON reply, checks it against the declared schema, and REJECTS
  it if it introduces any figure not in the grounding set.
- A narration that fails validation is DISCARDED and the caller falls back to the engine summary.
  It is never passed through and never repaired.
- The `groundedness` eval metric holds this at `>= 0.99`, and
  `tests/unit/test_not_falsely_green.py` proves the metric can go red. A groundedness metric that
  could not go red would be decoration.
- Personal data is masked before the audit write, before the outbound review payload and before a
  tool result returns (`domain/pii.py`).
- Every consequential result sets `requires_human_review` and is routed to `human-review-console` (rule R8) in the
  same call; nothing auto-executes.

## Adapters and profiles

| Profile | Generation adapter | Behaviour |
|---|---|---|
| `local` | `adapters/local/generation.py` (`LocalNarrationGenerator`) | No model call. It restates the FACTS block the prompt carries, so every figure in its output is one the engine produced and the groundedness check passes offline. It exercises the REAL narration path rather than dodging the validation. |
| `gcp` | `adapters/gcp/generation.py` (`VertexNarrationGenerator`) | Gemini via `google.generativeai`, imported lazily as the first statement of `generate` so an offline caller gets an ImportError at call time rather than at construction. Model id pinned in the module as `_MODEL`, currently `gemini-3.5-flash`, with a system instruction that states the no-new-figures rule. |
| `onprem` | `adapters/onprem/generation.py` (`OnPremNarrationGenerator`) | Fail-fast placeholder: raises, naming the client-hosted model gateway to bind. |

## Remaining controls (TODO, repo owner)

- **Model id, version and region** (P-07): `gemini-3.5-flash` is a module constant, not a
  confirmed deployment decision, and it is not reachable from configuration: there is no
  settings key or environment variable for it. Confirm the id is served in your deployment region,
  pin the exact version, lift it into `config/settings.yaml`, and record it here. Gemini model ids
  are regional and an unavailable one fails at call time rather than at boot.
- **Prompt-injection screening** (rule R1): the `agent-guardrail-gateway` is not bound, and this is
  the highest-priority item for THIS repo specifically. Evidence records can carry
  operator-written text, so untrusted free text can reach the fact block. The
  instruction-and-data split in `build_prompt` is a mitigation, not a screen. Fail closed to the
  engine summary when the screen is unavailable.
- **Budget, rate limit and a kill switch** (P-10, P-11): there is no per-tenant token budget, no
  request rate limit, and no switch that forces deterministic-only operation. A continuous
  monitor runs on a cadence, so an unbounded narration path is a cost surface as well as a risk
  one. The fallback already exists (a rejected narration yields the engine summary); what is
  missing is a deliberate operator control.
- **Evaluation of the live model**: the offline eval scores the deterministic pipeline with the
  local narrator. Add a managed-profile run, registered with the `model-quality-gate` promotion gate (P-08, rule
  R5), that scores `groundedness` with the real model bound.
- **Reasoning trace**: the audit record carries the validated narration and the engine's figures,
  not the prompt and reply pair. `COMPLIANCE.md` P-07 records that as owed.

Until these are complete the system is safe to run offline (deterministic engine plus the local
narrator) and the managed model path is not production-cleared.
