"""Plausibility check: facts that can't all be true get a warning, so a wrong value is never silent."""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from kyc_copilot.domain.enums import Purpose, SourceType
from kyc_copilot.domain.models import ExactDate, Fact, Money, Provenance, SpanOffset
from kyc_copilot.eval.case_format import load_case
from kyc_copilot.eval.harness import GoldStub, PipelineOutput, gold_facts, score_case
from kyc_copilot.plausibility import check
from kyc_copilot.rules import load_bounce_reasons

CASES = Path(__file__).parents[1] / "cases"
AS_OF = date(2026, 8, 25)


def fact(field, value, subject=None):
    prov = Provenance(source_type=SourceType.TRANSCRIPT, source_ref="t", extractor_version="test",
                      span_offsets=(SpanOffset(utt_id="u-01", start=0, end=1),))
    return Fact(case_id="T00", field=field, subject_ref=subject, value=value, confidence=1.0,
                purpose=(Purpose.AML,), provenance=(prov,), created_by="test")


def eur(a):
    return Money(amount=Decimal(a), currency="EUR")


def test_funding_above_every_stated_source_warns_both_sides():
    funding = fact("expected.initial_funding_amount", eur("600000"))
    dividend = fact("wealth_event.amount", eur("78000"), "wealth_event/1")
    (d,) = check([funding, dividend], AS_OF)
    assert set(d.fact_ids) == {funding.fact_id, dividend.fact_id} and d.rule == "funding_exceeds_sources"


def test_funding_covered_by_sources_or_assets_is_fine():
    funding = fact("expected.initial_funding_amount", eur("3000000"))
    assert check([funding, fact("wealth_event.amount", eur("4200000"), "wealth_event/1")], AS_OF) == []
    assert check([funding, fact("asset.value", eur("3900000"), "asset/1")], AS_OF) == []
    two = [fact("wealth_event.amount", eur("2000000"), "wealth_event/1"),
           fact("wealth_event.amount", eur("1500000"), "wealth_event/2")]
    assert check([funding, *two], AS_OF) == []  # sources add up


def test_no_currency_guessing_and_no_sources_means_no_warning():
    funding = fact("expected.initial_funding_amount", eur("900000"))
    chf = fact("wealth_event.amount", Money(amount=Decimal("100000"), currency="CHF"), "wealth_event/1")
    assert check([funding, chf], AS_OF) == []
    assert check([funding], AS_OF) == []


def test_dates_in_the_future_warn():
    sale = fact("wealth_event.date", ExactDate(value=date(2027, 1, 1)), "wealth_event/1")
    est = fact("structure.established", ExactDate(value=date(2026, 9, 1)), "structure/1")
    rules = {d.rule for d in check([sale, est], AS_OF)}
    assert rules == {"date_in_future"} and len(check([sale, est], AS_OF)) == 2
    assert check([fact("wealth_event.date", ExactDate(value=date(2026, 8, 25)), "wealth_event/1")], AS_OF) == []


@pytest.mark.parametrize("born,warns", [(date(2010, 1, 1), True), (date(1900, 1, 1), True), (date(1969, 1, 30), False)])
def test_date_of_birth_must_give_an_adult_age(born, warns):
    assert bool(check([fact("identity.date_of_birth", ExactDate(value=born))], AS_OF)) is warns


@pytest.mark.parametrize("path", sorted(CASES.glob("C*.yaml")), ids=lambda p: p.stem)
def test_gold_answers_raise_no_warnings(path, taxonomy):
    # Guard against eager rules: the correct answer to every frozen case must look plausible.
    case = load_case(path, taxonomy, load_bounce_reasons(taxonomy))
    assert check(gold_facts(case), case.as_of_date) == []


def test_warned_wrong_value_is_not_silent_and_warned_right_value_is_a_false_warning(taxonomy):
    from kyc_copilot.plausibility import Doubt
    reasons = load_bounce_reasons(taxonomy)
    case = load_case(CASES / "D01.yaml", taxonomy, reasons)
    out = GoldStub().run(case)
    wrong = tuple(f.model_copy(update={"value": eur("78000")})
                  if f.field == "wealth_event.amount" else f for f in out.facts)
    amount = next(f for f in wrong if f.field == "wealth_event.amount")
    funding = next(f for f in wrong if f.field == "expected.initial_funding_amount")
    silent = score_case(case, PipelineOutput(facts=wrong), reasons, taxonomy)
    warned = score_case(case, PipelineOutput(facts=wrong, doubts=(
        Doubt(fact_ids=(amount.fact_id, funding.fact_id), rule="funding_exceeds_sources", message="x"),)),
        reasons, taxonomy)
    assert silent.silent_wrong_critical == 1 and silent.false_warnings == 0
    assert warned.silent_wrong_critical == 0 and warned.false_warnings == 1  # the funding amount was right


def test_the_implausible_demo_case_raises_exactly_its_two_intended_doubts(taxonomy):
    """D04 is written to be implausible: funding above every stated source, and a sale dated after the meeting."""
    case = load_case(CASES / "D04.yaml", taxonomy, load_bounce_reasons(taxonomy))
    assert sorted(d.rule for d in check(gold_facts(case), case.as_of_date)) == ["date_in_future", "funding_exceeds_sources"]
