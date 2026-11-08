"""M1 eval harness (beta 0 step 3, docs/spec.md).

- `input_facts` / `gold_facts`: the facts a case provides before extraction (dossier stub, checklist) and the
  facts extraction should find (gold, with spans).
- `consistency_problems`: checks the case author's expectations against the rules, so a case can't silently
  expect a bounce reason the rules never fire, or list a gap that isn't missing or skip one that is.
- `score_case`: the code graders (§9.2): provenance, span validity, fact precision and recall (all and critical),
  silent wrong critical values, contradiction recall, bounce-reason recall and false fires.
- `--pipeline model` runs real extraction (`kyc_copilot.extract`), with `--only`, `--cap` and `--no-cache`.
- `run_cases` / `main`: the scorecard over a folder of case files, and the `kyc-eval` command.

Pipelines are anything with `run(case) -> PipelineOutput`. `GoldStub` returns the gold answer (the harness
must score it perfectly); `EmptyStub` returns nothing. Real extraction plugs in at build step 5.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from kyc_copilot.domain.checklist import document_facts
from kyc_copilot.domain.enums import FactStatus, Purpose, SourceType
from kyc_copilot.domain.models import Fact, Provenance
from kyc_copilot.domain.values import normalize, values_match  # noqa: F401  (values_match re-exported)
from kyc_copilot.eval.case_format import CaseFile, CaseFormatError, check_span, load_case, utterance_index
from kyc_copilot.reconcile import find_conflicts
from kyc_copilot.rules import BounceReasons, Outcome, evaluate, load_bounce_reasons
from kyc_copilot.taxonomy import Taxonomy, load_taxonomy

DEFAULT_CASES = Path(__file__).parents[3] / "cases"


# ---------- facts from a case ----------

def _fact(case: CaseFile, field_: str, subject_ref: str | None, value, prov: Provenance, by: str,
          status: FactStatus = FactStatus.STATED) -> Fact:
    return Fact(case_id=case.case_id, field=field_, subject_ref=subject_ref, value=value, confidence=1.0,
                purpose=(Purpose.AML,), provenance=(prov,), created_by=by, status=status)


def current(facts: Iterable[Fact]) -> list[Fact]:
    """Facts that state a value now: an answer the client later changed (superseded) is history, kept but not used
    by the rules, reconcile or gaps."""
    return [f for f in facts if f.status is not FactStatus.SUPERSEDED]


def input_facts(case: CaseFile) -> list[Fact]:
    """What the bank holds before the meeting: the dossier stub and the document checklist."""
    prov = Provenance(source_type=SourceType.DOSSIER, source_ref="dossier", extractor_version="dossier-stub")
    out = [_fact(case, d.field, d.subject_ref, d.value, prov, "dossier") for d in case.dossier]
    for item in case.checklist:
        out.extend(document_facts(case.case_id, item, "checklist"))
    return out


def gold_facts(case: CaseFile) -> list[Fact]:
    """What extraction should find in the transcript, each fact citing its gold spans."""
    out = []
    for g in case.gold.facts:
        prov = Provenance(source_type=SourceType.TRANSCRIPT, source_ref="transcript", span_offsets=g.spans,
                          extractor_version="gold")
        out.append(_fact(case, g.field, g.subject_ref, g.value, prov, "gold"))
    for g in case.gold.superseded:
        prov = Provenance(source_type=SourceType.TRANSCRIPT, source_ref="transcript", span_offsets=g.spans,
                          extractor_version="gold")
        out.append(_fact(case, g.field, g.subject_ref, g.value, prov, "gold", FactStatus.SUPERSEDED))
    return out


# A required field whose question another field can answer: a client who names a public function (their own or a
# relative's) has answered the PEP question, so asking them for a no-PEP declaration would be wrong (demo sample D02).
ANSWERED_BY = {"pep.none_declared": ("pep.self_public_function", "pep.family_public_function")}


def derived_gaps(facts: Iterable[Fact], taxonomy: Taxonomy) -> list[str]:
    """Required fields with no fact. Grouped fields: a missing group is one gap per required field; a group that
    exists but lacks a required field is a gap on that subject ('field@subject'). A field in ANSWERED_BY is not a
    gap when one of its answering fields is present."""
    facts = list(facts)
    present = {(f.field, f.subject_ref) for f in facts}
    fields_present = {f.field for f in facts}
    gaps = []
    for key, spec in taxonomy.fields.items():
        if not spec.required:
            continue
        if not spec.grouped:
            if key not in fields_present and not fields_present.intersection(ANSWERED_BY.get(key, ())):
                gaps.append(key)
            continue
        prefix = key.split(".")[0] + "."
        subjects = sorted({f.subject_ref for f in facts if f.field.startswith(prefix) and f.subject_ref})
        if not subjects:
            gaps.append(key)
        gaps.extend(f"{key}@{s}" for s in subjects if (key, s) not in present)
    return sorted(gaps)


def _fired(reasons: BounceReasons, facts: Sequence[Fact], case: CaseFile) -> set[str]:
    return {r.reason_id for r in evaluate(reasons, facts, case.as_of_date) if r.outcome is Outcome.FIRE}


def consistency_problems(case: CaseFile, reasons: BounceReasons, taxonomy: Taxonomy) -> list[str]:
    facts = input_facts(case) + current(gold_facts(case))
    fired, expected = _fired(reasons, facts, case), set(case.gold.bounce_reasons)
    problems = [f"{r}: expected in gold.bounce_reasons but does not fire on the gold facts"
                for r in sorted(expected - fired)]
    problems += [f"{r}: fires on the gold facts but is not listed in gold.bounce_reasons"
                 for r in sorted(fired - expected)]
    found = {(c.field, c.subject_ref) for c in find_conflicts(facts, [])}
    listed = {(c.field, c.subject_ref) for c in case.gold.contradictions}
    problems += [f"contradiction {f}@{s or '-'}: in gold but reconcile does not find it" for f, s in sorted(
        listed - found, key=str)]
    problems += [f"contradiction {f}@{s or '-'}: reconcile finds it but it is not listed in gold.contradictions"
                 for f, s in sorted(found - listed, key=str)]
    gaps = set(derived_gaps(facts, taxonomy))
    problems += [f"gold gap {g} is not missing: a fact for it exists" for g in case.gold.gaps if g not in gaps]
    problems += [f"gap {g}: required field is missing but not listed in gold.gaps"
                 for g in sorted(gaps - set(case.gold.gaps))]
    return problems


# ---------- grading match (graders only; reconcile keeps strict values_match) ----------

_STOP = frozenset("a an the of as in at for from to his her their its my our your is was are by on with".split())


def _content_words(text: str) -> list[str]:
    """Words that carry meaning, in order: normalised, possessive 's dropped, small function words removed."""
    words = re.findall(r"[a-z0-9]+", normalize(text).replace("\u2019", "'").replace("'s", ""))
    return [w for w in words if w not in _STOP]


def grade_match(field_: str, gold, pred, taxonomy: Taxonomy) -> bool:
    """Does a predicted value say the same thing as the gold value? Typed values and enums: exact (values_match).
    Free text, since a model rewords descriptions (run 1, 8 Nov): critical text needs the same content words in the
    same order; descriptive (non-critical) text matches when one side's content words contain the other's."""
    if values_match(gold, pred):
        return True
    spec = taxonomy.fields.get(field_)
    if spec is None or spec.type != "text" or gold.kind != "text" or pred.kind != "text":
        return False
    g, p = _content_words(gold.value), _content_words(pred.value)
    if not g or not p:
        return False
    if spec.critical:
        return g == p
    return set(g) <= set(p) or set(p) <= set(g)


# ---------- pipelines ----------

@dataclass(frozen=True)
class PipelineOutput:
    facts: tuple[Fact, ...] = ()
    contradictions: tuple[tuple[str, str | None], ...] = ()  # (field, subject_ref) of each contradiction found
    doubts: tuple = ()  # plausibility doubts (kyc_copilot.plausibility.Doubt): the facts named need RM confirmation


class Pipeline(Protocol):
    name: str

    def run(self, case: CaseFile) -> PipelineOutput: ...


class GoldStub:
    name = "gold"

    def run(self, case: CaseFile) -> PipelineOutput:
        return PipelineOutput(facts=tuple(gold_facts(case)),
                              contradictions=tuple((c.field, c.subject_ref) for c in case.gold.contradictions))


class EmptyStub:
    name = "empty"

    def run(self, case: CaseFile) -> PipelineOutput:
        return PipelineOutput()


PIPELINES: dict[str, type] = {"gold": GoldStub, "empty": EmptyStub}


# ---------- graders ----------

def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


@dataclass(frozen=True)
class CaseScore:
    case_id: str
    n_pred: int
    n_gold: int
    tp: int
    crit_pred: int
    crit_gold: int
    crit_tp: int
    silent_wrong_critical: int
    span_rejections: int
    missing_provenance: int
    contra_gold: int
    contra_found: int
    bounce_expected: int
    bounce_hit: int
    bounce_missed: tuple[str, ...]
    bounce_false_fires: tuple[str, ...]
    privacy_leaks: int = 0  # accepted facts quoting a forbidden (special-category) utterance, I10
    false_warnings: int = 0  # correct facts the plausibility check doubted (RM confirmation load)
    sup_gold: int = 0  # changed answers in gold (superseded statements)
    sup_found: int = 0
    silent_wrong: tuple[tuple[str, str, str, str], ...] = ()  # (field, subject, got, expected) for each one

    precision = property(lambda s: _ratio(s.tp, s.n_pred))
    recall = property(lambda s: _ratio(s.tp, s.n_gold))
    critical_precision = property(lambda s: _ratio(s.crit_tp, s.crit_pred))
    critical_recall = property(lambda s: _ratio(s.crit_tp, s.crit_gold))
    contradiction_recall = property(lambda s: _ratio(s.contra_found, s.contra_gold))
    bounce_recall = property(lambda s: _ratio(s.bounce_hit, s.bounce_expected))
    supersession_recall = property(lambda s: _ratio(s.sup_found, s.sup_gold))


def _accepted(case: CaseFile, facts: Iterable[Fact]) -> tuple[list[Fact], int, int]:
    """Drop facts with no provenance or a span that doesn't match the raw transcript (never silently: counted)."""
    utts = utterance_index(case.case_id, case.transcript)
    ok, rejected, unprovenanced = [], 0, 0
    for f in facts:
        if not f.provenance:
            unprovenanced += 1
            continue
        try:
            for p in f.provenance:
                for s in p.span_offsets:
                    check_span(case.case_id, utts, s, f.field)
        except CaseFormatError:
            rejected += 1
            continue
        ok.append(f)
    return ok, rejected, unprovenanced


def align_groups(facts: Sequence[Fact], gold: Sequence, taxonomy: Taxonomy | None = None) -> list[Fact]:
    """Group numbers are labels, not facts: an extractor may call the dividends 'wealth_event/1' where gold says
    'wealth_event/2'. Map each predicted group to the gold group of the same kind that shares the most matching
    (field, value) pairs, greedily, one-to-one. Groups with no overlap keep their label (and score as misses)."""
    def kind(ref: str | None) -> str | None:
        return ref.split("/")[0] if ref and "/" in ref else None

    overlap: dict[tuple[str, str], int] = {}
    for f in facts:
        for g in gold:
            if f.subject_ref and g.subject_ref and kind(f.subject_ref) == kind(g.subject_ref) \
                    and f.field == g.field and (grade_match(f.field, g.value, f.value, taxonomy) if taxonomy
                                                else values_match(f.value, g.value)):
                key = (f.subject_ref, g.subject_ref)
                overlap[key] = overlap.get(key, 0) + 1
    mapping: dict[str, str] = {}
    taken: set[str] = set()
    for (p, g), _ in sorted(overlap.items(), key=lambda kv: (-kv[1], kv[0])):
        if p not in mapping and g not in taken:
            mapping[p] = g
            taken.add(g)
    # A predicted label that collides with a gold label it was not mapped to is moved aside, so it can't
    # match the wrong group by accident.
    out = []
    for f in facts:
        ref = f.subject_ref
        if ref in mapping:
            ref = mapping[ref]
        elif ref in taken:
            ref = f"{ref}#unaligned"
        out.append(f if ref == f.subject_ref else f.model_copy(update={"subject_ref": ref}))
    return out


def score_case(case: CaseFile, output: PipelineOutput, reasons: BounceReasons, taxonomy: Taxonomy) -> CaseScore:
    accepted, rejected, unprovenanced = _accepted(case, output.facts)
    accepted = align_groups(accepted, case.gold.facts, taxonomy)
    old = [f for f in accepted if f.status is FactStatus.SUPERSEDED]  # scored apart, against gold.superseded
    accepted = current(accepted)
    sup_left = list(case.gold.superseded)
    sup_found = 0
    for f in old:
        hit = next((g for g in sup_left if (g.field, g.subject_ref) == (f.field, f.subject_ref)
                    and grade_match(f.field, g.value, f.value, taxonomy)), None)
        if hit is not None:
            sup_left.remove(hit)
            sup_found += 1
    gold = list(case.gold.facts)
    critical = taxonomy.critical_fields
    unmatched = list(range(len(gold)))
    doubted = {i for d in output.doubts for i in d.fact_ids}
    tp = crit_tp = silent = false_warn = 0
    silent_list = []
    for f in accepted:
        hit = next((i for i in unmatched if gold[i].field == f.field and gold[i].subject_ref == f.subject_ref
                    and grade_match(f.field, gold[i].value, f.value, taxonomy)), None)
        if hit is not None:
            unmatched.remove(hit)
            tp += 1
            false_warn += f.fact_id in doubted
            crit_tp += f.field in critical
        elif (f.field in critical and f.status is not FactStatus.CONTRADICTED and f.fact_id not in doubted
              and any(g.field == f.field and g.subject_ref == f.subject_ref for g in gold)):
            silent += 1  # a plausible wrong value for a critical field, not flagged
            silent_list.append((f.field, f.subject_ref or "-", _show(f.value), " or ".join(
                _show(g.value) for g in gold if g.field == f.field and g.subject_ref == f.subject_ref)))

    gold_contra = {(c.field, c.subject_ref) for c in case.gold.contradictions}
    expected = set(case.gold.bounce_reasons)
    fired = _fired(reasons, input_facts(case) + accepted, case)
    return CaseScore(
        case_id=case.case_id, n_pred=len(accepted), n_gold=len(gold), tp=tp,
        crit_pred=sum(f.field in critical for f in accepted), crit_gold=sum(g.field in critical for g in gold),
        crit_tp=crit_tp, silent_wrong_critical=silent, span_rejections=rejected, missing_provenance=unprovenanced,
        contra_gold=len(gold_contra), contra_found=len(gold_contra & set(output.contradictions)),
        bounce_expected=len(expected), bounce_hit=len(expected & fired),
        bounce_missed=tuple(sorted(expected - fired)), bounce_false_fires=tuple(sorted(fired - expected)),
        false_warnings=false_warn, sup_gold=len(case.gold.superseded), sup_found=sup_found,
        silent_wrong=tuple(silent_list),
        privacy_leaks=sum(any(o.utt_id in case.gold.forbidden_utterances for p in f.provenance for o in p.span_offsets)
                          for f in accepted),
    )


# ---------- scorecard ----------

def _show(value) -> str:
    """A value as one short readable string for the scorecard."""
    d = value.model_dump(mode="json")
    d.pop("kind", None)
    return ", ".join(str(v) for v in d.values() if v is not None)


def _fmt(v: float | int | None) -> str:
    return "n/a" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))


@dataclass
class Scorecard:
    pipeline: str
    versions: dict[str, str] = field(default_factory=dict)
    cases: dict[str, CaseScore] = field(default_factory=dict)
    problems: dict[str, list[str]] = field(default_factory=dict)

    @property
    def totals(self) -> dict[str, float | int | None]:
        c = list(self.cases.values())
        s = lambda attr: sum(getattr(x, attr) for x in c)  # noqa: E731
        return {
            "precision": _ratio(s("tp"), s("n_pred")), "recall": _ratio(s("tp"), s("n_gold")),
            "critical_precision": _ratio(s("crit_tp"), s("crit_pred")),
            "critical_recall": _ratio(s("crit_tp"), s("crit_gold")),
            "silent_wrong_critical": s("silent_wrong_critical"), "span_rejections": s("span_rejections"),
            "missing_provenance": s("missing_provenance"),
            "contradiction_recall": _ratio(s("contra_found"), s("contra_gold")),
            "bounce_recall": _ratio(s("bounce_hit"), s("bounce_expected")),
            "bounce_false_fires": sum(len(x.bounce_false_fires) for x in c),
            "privacy_leaks": s("privacy_leaks"),
            "false_warnings": s("false_warnings"),
            "supersession_recall": _ratio(s("sup_found"), s("sup_gold")),
        }

    def markdown(self) -> str:
        used = ", ".join(f"{k} {v}" for k, v in self.versions.items())
        lines = [f"# Scorecard: pipeline `{self.pipeline}`, {len(self.cases)} case(s)", "", f"Versions: {used}", "",
                 "| Metric | Value |", "|---|---|"]
        lines += [f"| {k} | {_fmt(v)} |" for k, v in self.totals.items()]
        lines += ["", "| Case | P | R | crit R | silent wrong | span rej | contra R | bounce R | missed | false fires | privacy leaks | false warn |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for cid, x in sorted(self.cases.items()):
            lines.append(f"| {cid} | {_fmt(x.precision)} | {_fmt(x.recall)} | {_fmt(x.critical_recall)} | "
                         f"{x.silent_wrong_critical} | {x.span_rejections} | {_fmt(x.contradiction_recall)} | "
                         f"{_fmt(x.bounce_recall)} | {', '.join(x.bounce_missed) or '-'} | "
                         f"{', '.join(x.bounce_false_fires) or '-'} | {x.privacy_leaks} | {x.false_warnings} |")
        silent = [(cid, w) for cid, x in sorted(self.cases.items()) for w in x.silent_wrong]
        if silent:
            lines += ["", "## Silent wrong values (check each: a real error, or wording the grader is strict about)",
                      "", "| Case | Field | Subject | Extracted | Expected |", "|---|---|---|---|---|"]
            lines += [f"| {cid} | {f} | {sub} | {got} | {exp} |" for cid, (f, sub, got, exp) in silent]
        if self.problems:
            lines += ["", "## Case problems (fix before trusting the scores)"]
            for cid, ps in sorted(self.problems.items()):
                lines += [f"- **{cid}:** {p}" for p in ps]
        return "\n".join(lines) + "\n"


def run_cases(folder: Path, pipeline: Pipeline, taxonomy: Taxonomy, reasons: BounceReasons,
              only: Sequence[str] = (), noisy: bool = False) -> Scorecard:
    card = Scorecard(pipeline=pipeline.name,
                     versions={"taxonomy": taxonomy.version, "bounce_reasons": reasons.version})
    if getattr(pipeline, "version", None):
        card.versions["extractor"] = pipeline.version
    if noisy:
        card.versions["transcript"] = "noisy"
    for path in sorted(folder.glob("*.yaml")):
        if only and path.stem not in only:
            continue
        try:
            case = load_case(path, taxonomy, reasons)
        except (CaseFormatError, ValidationError) as e:
            card.problems[path.stem] = [f"does not load: {e}"]
            continue
        problems = consistency_problems(case, reasons, taxonomy)
        if case.case_id != path.stem:
            problems.append(f"file name {path.name} does not match case_id {case.case_id}")
        if problems:
            card.problems[case.case_id] = problems
        if noisy:  # read the noisy transcript, score against the clean gold; quotes are checked against what was read
            if case.noisy_transcript is None:
                continue
            case = case.model_copy(update={"transcript": case.noisy_transcript})
        card.cases[case.case_id] = score_case(case, pipeline.run(case), reasons, taxonomy)
    return card



def run_capture(case: CaseFile, audios: Sequence[Path], pipeline: Pipeline, taxonomy: Taxonomy,
                reasons: BounceReasons, transcribe=None, transcripts: Sequence[Path] = ()) -> Scorecard:
    """Capture spike: score extraction against the case's gold on each recording of its script. Audio is
    transcribed with Whisper on this machine ("(whisper)" rows); a transcript copied from the device, such as Voice
    Memos, is scored as it is ("(device)" rows), so the two transcribers are compared on the same recording."""
    from kyc_copilot.capture import read_device_transcript
    if transcribe is None:
        from kyc_copilot.capture import transcribe
    card = Scorecard(pipeline=pipeline.name, versions={"taxonomy": taxonomy.version, "bounce_reasons": reasons.version,
                                                       "transcript": "audio"})
    if getattr(pipeline, "version", None):
        card.versions["extractor"] = pipeline.version
    runs = [(f"{a.stem} (whisper)", lambda a=a: transcribe(a, case.transcript.meeting_date)) for a in audios]
    runs += [(f"{t.stem} (device)", lambda t=t: read_device_transcript(t, case.transcript.meeting_date))
             for t in transcripts]
    for label, read in runs:
        heard = case.model_copy(update={"transcript": read()})
        card.cases[label] = score_case(heard, pipeline.run(heard), reasons, taxonomy)
    return card


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kyc-eval", description="Score a pipeline against the synthetic cases.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    run.add_argument("--pipeline", choices=sorted([*PIPELINES, "model"]), default="gold")
    run.add_argument("--only", default="", help="comma-separated case ids, e.g. a pilot: C01,D02,D04")
    run.add_argument("--model", default=None, help="model id for --pipeline model")
    run.add_argument("--cap", type=float, default=5.0, help="spend cap in USD for --pipeline model")
    run.add_argument("--no-cache", action="store_true", help="ignore cached model replies")
    run.add_argument("--noisy", action="store_true", help="run on the noisy transcripts (cases that have one)")
    cap = sub.add_parser("capture", help="score recordings of a case's script (capture spike)")
    cap.add_argument("--case", required=True, help="case id whose script was recorded, e.g. C01")
    cap.add_argument("--audio", type=Path, nargs="*", default=[], help="recordings, transcribed with Whisper")
    cap.add_argument("--transcript", type=Path, nargs="*", default=[],
                     help="device transcripts of the same recordings (e.g. Voice Memos), scored as they are")
    cap.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    cap.add_argument("--cap", type=float, default=2.0)
    cap.add_argument("--no-audio-doubts", action="store_true", help="switch off unclear-audio flags (before/after)")
    args = ap.parse_args(argv)
    taxonomy = load_taxonomy()
    if args.cmd == "capture":
        from kyc_copilot.extract import ModelExtractor
        reasons = load_bounce_reasons(taxonomy)
        case = load_case(args.cases / f"{args.case}.yaml", taxonomy, reasons)
        pipeline = ModelExtractor(taxonomy, cap_usd=args.cap, audio_doubts=not args.no_audio_doubts)
        if not args.audio and not args.transcript:
            ap.error("capture needs --audio and/or --transcript")
        print(run_capture(case, args.audio, pipeline, taxonomy, reasons, transcripts=args.transcript).markdown(),
              end="")
        print(pipeline.cost_markdown())
        return 0
    if args.pipeline == "model":
        from kyc_copilot.extract import DEFAULT_MODEL, ModelExtractor, SpendCapReached
        pipeline = ModelExtractor(taxonomy, model=args.model or DEFAULT_MODEL, cap_usd=args.cap,
                                  use_cache=not args.no_cache)
    else:
        pipeline, SpendCapReached = PIPELINES[args.pipeline](), None
    only = tuple(c.strip() for c in args.only.split(",") if c.strip())
    stopped = None
    try:
        card = run_cases(args.cases, pipeline, taxonomy, load_bounce_reasons(taxonomy), only, args.noisy)
    except Exception as e:  # a spend cap ends the run; anything else is a real error
        if SpendCapReached is None or not isinstance(e, SpendCapReached):
            raise
        stopped, card = str(e), None
    if card is not None:
        print(card.markdown(), end="")
    if hasattr(pipeline, "cost_markdown"):
        print(pipeline.cost_markdown())
    if stopped:
        print(f"\n**Stopped: spend cap.** {stopped}")
        return 2
    return 1 if card.problems else 0


def cli() -> None:
    sys.exit(main())
