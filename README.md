# kyc-meeting-copilot

A relationship manager at a private bank meets a new client and asks the onboarding questions. Then the file goes to compliance, and often comes back: the date of birth is missing, the source of wealth isn't explained, a relative in government was mentioned and nobody wrote it down. Each round trip costs days.

This tool checks the meeting before the file is submitted. Give it a recording or a transcript and, in about a minute, it returns:

- **every KYC fact the client stated, each linked to the exact words it came from;**
- the compliance flags those facts trigger (a politically exposed relative, a foundation, large funding), each rule citing the public regulation it comes from;
- what doesn't add up: an answer the client changed, a value that contradicts the bank's file, funding larger than all the wealth described, a date in the future;
- what was never said and must still be asked;
- the key figures, each with a play button for the seconds of audio it came from, so the RM can confirm them by ear.

It prepares the RM. It never makes a compliance decision.

![The viewer on a synthetic meeting: the transcript on the left with every quoted phrase underlined, flags and key figures to confirm on the right](docs/img/viewer-pep-and-changed-answer.png)

*All data in this repository is synthetic. No real people, clients or companies.*

## What it has shown

Scored against bars fixed before any paid run ([preregistration](eval/preregistration.md)), on two case sets:

| | Bar | Private set: 12 cases by a domain expert, 4 runs | Public set: 6 cases in this repo, 5 runs |
|---|---|---|---|
| Important facts found (critical recall) | ≥ 85% | 98–99% | 97–98% |
| Facts that are correct (precision) | ≥ 90% | 94–96% | 95–97% |
| Wrong important values with no warning | 0 | **0 in every run** | 0, 2, 0, 1, 1 (see below) |
| Quotes that aren't the client's real words | ≤ 5% | 0 | 0 |
| Expected compliance flags raised | ≥ 90% | 100%, none wrongly | 100%; one known false flag |

About $0.04 a meeting with `claude-opus-5-5`.

The public set shows where the method is weak, and the silent wrong values there are worth reading. They were not misheard figures. One was correct but worded with more detail than the strict grader accepts ("Sister Agnieszka Kowalczyk, Deputy Minister of Infrastructure, Poland" for "sister, deputy minister of infrastructure"). The other came from a field nobody had defined: is the counterparty of an inheritance the grandmother, or the notary who settled the estate? Both are listed in the [evaluation write-up](docs/evaluation.md). Neither the cases nor the grader were changed after seeing them.

**The real weakness is capture.** When a transcript mishears a word cleanly ("780k" heard as "78k"), the model believes it: on a noisy transcript, every planted mishearing became a confident wrong fact. So the design adds three defences that don't depend on the model's confidence: a plausibility check in code (values that can't all be true), the transcriber's own doubt about each word, and confirm-by-ear for every key figure.

![Confirm-by-ear: Whisper heard "Lena Varga-Holm" as "Lain of Argyholm"; the transcriber flagged its doubt, and the play button plays exactly those words](docs/img/viewer-confirm-by-ear.png)

## How it works

```
recording ──► local Whisper (word timings and confidence) ──┐
transcript ─────────────────────────────────────────────────┴─► utterances
                                                                    │
                   ┌── Claude, structured output: candidate facts, each with a quote
                   ▼
   code: is every quote really in the transcript?  (no → retry once, then reject)
                   ▼
   code: reconcile against the bank's file ─► contradictions (never resolved automatically)
   code: plausibility                        ─► "can't all be true" doubts
   code: transcriber doubt on quoted words   ─► "listen to the clip"
   code: compliance rules (public sources)   ─► flags
   code: required fields with no fact        ─► gaps
                   ▼
   viewer: transcript ⇄ facts, key figures with play and confirm, downloadable report
```

The model does one job: read the conversation and propose facts with quotes. **Everything that decides anything is plain code**, versioned and tested: whether a quote is real, whether two values conflict, whether a rule fires, what is missing. The details, and why, are in [docs/architecture.md](docs/architecture.md) and the [decision records](docs/decisions.md).

## The domain work

Most of the effort is not the model call. It is knowing what a compliance officer will send back, and writing that down so code can check it:

- **A fact taxonomy** of 32 fields: which are required, which are critical (a wrong value is worse than a missing one), how a changed answer or a relative date is kept.
- **Nine bounce rules**, each citing its source: the EU AML Regulation 2024/1624, the OECD Common Reporting Standard, FATF statements. The loader refuses any rule without a public source ([sources](src/kyc_copilot/rules/SOURCES.md)).
- **A trap catalogue** for test cases: self-corrected amounts, a PEP relative mentioned after "no PEPs", legal vs beneficial owners, a health disclosure that must never become a fact, a client who changes an answer mid-meeting ([authoring guide](cases/AUTHORING.md)).
- **Twelve invariants** the system must never break, each traced to a test: no fact without provenance, contradictions never resolved automatically, sensitive topics never stored ([spec](docs/spec.md)).

The private case set was written by a practising wealth-management domain expert, who prefers not to be named; those cases are not published. The six public cases were written for this repository and cover most of the same traps.

## Try it

Needs Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/NassarX/kyc-meeting-copilot && cd kyc-meeting-copilot
uv sync --extra viewer
uv run pytest -q                       # fakes only: no key, no network, no spend
uv run kyc-eval run --pipeline gold    # every case checked against the rules
```

With an Anthropic API key in `.env` (copy `.env.example`):

```bash
uv run kyc-check --transcript viewer/samples/D02-pep-and-changed-answer.txt --meeting-date 2026-11-09
uv run kyc-eval run --pipeline model --cap 1.0      # the full eval, about $0.50
uv run kyc-viewer                                    # http://127.0.0.1:8000, then New meeting → Load a sample meeting
```

Audio needs Apple Silicon for the local transcriber: `uv sync --extra audio --extra viewer`, then record or upload in the viewer, or run `kyc-check --audio meeting.m4a`. To share the viewer behind a password and a spend budget, see [viewer/README.md](viewer/README.md).

## What's here

| Path | What |
|---|---|
| `src/kyc_copilot/extract.py` | The model call: prompt, structured output, quote check, retry, cost cap, cache |
| `src/kyc_copilot/reconcile.py`, `plausibility.py`, `rules/` | The code that decides: contradictions, doubts, compliance rules |
| `src/kyc_copilot/capture.py` | Local Whisper with per-word timing and confidence |
| `src/kyc_copilot/eval/` | Case format, graders, scorecard, `kyc-eval` |
| `src/kyc_copilot/viewer.py`, `viewer/` | The web app |
| `src/kyc_copilot/service.py`, `store/`, `workflow/` | The case state machine and append-only store: the foundation for the human gates, not yet wired to the viewer |
| `cases/` | The public test cases and how to write one |
| `eval/` | Preregistration, scorecards, audio test tools |
| `docs/` | Spec, architecture, evaluation, decisions; design system in [DESIGN.md](DESIGN.md) |

## Limits

- Synthetic meetings only. It has not seen a real meeting.
- No blind test cases yet: everyone who wrote cases had seen the rules.
- Amount thresholds compare in EUR only; there is no currency conversion.
- The free-text grader is strict, and some field meanings (an inheritance's counterparty) are undefined. Both show up as silent wrong values that aren't misreadings.
- A relative's long-past or minor public role can still raise a PEP flag. It errs toward an extra review, never a missed one.
- The human gates, the independent checker and the source-of-wealth narrative in the spec are not built.

## Licence

MIT, see [LICENSE](LICENSE). Third-party parts (ideas adapted from gbrain, the OFL fonts) are listed in [NOTICE.md](NOTICE.md).
