"""Taxonomy v0.2: document fields and the document-type list."""
from datetime import date
from pathlib import Path

import pytest

from kyc_copilot.domain.models import ExactDate, Flag, Provenance, Text
from kyc_copilot.domain.enums import SourceType
from kyc_copilot.taxonomy import DEFAULT_PATH, TaxonomyError, load_taxonomy
from conftest import make_fact

V01 = DEFAULT_PATH.with_name("tax-v0.1.yaml")


def doc_prov(item_id: str = "chk-01") -> Provenance:
    return Provenance(source_type=SourceType.DOCUMENT, source_ref=item_id, extractor_version="checklist-loader-v1")


def test_default_taxonomy_is_v02(taxonomy):
    assert taxonomy.version == "tax-v0.2"


def test_document_types_listed(taxonomy):
    for t in ("passport", "national_id", "proof_of_address", "bank_statement", "sale_agreement"):
        assert t in taxonomy.document_types


def test_document_type_enum_is_derived_from_the_list(taxonomy):
    """One list, not two: document.type takes its values from document_types."""
    assert taxonomy.fields["document.type"].values == taxonomy.document_types


@pytest.mark.parametrize("field,value", [
    ("document.type", Text(value="passport")),
    ("document.present", Flag(value=True)),
    ("document.issue_date", ExactDate(value=date(2020, 3, 1))),
    ("document.expiry_date", ExactDate(value=date(2030, 3, 1))),
])
def test_document_facts_validate(taxonomy, field, value):
    fact = make_fact("c", field=field, value=value, subject_ref="document/chk-01", provenance=(doc_prov(),))
    taxonomy.validate_fact(fact)


def test_unknown_document_type_rejected(taxonomy):
    fact = make_fact("c", field="document.type", value=Text(value="selfie"), subject_ref="document/chk-01",
                     provenance=(doc_prov(),))
    with pytest.raises(TaxonomyError, match="one of"):
        taxonomy.validate_fact(fact)


def test_document_fields_are_grouped(taxonomy):
    fact = make_fact("c", field="document.present", value=Flag(value=True), subject_ref=None,
                     provenance=(doc_prov(),))
    with pytest.raises(TaxonomyError, match="subject_ref"):
        taxonomy.validate_fact(fact)


def test_v01_still_loads_without_document_types():
    old = load_taxonomy(V01)
    assert old.version == "tax-v0.1"
    assert old.document_types == frozenset()


def test_values_from_a_missing_list_fails_load(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text("version: x\nfields:\n  document.type: {type: enum, critical: false, required: false,"
                 " values_from: document_types}\n", encoding="utf-8")
    with pytest.raises(TaxonomyError, match="document_types"):
        load_taxonomy(p)


def test_values_and_values_from_together_fail_load(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text("version: x\ndocument_types: [passport]\nfields:\n  document.type: {type: enum, critical: false,"
                 " required: false, values: [passport], values_from: document_types}\n", encoding="utf-8")
    with pytest.raises(TaxonomyError, match="both"):
        load_taxonomy(p)
