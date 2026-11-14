# Spec

The contract the code is built against. IDs here (I1–I12, S1–S9, H1–H4, M0–M6) appear in the code and tests.

## Capability

Given a synthetic client meeting (a recording or a transcript), what the bank already holds about the client, and a document checklist, produce:

- the facts the client stated, each linked to its evidence;
- the open gaps against what onboarding requires;
- the compliance flags the facts trigger;
- what doesn't add up (contradictions, changed answers, implausible values);

so the relationship manager (RM) can fix the file before it goes to compliance.

**Promise to the user:** "After the meeting, the file compliance receives is fuller, every fact shows where it came from, and nothing was decided for you."

**Scope of this build:** the pre-submission check (S2–S4 plus rules, plausibility and gaps), the evaluation harness, local capture, and the viewer. The human gates, the source-of-wealth narrative and the independent checker (S5–S9) are specified, not built.

## Invariants

Each one is traced to a test; the unimplemented ones are skipped by name so they stay visible (`tests/test_invariants_pending.py`).

| ID | Invariant | Status |
|---|---|---|
| I1 | Every fact has provenance: source, transcript span or document, extractor version, confidence. No provenance, not stored. | Enforced |
| I2 | The fact store and audit trail are append-only. A correction is a new record that supersedes the old one. | Enforced |
| I3 | A risk score comes only from the rules engine, from confirmed facts and a rule version. The model never outputs a score. | Pending (no scoring yet) |
| I4 | No case passes a gate without a signed human gate event: actor, role, decision, reason, rule version. | Enforced in the state machine |
| I5 | Critical fields stay `stated` until the RM confirms them. Unconfirmed critical fields widen the score range. | Partly: confirm-by-ear in the viewer; no score range |
| I6 | Contradictions are never resolved automatically. Both values persist until a human resolves them. | Enforced |
| I7 | Role-based views come from the data layer. The RM never sees score factors. | Pending |
| I8 | Hard triggers (PEP, high-risk jurisdiction, uncorroborated source of wealth) set a minimum risk band. | Partly: flags, no band |
| I9 | Every fact carries a purpose tag (`aml`, `advice`). This build writes only `aml`. | Enforced |
| I10 | Sensitive topics (health, religion) are never stored as facts. | Measured (privacy leaks: 0 in every run), not yet enforced by a filter |
| I11 | The same person can't be the RM and the approver on one case. | Enforced |
| I12 | Synthetic data only. No real client data anywhere. | Enforced by policy; every case is invented |

## The case lifecycle

A deterministic state machine; the model never chooses the next state. Allowed transitions are a table in code (`src/kyc_copilot/workflow/state_machine.py`); anything else raises and is audited.

```
created → dossier_ready → transcript_ingested → facts_extracted
  → presubmit_checked   (this build: reconcile, rules, plausibility, gaps)
      ├─ rm_fixed ──────→ facts_extracted       (the RM fixes the file; re-checked)
      └─ ready_for_rm_gate → awaiting_rm_confirmation
  → (RM gate, no unresolved contradiction) → facts_confirmed
  → analysing → analysed → checked → awaiting_compliance_review
  → (compliance gate) → approved | returned_to_rm | escalated
any state → suspended (operator) | failed_needs_human (retry budget spent)
prohibited rule → blocked
```

## Steps

| Step | Who | Does | Built |
|---|---|---|---|
| S1 Dossier | Agent with tools (stubs) | Baseline profile from what the bank holds | Stub data in cases |
| S2 Ingest | Code | Utterances with ids, speakers and (from audio) word timings | Yes |
| S3 Extract | Model, structured output | Candidate facts, each quoting its words | Yes |
| S4 Reconcile | Code | Contradictions against the bank's file; gaps against the checklist | Yes |
| S5 Gap prompts | Model, short | Up to three neutral next questions | No |
| G1 RM gate | Human | Confirm, edit or mark unknown | Confirm-by-ear in the viewer; no signed gate event yet |
| S6 Source of wealth | Model + tools | Narrative; every sentence maps to confirmed facts | No |
| S7 Score | Code | Band or range from versioned rules | No |
| S8 Independent check | A different model | Unsupported claims, missed triggers | No |
| G2 Compliance gate | Human | Approve, amend, return, escalate | State machine only |
| S9 Case pack | Code | Evidence pack and pre-fill export | Downloadable report |

## Hypotheses

| ID | Hypothesis | How it is tested |
|---|---|---|
| H1 | A model can extract KYC facts with real quotes, no silent wrong critical values, and the expected flags. | `kyc-eval` on frozen cases against preregistered bars ([evaluation](evaluation.md)) |
| H2 | The workflow survives crashes and suspensions without losing or duplicating facts. | Crash and suspend drills (store transactions are crash-tested; the full drill needs S6–S8) |
| H3 | The same inputs and rule version always give the same findings. | Replay test (passes) |
| H4 | An independent checker catches seeded errors in a draft. | Needs S8 |

Outside the code: does the problem matter to people outside one bank (interviews), and can real meetings be captured well enough (recordings in real rooms)?

## Milestones

| M | Deliverable | State |
|---|---|---|
| M0 | Schemas, taxonomy, state machine, append-only store | Done |
| M1 | Evaluation harness: case format, graders, scorecard | Done |
| M2 | Rules: bounce reasons with public sources, hard triggers as flags | Done (scoring deferred) |
| M3 | Extraction and reconcile, plausibility, hardening | Done |
| M4 | Durable workflow, both human gates, independent checker | Not started |
| M5 | Review screens for RM and compliance; session with practitioners | Viewer done; session not run |
| M6 | An open-weight model against the strong model on extraction | Not started |
