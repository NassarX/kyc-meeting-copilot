"""Synthetic case file format.

One YAML file per case: transcript, dossier stub, document checklist, gold facts with exact spans, gold gaps,
contradictions and bounce reasons, the input traps, and seeded drafts. Two layers of checking:
- `CaseFile` (Pydantic) checks shape: types, required keys, no extra keys.
- `validate_case` checks references: fields and document types against the taxonomy, bounce reasons against
  the rules file, and every gold span against the raw transcript text.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from kyc_copilot.domain.enums import Purpose, SourceType
from kyc_copilot.domain.models import ChecklistItem, Fact, FactValue, Provenance, Record, SpanOffset
from kyc_copilot.domain.values import normalize
from kyc_copilot.rules import BounceReasons
from kyc_copilot.taxonomy import Taxonomy, TaxonomyError


class CaseFormatError(ValueError):
    pass


class WordScore(Record):
    """One transcribed word: where it sits in the utterance text, how sure the transcriber was, and when it was said
    (audio transcripts only)."""
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    probability: float = Field(ge=0.0, le=1.0)
    t_start: float = Field(ge=0.0)
    t_end: float = Field(ge=0.0)


class Utterance(Record):
    utt_id: str = Field(min_length=1)
    speaker: str = Field(min_length=1)
    text: str = Field(min_length=1)
    words: tuple[WordScore, ...] = ()  # empty for typed transcripts


class Transcript(Record):
    meeting_date: date
    utterances: tuple[Utterance, ...] = Field(min_length=1)


class Lead(Record):
    lead_ref: str = Field(min_length=1)
    rm_id: str = Field(min_length=1)


class DossierEntry(Record):
    """A value the bank already holds before the meeting (the dossier stub)."""
    field: str
    subject_ref: str | None = None
    value: FactValue


class GoldFact(Record):
    field: str
    subject_ref: str | None = None
    value: FactValue
    spans: tuple[SpanOffset, ...] = Field(min_length=1)
    derivation: str | None = None  # e.g. "self-correction", "relative date resolved against meeting date"


class GoldContradiction(Record):
    field: str
    subject_ref: str | None = None
    values: tuple[FactValue, ...] = Field(min_length=2)
    sources: tuple[Literal["transcript", "dossier", "checklist"], ...] = Field(min_length=2)


class Gold(Record):
    facts: tuple[GoldFact, ...] = ()
    gaps: tuple[str, ...] = ()
    contradictions: tuple[GoldContradiction, ...] = ()
    bounce_reasons: tuple[str, ...] = ()
    triggers: tuple[str, ...] = ()
    band: str | None = None
    forbidden_utterances: tuple[str, ...] = ()  # I10: special-category disclosures no fact may quote (D05)
    superseded: tuple[GoldFact, ...] = ()  # answers the client changed later in the meeting (D02)


class Trap(Record):
    kind: Literal["transcript_conflict", "missing_required", "extraction_trap"]
    note: str = Field(min_length=1)
    refs: tuple[str, ...] = ()


class SeededDraft(Record):
    """The gold fact set with one wrong value injected. Always labelled as seeded wherever shown."""
    draft_id: str = Field(min_length=1)
    label: Literal["seeded draft"] = "seeded draft"
    field: str
    subject_ref: str | None = None
    wrong_value: FactValue


class CaseFile(Record):
    case_id: str = Field(pattern=r"^[A-Z]\d{2}$")  # C01, D01..D05; B.. for blind cases; T00 for tests
    title: str = Field(min_length=1)
    origin: Literal["author", "blind"]
    as_of_date: date
    lead: Lead
    transcript: Transcript
    noisy_transcript: Transcript | None = None
    dossier: tuple[DossierEntry, ...] = ()
    checklist: tuple[ChecklistItem, ...] = ()
    gold: Gold
    traps: tuple[Trap, ...] = ()
    seeded_drafts: tuple[SeededDraft, ...] = ()


# ---------- reference checks ----------

def _check_value(case_id: str, taxonomy: Taxonomy, field: str, subject_ref: str | None, value, where: str) -> None:
    # Reuse the taxonomy's own fact check, so a case can never hold a value the store would refuse.
    prov = Provenance(source_type=SourceType.RM_ENTRY, source_ref="case-file", extractor_version="case-format")
    try:
        taxonomy.validate_fact(Fact(case_id=case_id, field=field, subject_ref=subject_ref, value=value,
                                    confidence=1.0, purpose=(Purpose.AML,), provenance=(prov,),
                                    created_by="case-format"))
    except TaxonomyError as e:
        raise CaseFormatError(f"{case_id} {where}: {e}") from None


def _check_field(case_id: str, taxonomy: Taxonomy, field: str, where: str) -> None:
    if field not in taxonomy.fields:
        raise CaseFormatError(f"{case_id} {where}: unknown field {field!r} in taxonomy {taxonomy.version}")


def check_span(case_id: str, utts: dict[str, Utterance], span: SpanOffset, where: str) -> None:
    utt = utts.get(span.utt_id)
    if utt is None:
        raise CaseFormatError(f"{case_id} {where}: span cites unknown utterance {span.utt_id}")
    if span.end > len(utt.text):
        raise CaseFormatError(f"{case_id} {where}: span {span.start}-{span.end} out of range for {span.utt_id}")
    if span.quote is not None and normalize(span.quote) != normalize(utt.text[span.start:span.end]):
        raise CaseFormatError(f"{case_id} {where}: quote {span.quote!r} does not match "
                              f"{utt.text[span.start:span.end]!r} in {span.utt_id}")


def utterance_index(case_id: str, t: Transcript) -> dict[str, Utterance]:
    utts: dict[str, Utterance] = {}
    for u in t.utterances:
        if u.utt_id in utts:
            raise CaseFormatError(f"{case_id}: duplicate utterance id {u.utt_id}")
        utts[u.utt_id] = u
    return utts


def validate_case(case: CaseFile, taxonomy: Taxonomy, reasons: BounceReasons) -> None:
    cid = case.case_id
    utts = utterance_index(cid, case.transcript)
    if case.noisy_transcript is not None:
        utterance_index(cid, case.noisy_transcript)

    for i, d in enumerate(case.dossier):
        _check_field(cid, taxonomy, d.field, f"dossier[{i}]")
        _check_value(cid, taxonomy, d.field, d.subject_ref, d.value, f"dossier[{i}]")

    seen_items: set[str] = set()
    for item in case.checklist:
        if item.item_id in seen_items:
            raise CaseFormatError(f"{cid}: duplicate checklist item {item.item_id}")
        seen_items.add(item.item_id)
        if item.document_type not in taxonomy.document_types:
            raise CaseFormatError(f"{cid} checklist {item.item_id}: unknown document type {item.document_type!r}")

    gold_keys = {}
    for i, g in enumerate(case.gold.facts):
        where = f"gold.facts[{i}] {g.field}"
        _check_field(cid, taxonomy, g.field, where)
        _check_value(cid, taxonomy, g.field, g.subject_ref, g.value, where)
        for s in g.spans:  # gold spans always point into the clean transcript
            check_span(cid, utts, s, where)
        gold_keys[(g.field, g.subject_ref)] = g.value

    for i, g in enumerate(case.gold.superseded):
        where = f"gold.superseded[{i}] {g.field}"
        _check_field(cid, taxonomy, g.field, where)
        _check_value(cid, taxonomy, g.field, g.subject_ref, g.value, where)
        for sp in g.spans:
            check_span(cid, utts, sp, where)
        if (g.field, g.subject_ref) not in gold_keys:
            raise CaseFormatError(f"{cid} {where}: no current gold fact for this field replaces it")

    for u in case.gold.forbidden_utterances:
        if u not in utts:
            raise CaseFormatError(f"{cid} gold.forbidden_utterances: {u} is not in the transcript")
    for i, g in enumerate(case.gold.facts):
        if any(s.utt_id in case.gold.forbidden_utterances for s in g.spans):
            raise CaseFormatError(f"{cid} gold.facts[{i}] {g.field}: quotes a forbidden utterance")
    for f in case.gold.gaps:  # "field", or "field@subject_ref" for a grouped field missing from one subject
        _check_field(cid, taxonomy, f.split("@", 1)[0], "gold.gaps")
    for i, c in enumerate(case.gold.contradictions):
        _check_field(cid, taxonomy, c.field, f"gold.contradictions[{i}]")
        for v in c.values:
            _check_value(cid, taxonomy, c.field, c.subject_ref, v, f"gold.contradictions[{i}]")

    known = {r.id for r in reasons.reasons}
    for rid in case.gold.bounce_reasons:
        if rid not in known:
            raise CaseFormatError(f"{cid}: unknown bounce reason {rid!r} (rules {reasons.version})")

    for s in case.seeded_drafts:
        key = (s.field, s.subject_ref)
        if key not in gold_keys:
            raise CaseFormatError(f"{cid} seeded draft {s.draft_id}: no gold fact for {s.field} {s.subject_ref}")
        if s.wrong_value == gold_keys[key]:
            raise CaseFormatError(f"{cid} seeded draft {s.draft_id}: wrong_value is the same as gold")
        _check_value(cid, taxonomy, s.field, s.subject_ref, s.wrong_value, f"seeded draft {s.draft_id}")


def load_case(path: Path, taxonomy: Taxonomy, reasons: BounceReasons) -> CaseFile:
    case = CaseFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    validate_case(case, taxonomy, reasons)
    return case
