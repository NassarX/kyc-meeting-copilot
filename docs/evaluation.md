# Evaluation

The question: can a model pull KYC facts out of a meeting with real quotes, without passing a wrong important value silently, and raise the flags compliance would? Everything below was measured with `kyc-eval`, against bars fixed before the first paid call.

## Method

- **Bars, preregistered** on 8 Nov 2026 ([preregistration](../eval/preregistration.md)): critical recall ≥ 0.85; **silent wrong critical values = 0**; precision ≥ 0.90; quotes rejected after the retry ≤ 5%; expected-flag recall ≥ 0.90. One deviation is recorded there: after the first run, free-text grading moved from exact match to content words, because rewordings ("Father's estate" vs "his father's estate") were being scored as wrong values. The bars did not change, and the first run is reported both ways.
- **A silent wrong value** is a critical field (a name, amount, date, ownership share, nationality, tax residence, a public function) with a wrong value and no warning on it. A wrong value that a contradiction or a doubt flags is not silent: the RM is told to check it.
- **Frozen cases.** Each case set gets a fingerprint before any model sees it. Prompts are tuned only after the set is frozen, and every run is reported, not the best one.
- **Fresh runs.** Variation is measured with uncached runs; re-scoring an old run from cached replies is free and labelled as such.

## The private set: 12 cases by a domain expert

C02–C12 were written by a practising wealth-management domain expert, one trap per case (a PEP brother mentioned after "no PEPs", a registry figure that contradicts the client, a client who changes an answer to fit a product, an accountant who states the key figure, a health disclosure, a large uncorroborated source of wealth, a clean control, a noisy transcript). C01 is public. The private cases are not published.

**First version** (prompt v0.1), four fresh runs:

| | Run 1 | Run 2 | Run 3 | Run 4 |
|---|---|---|---|---|
| Precision | 0.95 | 0.96 | 0.97 | 0.96 |
| Critical recall | 0.97 | 0.98 | 0.99 | 0.97 |
| Silent wrong critical | 0 | 0 | 0 | 0 |
| Quote rejections | 0 | 0 | 0 | 0 |
| Flag recall / false flags | 1.00 / 0 | 1.00 / 0 | 1.00 / 0 | 1.00 / 0 |
| Privacy leaks | 0 | 0 | 0 | 0 |

**Final version** (prompt v0.2 with the hardening below, plausibility v0.2), four fresh runs:

| | Run 1 | Run 2 | Run 3 | Run 4 |
|---|---|---|---|---|
| Precision | 0.96 | 0.96 | 0.94 | 0.96 |
| Critical recall | 0.99 | 0.98 | 0.99 | 0.99 |
| Silent wrong critical | 0 | 0 | 0 | 0 |
| Quote rejections | 0 | 0 | 0 | 0 |
| Flag recall / false flags | 1.00 / 0 | 1.00 / 0 | 1.00 / 0 | 1.00 / 0 |
| Contradiction / changed-answer recall | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |

Run 1 of the final version first scored one silent wrong value: a correct beneficial owner with "(beneficiaries)" appended. The fix went into the pipeline, not the grader: a note in brackets is not part of a name, and it would also break matching against the bank's file. Re-scored from the same replies, that run has 0; both numbers were kept on record.

**What went wrong, and matters:**

1. **Noisy capture passes silently.** On the noisy case, four plausible mishearings (a name, nationality SI heard as SK, 40% as 14%, €780k as €78k) became four confident facts, in all four runs. The transcript held clues the model ignored. A plausibility check in code cut it to three (the €78k dividend is now smaller than the amount to invest, so it is flagged). Logic can't catch the rest. The model's self-reported confidence didn't either: it gave the mishearings full confidence.
2. **Legal owner recorded as beneficial owner.** In the foundation case the model named the foundation as beneficial owner of a company. The grader couldn't see it (gold had no fact there). In a real file this is the error that matters most.
3. **A denial dropped.** After a PEP remark, the client's flat "no" was not recorded. The flag still fired.

## The public set: 6 cases in this repo

C01 plus five demo meetings (D01–D05), written for this repository from the trap catalogue; gold facts were written from the transcripts by hand, never from model output. Five fresh runs (`eval/results/public-clean-run1..5.md`):

| | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 |
|---|---|---|---|---|---|
| Precision | 0.95 | 0.96 | 0.97 | 0.95 | 0.96 |
| Critical precision | 0.98 | 0.97 | 0.98 | 0.97 | 0.98 |
| Critical recall | 0.97 | 0.97 | 0.98 | 0.97 | 0.98 |
| Silent wrong critical | 0 | 2 | 0 | 1 | 1 |
| Quote rejections | 0 | 0 | 0 | 0 | 0 |
| Flag recall / false flags | 1.00 / 1 | 1.00 / 1 | 1.00 / 1 | 1.00 / 1 | 1.00 / 1 |
| Privacy leaks | 0 | 0 | 0 | 0 | 0 |
| Changed-answer recall | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Warnings on correct facts | 8 | 9 | 8 | 7 | 7 |

**The silent wrong values,** as the scorecard lists them:

| Run | Case | Field | Extracted | Expected |
|---|---|---|---|---|
| 4 | D01 | wealth_event.counterparty | Lindqvist and Aamodt practice | grandmother |
| 5 | D02 | pep.family_public_function | Sister Agnieszka Kowalczyk, Deputy Minister of Infrastructure, Poland (appointed last year) | sister, deputy minister of infrastructure |
| 2 | D01, D02 | (one each) | not recorded: that run kept no replies, and the scorecard did not yet name its silent wrong values | |

Neither recorded one is a misread figure:

- **D02** is correct, worded with more detail than the strict critical-text rule accepts. The fix is a stated format for public functions in the prompt, or grading this field by meaning; neither was applied after seeing it.
- **D01** is a definition gap. For an inheritance, the model named the notary who settled the estate as the counterparty; the case says the grandmother. The taxonomy never defines the field for an inheritance. The fix is a field definition, then a re-freeze of the cases.

Run 2's two, one in each of the same cases, were most likely the same two; that is unverified.

**The false flag** in every run is D05: the spouse's father was a local councillor in the 1990s. The model records it as a family public function and the PEP rule fires. A parent-in-law, a local role, decades ago, falls outside the usual definition. It errs toward an extra review, never a missed one; where to draw the line is a compliance question.

**Warnings on correct facts** are mostly D04, where the funding and the future date are meant to be doubted; the doubt then also lands on the correct value it was compared with.

**Noisy D01** (`eval/results/public-noisy.md`): three planted mishearings (the name, Norwegian heard as Nigerian, €1.8M heard as €1.3M) became three silent wrong values, the same failure as in the private set. Nothing in that transcript lets logic catch them; only the audio can.

## Catching misheard values

Since the model can't tell a clean mishearing from the truth, four defences sit outside it:

1. **The transcriber's own doubt.** Whisper scores each word. A fact whose quote touches a word under 0.5 gets "listen to the clip". On a synthetic recording degraded seven ways, no condition produced a silent wrong critical value; in the worst, the three wrong values were all flagged by the model's low confidence, and two also by the transcriber, independently. Cost: no extra warnings on clean or moderately noisy audio, and 3 to 7 in the worst.

   **Words that were never said.** In long silences or noise, Whisper sometimes writes text nobody spoke, and a fact quoting it passes the quote check, because the words really are in the transcript. On synthetic recordings of 12 case scripts with four 30-second gaps of silence or noise each, it invented a looping "the", stray words, a plausible full name ("Peter Vandenberg"), and, in one run whose transcript was not kept, a sentence with an amount ("$708"). So a fact also gets "listen to the clip" when its quote sits in a segment whose words average under 0.7. That caught 14 of 22 invented segments, including all 7 outside a repetition loop. One of those was the name, which had no word under 0.5. It flagged 12 of 541 real segments, mostly "Thank you" and "Date of birth" ([results](../eval/results/gap-probe.md), tool `eval/tools/gap_probe.py`). Whisper's own `hallucination_silence_threshold` was rejected: it deleted real speech next to the gaps and turned "160,000" into "60,000", a new silent wrong value. Limit: in a repetition loop, Whisper's confidence rises (the looping "the" went from 0.07 to 0.99, and its last 8 segments pass the rule), and the loop swallows the start of the next real sentence. Voice-activity detection before Whisper is the candidate fix. The threshold comes from synthetic audio and needs real recordings to confirm.
2. **Confirm by ear.** Every critical figure gets a play button for the exact seconds of audio behind its quote (built).
3. **Two transcribers.** Whisper against the device's own transcript on the same recording; a different number, date or name is flagged (scoring built; needs real recordings).
4. **Spoken read-back.** The RM recaps the key figures; code checks the recap (not built).

Synthetic speech mostly produced garbled mishearings, which the first two catch. Clean-sounding substitutions ("780k" as "78k") are the real risk, and only real recordings in real rooms can show how often they happen.

## Cost

About $0.04 a meeting, $0.45–0.50 for a full run of six or twelve cases with `claude-opus-5-5` at medium effort. The whole evaluation history above cost about $7.
