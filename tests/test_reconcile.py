"""S4 reconcile (beta 0 step 4): the only component that decides a contradiction (I6). Pure and deterministic."""
from datetime import date
from decimal import Decimal

from kyc_copilot.domain.enums import FactStatus, SourceType
from kyc_copilot.domain.models import Country, ExactDate, Money, Provenance, RelativeDate, Text
from kyc_copilot.reconcile import RECONCILE_VERSION, find_conflicts
from conftest import make_fact

DOSSIER = Provenance(source_type=SourceType.DOSSIER, source_ref="dossier", extractor_version="dossier-stub")


def f(field, value, subject=None, **kw):
    return make_fact("c", field=field, subject_ref=subject, value=value, **kw)


def test_dossier_and_transcript_disagree():
    d = f("identity.tax_residence", Country(iso2="LU"), provenance=(DOSSIER,))
    t = f("identity.tax_residence", Country(iso2="FR"))
    (c,) = find_conflicts([d, t], [])
    assert c.field == "identity.tax_residence" and c.subject_ref is None and set(c.fact_ids) == {d.fact_id, t.fact_id}


def test_same_value_in_different_words_is_no_conflict():
    a = f("identity.full_name", Text(value="Ana  Toy"), provenance=(DOSSIER,))
    b = f("identity.full_name", Text(value="ana toy"))
    assert find_conflicts([a, b], []) == []


def test_relative_date_resolving_to_the_same_day_is_no_conflict():
    a = f("identity.residence_since", ExactDate(value=date(2023, 6, 1)), provenance=(DOSSIER,))
    b = f("identity.residence_since", RelativeDate(words="three years ago in June", anchor=date(2026, 11, 7),
                                                   resolved=date(2023, 6, 1)))
    assert find_conflicts([a, b], []) == []


def test_groups_are_compared_within_their_subject_only():
    a = f("wealth_event.amount", Money(amount=Decimal("1"), currency="EUR"), "wealth_event/1")
    b = f("wealth_event.amount", Money(amount=Decimal("2"), currency="EUR"), "wealth_event/2")
    assert find_conflicts([a, b], []) == []


def test_three_way_disagreement_is_one_contradiction():
    vals = [f("wealth_event.amount", Money(amount=Decimal(v), currency="EUR"), "wealth_event/1") for v in "123"]
    (c,) = find_conflicts(vals, [])
    assert len(c.fact_ids) == 3


def test_nationality_can_have_several_values():
    a = f("identity.nationality", Country(iso2="IT"), provenance=(DOSSIER,))
    b = f("identity.nationality", Country(iso2="NG"))
    assert find_conflicts([a, b], []) == []


def test_superseded_and_already_contradicted_facts_are_not_raised_again():
    d = f("identity.tax_residence", Country(iso2="LU"), provenance=(DOSSIER,))
    t = f("identity.tax_residence", Country(iso2="FR"))
    copies = [x.model_copy(update={"fact_id": x.fact_id + "-k", "status": FactStatus.CONTRADICTED,
                                   "supersedes_fact_id": x.fact_id}) for x in (d, t)]
    assert find_conflicts([d, t, *copies], [frozenset({d.fact_id, t.fact_id})]) == []


def test_rm_fix_that_supersedes_one_side_clears_the_group():
    d = f("identity.tax_residence", Country(iso2="LU"), provenance=(DOSSIER,))
    t = f("identity.tax_residence", Country(iso2="FR"))
    copies = [x.model_copy(update={"fact_id": x.fact_id + "-k", "status": FactStatus.CONTRADICTED,
                                   "supersedes_fact_id": x.fact_id}) for x in (d, t)]
    fix = f("identity.tax_residence", Country(iso2="FR"), supersedes_fact_id=copies[1].fact_id)
    assert find_conflicts([d, t, *copies, fix], [frozenset({d.fact_id, t.fact_id})]) == []


def test_output_is_deterministic():
    facts = [f("identity.tax_residence", Country(iso2=c)) for c in ("LU", "FR")] + \
            [f("wealth_event.amount", Money(amount=Decimal(v), currency="EUR"), "wealth_event/1") for v in "12"]
    assert find_conflicts(facts, []) == find_conflicts(list(reversed(facts)), [])
    assert RECONCILE_VERSION
