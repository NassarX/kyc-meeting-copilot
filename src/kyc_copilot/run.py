"""One entry point for a meeting: a transcript or an audio file in, the pre-submission check out.

    kyc-check --transcript meeting.txt [--meeting-date 2026-11-07] [--case C01] [--json out.json]
    kyc-check --audio meeting.m4a      [--meeting-date 2026-11-07] [--case C01] [--json out.json]

A transcript file is plain text, one turn per line as `speaker: text` (a line without a colon is speaker
`unknown`), or a case-style YAML/JSON list of utterances. `--case` borrows that case's dossier stub and document
checklist, so the bounce rules have the bank's side too. The demo viewer calls `process()`; the CLI prints the same
result as markdown or JSON.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from kyc_copilot.eval.case_format import CaseFile, Gold, Lead, Transcript, Utterance, load_case
from kyc_copilot.eval.harness import DEFAULT_CASES, current, derived_gaps, input_facts
from kyc_copilot.names import explain_conflict
from kyc_copilot.rules import Outcome, evaluate, load_bounce_reasons
from kyc_copilot.taxonomy import load_taxonomy


def read_transcript(path: Path, meeting_date: date) -> Transcript:
    if path.suffix.lower() in (".yaml", ".yml", ".json"):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        utts = data.get("utterances", data) if isinstance(data, dict) else data
        return Transcript(meeting_date=meeting_date, utterances=tuple(
            Utterance(utt_id=u.get("utt_id", f"u-{i:02d}"), speaker=u.get("speaker", "unknown"), text=u["text"])
            for i, u in enumerate(utts, 1)))
    return parse_transcript(path.read_text(encoding="utf-8"), meeting_date, str(path))


def parse_transcript(text: str, meeting_date: date, where: str = "transcript") -> Transcript:
    """Plain text, one turn per line as `speaker: text`; a line without a short label is speaker `unknown`."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        speaker, sep, text = line.partition(":")
        if not sep or not text.strip() or len(speaker.split()) > 3:  # a colon inside a sentence, not a label
            speaker, text = "unknown", line
        out.append(Utterance(utt_id=f"u-{len(out) + 1:02d}", speaker=speaker.strip().lower(), text=text.strip()))
    if not out:
        raise ValueError(f"{where}: no utterances")
    return Transcript(meeting_date=meeting_date, utterances=tuple(out))


@dataclass
class RunResult:
    transcript: Transcript
    facts: tuple
    doubts: tuple
    contradictions: tuple
    notes: dict
    gaps: list[str]
    flags: list[dict]
    rejected: list[str]
    cost_usd: float
    extractor: str

    def _clip(self, f) -> list[float] | None:
        """Seconds of audio behind a fact's quote, from the transcriber's word timings (confirm-by-ear). A fact
        quoted in several places plays one quote, not the stretch between them: the one sharing most words with the
        value ("Ms. Marchetti Okonkwo" over "Isabel" for a full name), then the shortest."""
        utts = {u.utt_id: u for u in self.transcript.utterances}
        value_words = set(re.findall(r"[a-z0-9]+", json.dumps(f.value.model_dump(mode="json")).lower())) \
            if hasattr(f, "value") else set()
        clips = []
        for o in (o for p in f.provenance for o in p.span_offsets if o.utt_id in utts):
            ws = [w for w in utts[o.utt_id].words if w.start < o.end and w.end > o.start]
            if ws:
                shared = len(value_words & set(re.findall(r"[a-z0-9]+", utts[o.utt_id].text[o.start:o.end].lower())))
                start, end = round(min(w.t_start for w in ws), 2), round(max(w.t_end for w in ws), 2)
                clips.append((-shared, end - start, [start, end]))
        return min(clips)[2] if clips else None

    def to_dict(self) -> dict[str, Any]:
        critical = load_taxonomy().critical_fields
        return {
            "extractor": self.extractor, "cost_usd": round(self.cost_usd, 4),
            "transcript": [u.model_dump(exclude={"words"}) for u in self.transcript.utterances],
            "facts": [{"fact_id": f.fact_id, "field": f.field, "subject_ref": f.subject_ref, "status": str(f.status),
                       "value": f.value.model_dump(mode="json"), "confidence": f.confidence,
                       "critical": f.field in critical, "clip": self._clip(f),
                       "spans": [s.model_dump() for p in f.provenance for s in p.span_offsets]} for f in self.facts],
            "doubts": [{"rule": d.rule, "message": d.message, "fact_ids": list(d.fact_ids)} for d in self.doubts],
            "contradictions": [{"field": f, "subject_ref": s, "note": self.notes.get((f, s))}
                               for f, s in self.contradictions],
            "gaps": self.gaps, "flags": self.flags, "rejected": self.rejected,
        }

    def markdown(self) -> str:
        lines = [f"# Pre-submission check ({self.extractor}, ${self.cost_usd:.4f})", "",
                 f"{len(self.transcript.utterances)} utterances, {len(self.facts)} facts.", "", "## Flags"]
        lines += [f"- **{f['reason_id']}** {f['title']}" for f in self.flags] or ["- none"]
        lines += ["", "## Needs confirmation"]
        lines += [f"- {d.message} ({d.rule})" for d in self.doubts] or ["- nothing doubted"]
        lines += [f"- contradiction: {f}{'@' + s if s else ''}" + (f" ({self.notes[(f, s)]})" if (f, s) in self.notes else "")
                  for f, s in self.contradictions]
        lines += ["", "## Gaps"] + ([f"- {g}" for g in self.gaps] or ["- none"])
        lines += ["", "## Facts", "", "| Field | Group | Value | Quote |", "|---|---|---|---|"]
        for f in self.facts:
            v = {k: str(x) for k, x in f.value.model_dump().items() if k != "kind"}
            q = " / ".join(s.quote or "" for p in f.provenance for s in p.span_offsets)
            lines.append(f"| {f.field} | {f.subject_ref or '-'} | {', '.join(v.values())} | {q} |")
        if self.rejected:
            lines += ["", "## Rejected after retry"] + [f"- {r}" for r in self.rejected]
        return "\n".join(lines) + "\n"


def process(transcript: Transcript, *, borrow: CaseFile | None = None, extractor=None) -> RunResult:
    """Extract, reconcile, doubt, and run the bounce rules on one meeting."""
    from kyc_copilot.extract import ModelExtractor
    taxonomy = load_taxonomy()
    reasons = load_bounce_reasons(taxonomy)
    case = CaseFile(case_id="R01", title="ad hoc run", origin="author", as_of_date=transcript.meeting_date,
                    lead=Lead(lead_ref="adhoc", rm_id="rm.demo"), transcript=transcript,
                    dossier=borrow.dossier if borrow else (), checklist=borrow.checklist if borrow else (),
                    gold=Gold())
    extractor = extractor or ModelExtractor(taxonomy)
    out = extractor.run(case)
    facts = input_facts(case) + current(out.facts)
    notes = {}
    for field_, subject in out.contradictions:  # explain name conflicts: likely the same name, or two people?
        values = [str(f.value.model_dump().get("value", "")) for f in facts
                  if (f.field, f.subject_ref) == (field_, subject) and f.value.kind == "text"]
        note = explain_conflict(field_, values)
        if note:
            notes[(field_, subject)] = note
    fired = [r for r in evaluate(reasons, facts, case.as_of_date) if r.outcome is Outcome.FIRE]
    titles = {r.id: r.title for r in reasons.reasons}
    return RunResult(transcript=transcript, facts=out.facts, doubts=out.doubts, contradictions=out.contradictions,
                     notes=notes,
                     gaps=derived_gaps(facts, taxonomy),
                     flags=[{"reason_id": r.reason_id, "title": titles.get(r.reason_id, "")} for r in fired],
                     rejected=extractor.rejected.get(case.case_id, []) if hasattr(extractor, "rejected") else [],
                     cost_usd=getattr(extractor, "spent", 0.0), extractor=getattr(extractor, "version", "?"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kyc-check", description="Run the pre-submission check on one meeting.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--transcript", type=Path)
    src.add_argument("--audio", type=Path)
    ap.add_argument("--meeting-date", type=date.fromisoformat, default=date.today())
    ap.add_argument("--case", help="borrow this case's dossier and checklist, e.g. C01")
    ap.add_argument("--json", type=Path, help="also write the result as JSON")
    ap.add_argument("--cap", type=float, default=1.0, help="spend cap in USD")
    args = ap.parse_args(argv)
    from kyc_copilot.extract import ModelExtractor
    taxonomy = load_taxonomy()
    if args.audio:
        from kyc_copilot.capture import transcribe
        transcript = transcribe(args.audio, args.meeting_date)
    else:
        transcript = read_transcript(args.transcript, args.meeting_date)
    borrow = load_case(DEFAULT_CASES / f"{args.case}.yaml", taxonomy, load_bounce_reasons(taxonomy)) \
        if args.case else None
    result = process(transcript, borrow=borrow, extractor=ModelExtractor(taxonomy, cap_usd=args.cap))
    print(result.markdown(), end="")
    if args.json:
        args.json.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


def cli() -> None:
    sys.exit(main())
