# Preregistration: first extraction run on the private 12-case set

> Kept as written, as the record that the bars were fixed before any paid call. C01–C12 are the private evaluation set (C01 is public; C02–C12 were written by a domain expert and are not published). Results: `docs/evaluation.md`.

Preregistered 8 Nov 2026, before any paid call. Bars approved by the project owner before the run. Format and
completeness check: gstack `eval-plan prereg --check`. Run with `kyc-eval run --pipeline model`.

## Bars
- critical_recall >= 0.85 (higher is better). Miss: the RM retypes too much; tune the prompt or try a stronger setting.
- silent_wrong_critical = 0 (lower is better). Miss: the safety line is crossed; this is the stop-or-rethink signal if it survives one tuning round.
- precision >= 0.90 (higher is better). Miss: invented or loose facts cost RM trust.
- span rejections after the retry <= 5% of predicted facts (lower is better). Miss: the provenance rule (I1) is not workable as built.
- bounce_recall >= 0.90 on the cases' expected flags (higher is better). Miss: the pre-submission check misses what it exists for.
- Decision rule: a first, untuned run below the bars does not end the project. Bars still missed after one tuning round on frozen cases trigger the stop-or-rethink rule.

## Arms
- `claude-opus-5-5` (the default model), effort `medium`, adaptive thinking (always on for this model), structured output, prompt `extract-prompt-v0.1`, max_tokens 16000. Estimated ~$0.05-0.15 per case (about 4k input, 2-5k output at $4/$20 per 1M); the pilot settles the real figure.
- No second arm in the first run. A cheaper model (Sonnet 5.5, Haiku 5.5) is the owner's call after the first scorecard.

## Comparison
stack: none
why: one arm, scored by deterministic code graders against gold facts; no skill stack is loaded into the model under test.

## Decoys
- Gold and empty stubs are the scorer's controls: gold must score 1.00, empty must score zero recall (tested).
- 7 deliberately broken case copies: the consistency check catches all 7.
- In the cases themselves: C08's health detail must not become a fact; C12's noisy variant (not scored yet); seeded drafts per case.

## Stop rules
- Spend cap: $5 per run (`--cap 5`), $20 for all of step 5. The extractor refuses a call that could cross the cap (exit code 2).
- Pilot first: 3 cases (C01, C04, C07). Stop and review if the pilot shows a systematic failure (all quotes rejected, schema errors, refusals) or a per-case cost above $0.40.
- Any refusal or repeated API error stops the run for review, not a silent retry loop.

## Held-out exposure
| set | prior exposure (which runs, which models) | reservation (what this run may read) |
|---|---|---|
| C01-C12 (author cases) | none: no model has seen them | this run reads all; prompt tuning only after the case set is frozen and signed off |
| B01-B04 (blind cases) | not written yet | never used for tuning; scored once, on frozen versions |

## Deviations
- 8 Nov 2026, after run 1: the grader's free-text rule changed from exact (normalised) match to content-word matching (docs/evaluation.md). Reason: both "silent wrong critical" values and most precision misses were rewordings ("Father's estate" vs "his father's estate"), confirmed fact by fact before the change. Approved by the owner. The bars did not change. Run 1 is reported both ways: as first scored (precision 0.87, silent wrong 2) and rescored from cached replies at no cost (precision 0.95, silent wrong 0, critical recall 0.97, flag recall 1.00). No prompt was changed.
