# Decisions

Short records of the choices that shape the system, with what was rejected and why.

## 1. The model proposes; code decides

**Decision.** The model extracts candidate facts with quotes. Contradictions, rules, plausibility, gaps and the case's next state are all plain code.

**Why.** A compliance file needs answers that are the same every time and can be explained line by line. A model's judgement is neither. Keeping the model to reading, and everything with consequences in code, makes the risky part testable and replayable (hypothesis H3 passes).

**Rejected.** An agent that reads the meeting and decides what to flag. Fewer moving parts, but no way to audit why a flag fired or didn't, and no way to change a rule without re-testing a prompt.

## 2. Every fact quotes its words, and code checks the quote

**Decision.** Each fact carries the exact words it came from. Code finds them in the raw transcript and computes the offsets; the model never supplies positions. A quote that isn't there is retried once, then rejected and counted.

**Why.** It turns "the model said so" into "the client said so, here". It is the product's memorable thing in the viewer, and it catches invented facts mechanically: across every run, quote rejections were zero.

**Rejected.** Model-supplied character offsets (models miscount), and paraphrased evidence (can't be checked).

## 3. Bars before results; report every run

**Decision.** Preregister the bars, freeze and fingerprint the cases, then run. Report every run, including the bad ones. Fix the pipeline, not the grader, when a result is wrong for a fixable reason.

**Why.** With twelve cases it is easy to fool yourself. The one grader change (exact match to content words) is recorded with its reason and both scores. When a silent wrong value turned out to be a bracketed note on a correct name, the fix went into the pipeline and both numbers stayed on record. The public set's silent wrong values were left as they came out.

## 4. Plausibility and doubts as code, not as model confidence

**Decision.** Values that can't all be true raise a doubt in code. The model's confidence is used too, but never alone.

**Why.** On the noisy case the model gave clean mishearings full confidence. A rule like "funding can't exceed every stated source in that currency" caught one of them for free; self-reported confidence caught none.

## 5. Transcribe locally; confirm by ear

**Decision.** Whisper runs on the machine and keeps word timings and probabilities. Every critical figure links to its seconds of audio.

**Why.** Audio of a client meeting is the most sensitive input, and it never leaves the machine. Word timings make two defences cheap: the transcriber's own doubt per word, and a play button that lets the RM hear exactly what was said. Once a word is misheard, the audio is the only place the truth still exists.

**Rejected.** A hosted transcription API: better diarisation, but the audio leaves the machine, and the second-transcriber check would lose its independence.

## 6. Synthetic data and public sources only

**Decision.** Every case and client is invented. Every rule cites a public text (EU AML Regulation 2024/1624, OECD CRS, FATF); the loader refuses a rule whose source isn't public or an interview.

**Why.** A KYC tool built on real files or internal checklists couldn't be shared, and couldn't be trusted to be free of them. Public sources also make each rule checkable by anyone.

## 7. Borrow, with credit

**Decision.** Three ideas were adapted from gbrain (MIT): a prompt-injection phrase guard, name-variant matching, and bounded windows for long inputs. Each file credits it.

**Why.** They solved problems this pipeline had (a transcript that tells the model to approve the file, a name spelt two ways, a long meeting) and were small enough to port and test. gbrain's own extractor was not used: it stores paraphrased claims without quote offsets, which breaks decision 2.
