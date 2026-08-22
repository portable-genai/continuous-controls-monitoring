# FAQ index

Answers to the questions different teams ask when evaluating, adopting or reviewing this
repository as a continuous control-testing base. Each file is written for a specific audience;
skim the one that matches your role.

| FAQ | For | Answers |
|---|---|---|
| [security-faq.md](security-faq.md) | AppSec / security review | server-side identity, what the evidence scanner is trusted with, secrets, supply chain, the audit chain |
| [portability-faq.md](portability-faq.md) | Architecture / cloud / exit planning | no-lock-in, the three profiles, the sovereign exit, the time-series export |
| [features-faq.md](features-faq.md) | Product / audit / delivery | what the grading engine decides, what the model is allowed to say, and the boundary with Rgc7 and Rsk1 |
| [adoption-faq.md](adoption-faq.md) | Engineering leads forking the repo | rename, upstream fixes, writing your own packs, what stays open |
| [compliance-faq.md](compliance-faq.md) | Compliance / internal audit / second line | why an effectiveness rating is defensible, maker-checker, residency, retention, model-risk evidence |

These FAQs deliberately do **not** re-document capabilities owned by sibling systems in the GRC
catalog. Where a concern belongs to another repo (the control inventory Rgc7, the cloud
control-evidence packs Rsk1, the guardrail gateway Hrz1, the human-review console Hrz7, the eval
platform Hrz4), the FAQ points at it and explains the boundary rather than duplicating it. See
[features-faq.md](features-faq.md) for the full "what this repo owns vs what it integrates" map.

This is a control-plane service with no end-user screen, so there is no UI to review: `make
drop-ui` has been run and there is no `ui/` directory.

Authority order for anything these pages disagree with: [`SPEC.md`](../../SPEC.md), then
[`ARCHITECTURE.md`](../../ARCHITECTURE.md), then [`COMPLIANCE.md`](../../COMPLIANCE.md), then
[`README.md`](../../README.md). These pages restate; they do not decide.
