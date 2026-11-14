# Architecture

One rule shapes everything: **the model proposes, code decides.** The model is good at reading a messy conversation. It is bad at being certain, consistent and auditable. So it gets exactly one job, and everything with consequences is plain code that can be tested and replayed.

## The path of one meeting

`kyc_copilot.run.process` is the single entry point; the CLI (`kyc-check`), the eval harness and the viewer all call it.

1. **Capture** (`capture.py`). Audio is transcribed on the machine with mlx-whisper (`whisper-large-v3-turbo`), keeping each word's timing and probability. Transcripts are cached by the audio's SHA-256. A device transcript (Apple's Voice Memos) can be read too, so two transcribers can be compared on the same recording. Nothing leaves the machine at this step.

2. **Extract** (`extract.py`). One call to `claude-opus-5-5` with structured output (`messages.parse` into a Pydantic schema). The transcript goes in inside `<transcript>` tags, marked as data, not instructions; known injection phrases are neutralised in the model's copy only (`guard.py`). The model returns candidate facts, each with a value, a confidence and **the exact words it came from**. Long transcripts are split at turn boundaries into bounded windows (`windows.py`).

3. **Check every quote** (`extract.locate`). Code finds each quote in the raw transcript and computes its character offsets. The model never supplies offsets. A quote that isn't there is rejected, and the model gets one retry with the reasons. A fact that still has no real quote is dropped and counted as a rejection, never kept silently.

4. **Decide** (all code, all deterministic):
   - `reconcile.py`: facts that disagree with each other or with the bank's file become a contradiction. Both values persist; nothing picks one (invariant I6).
   - `plausibility.py`: facts that can't all be true become doubts: funding larger than every stated source in that currency, a past event dated after the meeting, an implausible age, the model's own low confidence, an answer the client changed.
   - transcriber doubt: a fact whose quote touches a word Whisper was unsure of (probability under 0.5) gets an `unclear_audio` doubt.
   - `rules/`: nine bounce rules, each with a public source, fire on the facts. Hard triggers are flags, never blocks.
   - gaps: required fields with no fact. A field another field answers (a declared public function answers the PEP question) is not a gap.
   - `names.py`: when two names conflict, a plain note says whether it looks like one person written differently (a typo, an initial, a dropped title). It explains; it never merges.

5. **Show** (`viewer.py`, `viewer/index.html`). A FastAPI app. The transcript on the left, with every quoted phrase underlined; flags, key figures and doubts on the right. Clicking either side finds the other. Each critical figure has a play button for the seconds of audio behind its quote, and a Confirm button. **Download check** saves one printable HTML report.

## Cost and safety controls

- **Spend cap per call**, checked against the worst case before the call is made; cached replies are served before the check, so a used-up budget still allows anything already seen.
- **Disk cache** keyed by model, effort, system prompt and user prompt: re-scoring an old run costs nothing.
- **Viewer budget** across restarts, and an optional shared password on every route, for a link others open.
- **Prompt caching** on the system prompt.
- The key is read from the environment or a git-ignored `.env`, and never logged.

## The evaluation harness

`kyc-eval` runs a pipeline over the case folder and prints a scorecard.

- **Cases** (`eval/case_format.py`): a transcript, the bank's file, a document checklist, and the gold answer: facts with quotes, gaps, contradictions, expected flags, changed answers, and utterances no fact may quote. Loading a case validates every quote against its turn.
- **Consistency**: before scoring a model, `--pipeline gold` checks each case against the rules: the expected flags must be exactly what fires on the gold facts, and the gaps exactly what is missing, both ways. A mismatch means the case or a rule is wrong.
- **Graders**: typed values match exactly; free text matches on content words, strictly for critical fields. A wrong critical value with no warning on it is a **silent wrong value**, the number that matters most; the scorecard names each one.
- **Pipelines**: `gold` (must score 1.00), `empty` (zero recall), `model` (the real thing), each run on clean or `--noisy` transcripts; `capture` scores recordings of a case's script.

## The rest of the system

`service.py`, `store/` and `workflow/` hold the case lifecycle: an append-only SQLite store (corrections supersede, nothing is updated or deleted), a transition table that is the only way a case changes state, and gate events with actor, role and reason. They are tested (crash injection on every write path) but not yet wired to the viewer; they are the foundation for the human gates in the spec.
