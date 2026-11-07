"""Beta 0 records: span offsets, run id, as_of_date, StepRun, Contradiction, Resolution, Finding."""
from datetime import date

import pytest
from pydantic import ValidationError

from kyc_copilot.domain.enums import SourceType
from kyc_copilot.domain.models import (Case, Contradiction, Finding, Provenance, Resolution, SpanOffset, StepRun)


def off(utt="u-01", start=0, end=5):
    return SpanOffset(utt_id=utt, start=start, end=end)


# ---------- Provenance (D6) ----------

def test_transcript_provenance_needs_offsets():
    with pytest.raises(ValidationError, match="span"):
        Provenance(source_type=SourceType.TRANSCRIPT, source_ref="transcript/v1", extractor_version="x")


def test_utterance_ids_are_derived_from_offsets():
    p = Provenance(source_type=SourceType.TRANSCRIPT, source_ref="transcript/v1", extractor_version="x",
                   span_offsets=(off("u-02"), off("u-07"), off("u-02", 10, 20)))
    assert p.utt_ids == ("u-02", "u-07")


def test_run_id_is_optional_and_kept_when_given():
    doc = Provenance(source_type=SourceType.DOCUMENT, source_ref="chk-01", extractor_version="checklist-loader-v1")
    assert doc.run_id is None
    t = Provenance(source_type=SourceType.TRANSCRIPT, source_ref="t", extractor_version="x",
                   span_offsets=(off(),), run_id="run-1")
    assert t.run_id == "run-1"


def test_old_span_utt_ids_field_is_gone():
    with pytest.raises(ValidationError):
        Provenance(source_type=SourceType.TRANSCRIPT, source_ref="t", extractor_version="x", span_utt_ids=("u-01",))


def test_document_provenance_must_not_carry_spans():
    with pytest.raises(ValidationError, match="span"):
        Provenance(source_type=SourceType.DOCUMENT, source_ref="chk-01", extractor_version="checklist-loader-v1",
                   span_offsets=(off(),))


# ---------- Case.as_of_date (D8) ----------

def test_case_requires_as_of_date():
    with pytest.raises(ValidationError, match="as_of_date"):
        Case(lead_ref="lead-1", rm_id="rm.alice")
    assert Case(lead_ref="lead-1", rm_id="rm.alice", as_of_date=date(2026, 11, 1)).as_of_date == date(2026, 11, 1)


# ---------- StepRun (D14) ----------

def test_step_run_completed_needs_output_ref():
    with pytest.raises(ValidationError, match="output"):
        StepRun(case_id="c", step="S3_extract", attempt=0, input_hash="a" * 64, model_id="m",
                prompt_version="p", status="completed")


def test_step_run_input_hash_is_sha256_hex():
    with pytest.raises(ValidationError):
        StepRun(case_id="c", step="S3_extract", attempt=0, input_hash="nothex", model_id="m",
                prompt_version="p", status="started")


def test_step_run_attempt_not_negative():
    with pytest.raises(ValidationError):
        StepRun(case_id="c", step="S3_extract", attempt=-1, input_hash="a" * 64, model_id="m",
                prompt_version="p", status="started")


# ---------- Contradiction (D4, D19) ----------

def test_contradiction_needs_two_distinct_facts():
    with pytest.raises(ValidationError):
        Contradiction(case_id="c", field="wealth_event.amount", fact_ids=("f-1",), rule_version="r")
    with pytest.raises(ValidationError, match="distinct"):
        Contradiction(case_id="c", field="wealth_event.amount", fact_ids=("f-1", "f-1"), rule_version="r")
    c = Contradiction(case_id="c", field="wealth_event.amount", fact_ids=("f-1", "f-2", "f-3"), rule_version="r")
    assert len(c.fact_ids) == 3


# ---------- Resolution (design: "open for compliance" is a resolution) ----------

def test_resolution_standing_fact_or_open_or_unknown():
    Resolution(case_id="c", contradiction_id="k", outcome="stands", standing_fact_id="f-2",
               reason="passport shows it", actor_id="rm.alice")
    Resolution(case_id="c", contradiction_id="k", outcome="open", reason="ask compliance", actor_id="rm.alice")
    with pytest.raises(ValidationError, match="standing_fact_id"):
        Resolution(case_id="c", contradiction_id="k", outcome="stands", reason="x", actor_id="rm.alice")
    with pytest.raises(ValidationError, match="standing_fact_id"):
        Resolution(case_id="c", contradiction_id="k", outcome="unknown", standing_fact_id="f-2",
                   reason="x", actor_id="rm.alice")


def test_resolution_needs_a_reason():
    with pytest.raises(ValidationError):
        Resolution(case_id="c", contradiction_id="k", outcome="open", reason="", actor_id="rm.alice")


# ---------- Finding (D17) ----------

def test_finding_from_rule_and_from_checker():
    f = Finding(case_id="c", attempt=0, source="rule", source_id="BR-ID-DOB", source_version="br-v0.1",
                outcome="fire", effect="bounce")
    assert f.fact_refs == ()
    Finding(case_id="c", attempt=1, source="checker", source_id="claude-x", source_version="checker-v0",
            outcome="fire", effect="flag", fact_refs=("f-1",), detail="span does not support value")


def test_finding_rejects_unknown_source():
    with pytest.raises(ValidationError):
        Finding(case_id="c", attempt=0, source="vibes", source_id="x", source_version="v", outcome="fire",
                effect="flag")
