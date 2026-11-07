from datetime import date

import pytest

from kyc_copilot.domain.models import Country, ExactDate, RelativeDate, Text
from kyc_copilot.taxonomy import TaxonomyError
from conftest import make_fact


def test_loads_version_and_fields(taxonomy):
    assert taxonomy.version == "tax-v0.2"
    assert len(taxonomy.fields) >= 30


def test_names_amounts_dates_are_critical(taxonomy):
    for key in ("identity.full_name", "identity.date_of_birth", "wealth_event.amount",
                "wealth_event.date", "structure.beneficial_owner", "wealth_event.ownership_pct"):
        assert key in taxonomy.critical_fields


def test_valid_fact_passes(taxonomy):
    taxonomy.validate_fact(make_fact("c"))


def test_unknown_field_rejected(taxonomy):
    with pytest.raises(TaxonomyError, match="unknown field"):
        taxonomy.validate_fact(make_fact("c", field="client.favourite_colour"))


def test_wrong_value_type_rejected(taxonomy):
    with pytest.raises(TaxonomyError, match="expects money"):
        taxonomy.validate_fact(make_fact("c", value=Text(value="lots")))


def test_enum_value_checked(taxonomy):
    taxonomy.validate_fact(make_fact("c", field="wealth_event.type", value=Text(value="business_sale")))
    with pytest.raises(TaxonomyError, match="one of"):
        taxonomy.validate_fact(make_fact("c", field="wealth_event.type", value=Text(value="lottery")))


def test_grouped_field_needs_subject_ref(taxonomy):
    with pytest.raises(TaxonomyError, match="subject_ref"):
        taxonomy.validate_fact(make_fact("c", subject_ref=None))


def test_relative_date_accepted_for_date_fields(taxonomy):
    """Spike item D4: 'three years ago in June' keeps its words."""
    v = RelativeDate(words="three years ago in June", anchor=date(2026, 11, 7))
    taxonomy.validate_fact(make_fact("c", field="identity.residence_since", subject_ref=None, value=v))


def test_country_field(taxonomy):
    taxonomy.validate_fact(make_fact("c", field="identity.residence_country", subject_ref=None,
                                     value=Country(iso2="LU")))
