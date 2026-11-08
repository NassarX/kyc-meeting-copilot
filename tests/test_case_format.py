"""Case format: one YAML file per synthetic case."""
from datetime import date
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from kyc_copilot.domain.models import ChecklistItem, SpanOffset
from kyc_copilot.eval.case_format import CaseFile, CaseFormatError, load_case, validate_case
from kyc_copilot.rules import load_bounce_reasons

TOY = Path(__file__).parent / "fixtures" / "toy_case.yaml"


@pytest.fixture
def reasons(taxonomy):
    return load_bounce_reasons(taxonomy)


def raw() -> dict:
    return yaml.safe_load(TOY.read_text(encoding="utf-8"))


def check(data: dict, taxonomy, reasons) -> CaseFile:
    case = CaseFile.model_validate(data)
    validate_case(case, taxonomy, reasons)
    return case


# ---------- the toy case ----------

def test_toy_case_loads_and_validates(taxonomy, reasons):
    case = load_case(TOY, taxonomy, reasons)
    assert case.case_id == "T00" and case.as_of_date == date(2026, 11, 1)
    assert isinstance(case.checklist[0], ChecklistItem)
    assert case.gold.facts[0].spans[0] == SpanOffset(utt_id="u-02", start=32, end=69,
                                                      quote="3.4 million, sorry, 2.4 million euros")


def test_seeded_draft_is_labelled(taxonomy, reasons):
    case = load_case(TOY, taxonomy, reasons)
    assert case.seeded_drafts[0].label == "seeded draft"


# ---------- schema failures ----------

def test_unknown_gold_field_fails(taxonomy, reasons):
    d = raw()
    d["gold"]["facts"][1]["field"] = "client.favourite_colour"
    with pytest.raises(CaseFormatError, match="unknown field"):
        check(d, taxonomy, reasons)


def test_wrong_value_kind_for_field_fails(taxonomy, reasons):
    d = raw()
    d["gold"]["facts"][1]["value"] = {"kind": "text", "value": "France"}
    with pytest.raises(CaseFormatError, match="expects country"):
        check(d, taxonomy, reasons)


def test_extra_keys_are_rejected():
    d = raw()
    d["surprise"] = 1
    with pytest.raises(ValidationError):
        CaseFile.model_validate(d)


def test_unknown_gap_field_fails(taxonomy, reasons):
    d = raw()
    d["gold"]["gaps"] = ["identity.shoe_size"]
    with pytest.raises(CaseFormatError, match="unknown field"):
        check(d, taxonomy, reasons)


def test_unknown_bounce_reason_fails(taxonomy, reasons):
    d = raw()
    d["gold"]["bounce_reasons"].append("BR-NOPE")
    with pytest.raises(CaseFormatError, match="bounce reason"):
        check(d, taxonomy, reasons)


# ---------- spans quote the raw transcript ----------

def test_span_quote_must_match_raw_slice(taxonomy, reasons):
    d = raw()
    d["gold"]["facts"][0]["spans"][0]["quote"] = "2.4 million euros"
    with pytest.raises(CaseFormatError, match="does not match"):
        check(d, taxonomy, reasons)


def test_span_match_ignores_case_and_whitespace(taxonomy, reasons):
    d = raw()
    d["gold"]["facts"][1]["spans"][0]["quote"] = "Tax  resident in FRANCE"
    check(d, taxonomy, reasons)


def test_span_on_unknown_utterance_fails(taxonomy, reasons):
    d = raw()
    d["gold"]["facts"][1]["spans"][0]["utt_id"] = "u-99"
    with pytest.raises(CaseFormatError, match="u-99"):
        check(d, taxonomy, reasons)


def test_span_past_end_of_utterance_fails(taxonomy, reasons):
    d = raw()
    d["gold"]["facts"][1]["spans"][0]["end"] = 500
    with pytest.raises(CaseFormatError, match="out of range"):
        check(d, taxonomy, reasons)


def test_span_end_before_start_fails():
    with pytest.raises(ValidationError):
        SpanOffset(utt_id="u-01", start=10, end=5)


def test_gold_fact_needs_a_span():
    d = raw()
    d["gold"]["facts"][0]["spans"] = []
    with pytest.raises(ValidationError):
        CaseFile.model_validate(d)


def test_duplicate_utterance_ids_fail(taxonomy, reasons):
    d = raw()
    d["transcript"]["utterances"][1]["utt_id"] = "u-01"
    with pytest.raises(CaseFormatError, match="duplicate utterance"):
        check(d, taxonomy, reasons)


# ---------- checklist ----------

def test_unknown_document_type_fails(taxonomy, reasons):
    d = raw()
    d["checklist"][0]["document_type"] = "selfie"
    with pytest.raises(CaseFormatError, match="document type"):
        check(d, taxonomy, reasons)


def test_duplicate_checklist_item_ids_fail(taxonomy, reasons):
    d = raw()
    d["checklist"][1]["item_id"] = "chk-01"
    with pytest.raises(CaseFormatError, match="duplicate checklist item"):
        check(d, taxonomy, reasons)


def test_checklist_expiry_before_issue_fails():
    with pytest.raises(ValidationError):
        ChecklistItem(item_id="x", document_type="passport", present=True,
                      issue_date=date(2026, 1, 1), expiry_date=date(2025, 1, 1))


# ---------- dossier, traps, seeded drafts ----------

def test_dossier_entry_with_unknown_field_fails(taxonomy, reasons):
    d = raw()
    d["dossier"][0]["field"] = "identity.nickname"
    with pytest.raises(CaseFormatError, match="unknown field"):
        check(d, taxonomy, reasons)


def test_unknown_trap_kind_fails():
    d = raw()
    d["traps"][0]["kind"] = "vibes"
    with pytest.raises(ValidationError):
        CaseFile.model_validate(d)


def test_seeded_draft_must_target_a_gold_fact(taxonomy, reasons):
    d = raw()
    d["seeded_drafts"][0]["field"] = "identity.tax_residence"
    d["seeded_drafts"][0]["subject_ref"] = "wealth_event/1"
    with pytest.raises(CaseFormatError, match="no gold fact"):
        check(d, taxonomy, reasons)


def test_seeded_draft_must_change_the_value(taxonomy, reasons):
    d = raw()
    d["seeded_drafts"][0]["wrong_value"] = {"kind": "money", "amount": "2400000", "currency": "EUR"}
    with pytest.raises(CaseFormatError, match="same as gold"):
        check(d, taxonomy, reasons)


def test_case_id_shape_enforced():
    d = raw()
    d["case_id"] = "case one"
    with pytest.raises(ValidationError):
        CaseFile.model_validate(d)


def test_grouped_gap_names_its_subject(taxonomy, reasons):
    d = raw()
    d["gold"]["gaps"] = ["wealth_event.date@wealth_event/1"]
    check(d, taxonomy, reasons)
    d["gold"]["gaps"] = ["wealth_event.shoe_size@wealth_event/1"]
    with pytest.raises(CaseFormatError, match="unknown field"):
        check(d, taxonomy, reasons)
