# Security FAQ

For AppSec and security architecture. Every answer names the file that is the evidence, so the
review can read the control rather than the claim.

### Who is the actor on a decision, and can a caller assert it?

A server-verified `Principal`, always. No request schema in `api/schemas.py` carries an `actor`
field: the audit actor and the review maker both come from the identity adapter. Under the `gcp`
profile the adapter verifies the IAP-injected assertion against the configured audience, against
IAP's own key set and against the issuer (`adapters/gcp/identity.py`); an unset or emptied
`CCM_IAP_AUDIENCE` REFUSES every caller, because `audience=None` means google-auth does not verify
the audience at all and would accept any Google-signed token from any project.
`tests/unit/test_iap_identity.py` runs in every gate and
`tests/unit/test_iap_crypto_matrix.py` runs the real verifier over locally minted assertions in
its own CI job.

There is no browser boundary to review: this is a control-plane service, `make drop-ui` has been
run, and there is no `ui/` directory.

### What is the largest risk in a system like this?

An always-on control test that grades a silent control green. The engine answers that
structurally rather than by review: a dimension with no evidence to test is DEFICIENT, never
quietly EFFECTIVE, and a control fails when ANY finding reaches the pack's gate severity. There is
no branch in `domain/testing.py` that turns absent evidence into a pass.

The second risk is the scanner's own privilege. `EvidenceScannerPort` reads live configuration,
access and transaction evidence, which is a broad read grant by nature. That grant is an adopter
control: this repo defines the port and its contract, and the credentials behind it are yours.

### What happens if the profile variable goes missing in production?

The process still binds the SDK-free adapters (the alternative is importing cloud SDKs that are
not installed), but nobody chose them, so every relaxation is withdrawn: the seeded dev personas
refuse to construct, no service-to-service scheme is selected, the dev CORS allowlist and the
`X-Dev-Persona` header are gone, the interactive docs are not registered, and the loopback
exposure guard refuses every route to any non-loopback peer. An emptied or mis-capitalised value
raises AT IMPORT, so the process fails to boot rather than serving on a posture nobody chose
(`config.py`, `tests/unit/test_profile_single_source.py`).

### Does setting the service-to-service token open anything?

No, and this is enforced rather than intended. The exposure guard's posture is derived from the
identity BINDING (the adapter declares `VERIFIED` / `CLIENT_ASSERTED` / `UNIMPLEMENTED`), never
from a credential. `CCM_S2S_TOKEN` authenticates a calling SERVICE and no end user.
`tests/unit/test_end_user_auth_posture.py` walks the guard's argument through the constants it
names and fails the build if a credential reappears at any depth, because it did once: setting the
token switched the guard off for the end-user routes it was protecting.

### Can the model exfiltrate or invent anything?

The model is reachable through exactly one port (`ports/generation.py`), and
`domain/narration.py` keeps the DATA separate from the INSTRUCTION in `build_prompt`, so text
that arrived on an evidence record cannot escalate the model's authority. The reply is parsed by
`validate_narration`, checked against the declared schema, and REJECTED if it introduces any
figure that is not in the grounding set `narration_facts` extracted from the engine's own result.
A rejected narration is discarded and the caller falls back to the engine summary. The
`groundedness` eval metric holds this at `>= 0.99` and `tests/unit/test_not_falsely_green.py`
proves it can go red. Prompt-injection screening through the `agent-guardrail-gateway` is **not**
wired yet, which matters here because evidence records can carry operator-written text.

### Where does personal data go?

Into evidence records and, from there, into nothing that leaves unmasked. Redaction runs before
the audit write, before a review payload leaves the process, and before a tool result returns from
`agent/tools.py`. The pattern set and its ORDER are this vertical's (`domain/pii.py`, national
rows first, universal rows last), drawn from the shared `pii-kit`. The `pii_safety` eval metric
holds this at `>= 0.99` and is proved able to go red.

### How is the audit trail protected?

Append-only and hash-chained, AND externally anchored. The chain catches an edit, a deletion or a
reorder; only the anchor catches a TRUNCATED TAIL, because dropping the newest rows leaves a
shorter chain that verifies perfectly. `audit_anchor_path` (`CCM_AUDIT_ANCHOR`) writes the chain
head to a file on another volume, and `tests/unit/test_audit_anchor.py` proves the detection,
proves the control case goes UNDETECTED without an anchor, and proves an append after truncation
refuses rather than re-anchoring. Under the managed profile the sink is a locked Cloud Logging
bucket (`infra/terraform/logging_worm.tf`), which provides non-rewritability itself.

### What about the effectiveness time series?

`TimeSeriesExportPort` appends each result to a BigQuery dataset under the managed profile. That
dataset is named by `CCM_BIGQUERY_DATASET` and is NOT created by this stack, so its region, its
CMEK binding and its access control are adopter responsibilities. A dataset in the wrong region
would put a residency-relevant record out of jurisdiction without the Terraform noticing, which is
why `ADOPTING.md` calls it out as a deliberate adoption step.

### What about supply chain?

Both lockfiles are committed and pin every dependency exactly; the catalog commons are pinned to
40-character COMMIT shas rather than tags, because a re-pushed tag changes what installs with no
diff in the lockfile. The base image is digest-pinned, Actions are SHA-pinned, dependabot covers
the ecosystems this repo actually has, and `pip-audit` is a HARD CI failure.
`tests/unit/test_repo_artifacts.py` asserts each of these from inside the repo, and it asks git
whether each pinned sha is a COMMIT object rather than an annotated tag object, which a regular
expression cannot tell apart.

### What is deliberately out of scope?

- **Login.** This repo authenticates nobody itself: the platform in front of it does.
- **Injection defence and output filtering.** Owned by `agent-guardrail-gateway`; not bound yet.
- **The control inventory.** Owned by `obligations-control-mapping`; read, never copied.
- **The remediation lifecycle after an exception.** Owned by `issue-remediation-capa`.
- **Network egress control.** VPC-SC governs access to Google APIs across perimeters, not
  arbitrary internet egress. The private-egress rule that lets this service reach the `obligations-control-mapping`
  register, the `compliance-advisory` evidence packs and the `human-review-console` and nothing else is an adopter network
  decision, called out in `COMPLIANCE.md` P-01.
