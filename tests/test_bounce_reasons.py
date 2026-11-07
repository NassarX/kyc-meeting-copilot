"""Bounce reasons: the loader's reference checks and the four worked checks."""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from kyc_copilot.domain.enums import SourceType
from kyc_copilot.domain.models import Country, ExactDate, Flag, Money, Provenance, Text
from kyc_copilot.rules import BounceReasonError, Outcome, evaluate, load_bounce_reasons
from conftest import make_fact

AS_OF = date(2026, 11, 1)


@pytest.fixture
def reasons(taxonomy):
    return load_bounce_reasons(taxonomy)


def doc(field, value, item="chk-01"):
    prov = Provenance(source_type=SourceType.DOCUMENT, source_ref=item, extractor_version="checklist-loader-v1")
    return make_fact("c", field=field, value=value, subject_ref=f"document/{item}", provenance=(prov,))


def passport(expiry: date, item="chk-01", present=True):
    return [doc("document.type", Text(value="passport"), item), doc("document.present", Flag(value=present), item),
            doc("document.expiry_date", ExactDate(value=expiry), item)]


def result(results, reason_id):
    (r,) = [r for r in results if r.reason_id == reason_id]
    return r


# ---------- loader ----------

def test_default_file_loads_and_every_reason_has_a_source(reasons):
    assert len(reasons.reasons) >= 4
    for r in reasons.reasons:
        assert r.source.type in {"public", "interview"} and r.source.ref


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "r.yaml"
    p.write_text("version: test\nreasons:\n" + body, encoding="utf-8")
    return p


def test_unknown_field_fails_load(tmp_path, taxonomy):
    p = _write(tmp_path, "  - {id: X1, title: t, category: fact, effect: bounce,"
                         " source: {type: public, ref: r, checked: false},"
                         " check: {kind: missing_fact, field: client.favourite_colour}}\n")
    with pytest.raises(BounceReasonError, match="unknown field"):
        load_bounce_reasons(taxonomy, p)


def test_unknown_document_type_fails_load(tmp_path, taxonomy):
    p = _write(tmp_path, "  - {id: X1, title: t, category: document, effect: bounce,"
                         " source: {type: public, ref: r, checked: false},"
                         " check: {kind: document_expired, document_type: selfie}}\n")
    with pytest.raises(BounceReasonError, match="document type"):
        load_bounce_reasons(taxonomy, p)


def test_missing_source_fails_load(tmp_path, taxonomy):
    p = _write(tmp_path, "  - {id: X1, title: t, category: fact, effect: bounce,"
                         " check: {kind: missing_fact, field: identity.full_name}}\n")
    with pytest.raises(BounceReasonError, match="source"):
        load_bounce_reasons(taxonomy, p)


def test_non_public_source_type_fails_load(tmp_path, taxonomy):
    """Only public or interview sources are allowed: no private or internal material."""
    p = _write(tmp_path, "  - {id: X1, title: t, category: fact, effect: bounce,"
                         " source: {type: employer, ref: r, checked: false},"
                         " check: {kind: missing_fact, field: identity.full_name}}\n")
    with pytest.raises(BounceReasonError, match="source"):
        load_bounce_reasons(taxonomy, p)


def test_duplicate_ids_fail_load(tmp_path, taxonomy):
    row = ("  - {id: X1, title: t, category: fact, effect: bounce,"
           " source: {type: public, ref: r, checked: false},"
           " check: {kind: missing_fact, field: identity.full_name}}\n")
    with pytest.raises(BounceReasonError, match="duplicate"):
        load_bounce_reasons(taxonomy, _write(tmp_path, row + row))


def test_unknown_check_kind_fails_load(tmp_path, taxonomy):
    p = _write(tmp_path, "  - {id: X1, title: t, category: fact, effect: bounce,"
                         " source: {type: public, ref: r, checked: false}, check: {kind: vibes}}\n")
    with pytest.raises(BounceReasonError, match="check kind"):
        load_bounce_reasons(taxonomy, p)


# ---------- worked check 1: missing fact ----------

def test_missing_fact_fires_when_absent_and_passes_when_present(reasons):
    assert result(evaluate(reasons, [], AS_OF), "BR-ID-DOB").outcome is Outcome.FIRE
    dob = make_fact("c", field="identity.date_of_birth", subject_ref=None, value=ExactDate(value=date(1970, 5, 2)))
    r = result(evaluate(reasons, [dob], AS_OF), "BR-ID-DOB")
    assert r.outcome is Outcome.PASS and r.fact_refs == (dob.fact_id,)


# ---------- worked check 2: expired document vs as_of_date ----------

def test_expired_passport_fires(reasons):
    r = result(evaluate(reasons, passport(date(2026, 10, 31)), AS_OF), "BR-DOC-ID-EXPIRED")
    assert r.outcome is Outcome.FIRE and r.fact_refs


def test_passport_expiring_on_as_of_date_is_still_valid(reasons):
    assert result(evaluate(reasons, passport(AS_OF), AS_OF), "BR-DOC-ID-EXPIRED").outcome is Outcome.PASS


def test_judged_against_as_of_date_not_today(reasons):
    facts = passport(date(2026, 6, 1))
    assert result(evaluate(reasons, facts, date(2026, 5, 1)), "BR-DOC-ID-EXPIRED").outcome is Outcome.PASS
    assert result(evaluate(reasons, facts, date(2026, 7, 1)), "BR-DOC-ID-EXPIRED").outcome is Outcome.FIRE


def test_missing_passport_fires_the_missing_document_reason(reasons):
    assert result(evaluate(reasons, [], AS_OF), "BR-DOC-ID-MISSING").outcome is Outcome.FIRE
    absent = passport(date(2030, 1, 1), present=False)
    assert result(evaluate(reasons, absent, AS_OF), "BR-DOC-ID-MISSING").outcome is Outcome.FIRE
    assert result(evaluate(reasons, passport(date(2030, 1, 1)), AS_OF), "BR-DOC-ID-MISSING").outcome is Outcome.PASS


def test_expiry_check_is_unknown_without_an_expiry_date(reasons):
    facts = [doc("document.type", Text(value="passport")), doc("document.present", Flag(value=True))]
    assert result(evaluate(reasons, facts, AS_OF), "BR-DOC-ID-EXPIRED").outcome is Outcome.UNKNOWN


# ---------- worked check 3: cross-field mismatch ----------

def _countries(res: str, tax: str):
    return [make_fact("c", field="identity.residence_country", subject_ref=None, value=Country(iso2=res)),
            make_fact("c", field="identity.tax_residence", subject_ref=None, value=Country(iso2=tax))]


def test_residence_and_tax_residence_differ_fires(reasons):
    r = result(evaluate(reasons, _countries("LU", "FR"), AS_OF), "BR-TAX-RESIDENCE-DIFFERS")
    assert r.outcome is Outcome.FIRE and len(r.fact_refs) == 2


def test_same_residence_and_tax_residence_passes(reasons):
    assert result(evaluate(reasons, _countries("LU", "LU"), AS_OF), "BR-TAX-RESIDENCE-DIFFERS").outcome is Outcome.PASS


def test_mismatch_unknown_when_one_side_missing(reasons):
    facts = _countries("LU", "LU")[:1]
    assert result(evaluate(reasons, facts, AS_OF), "BR-TAX-RESIDENCE-DIFFERS").outcome is Outcome.UNKNOWN


# ---------- worked check 4: threshold trigger ----------

def _funding(amount: str, currency="EUR"):
    return [make_fact("c", field="expected.initial_funding_amount", subject_ref=None,
                      value=Money(amount=Decimal(amount), currency=currency))]


def test_funding_at_threshold_fires_the_edd_flag(reasons):
    r = result(evaluate(reasons, _funding("5000000"), AS_OF), "BR-EDD-LARGE-FUNDING")
    assert r.outcome is Outcome.FIRE and r.effect == "flag"


def test_funding_below_threshold_passes(reasons):
    assert result(evaluate(reasons, _funding("4999999.99"), AS_OF), "BR-EDD-LARGE-FUNDING").outcome is Outcome.PASS


def test_other_currency_is_unknown_not_a_silent_pass(reasons):
    assert result(evaluate(reasons, _funding("9000000", "USD"), AS_OF), "BR-EDD-LARGE-FUNDING").outcome is Outcome.UNKNOWN


def test_evaluation_is_deterministic(reasons):
    facts = _funding("6000000") + _countries("LU", "FR") + passport(date(2025, 1, 1))
    assert evaluate(reasons, facts, AS_OF) == evaluate(reasons, facts, AS_OF)


# ---------- hard triggers (step 4): flags before G1, never blocks (invariant I8) ----------

def _f(field, value, subject=None):
    return make_fact("c", field=field, subject_ref=subject, value=value)


def test_triggers_are_flags_with_public_sources(reasons):
    trig = {r.id: r for r in reasons.reasons if r.category == "risk"}
    for rid in ("BR-EDD-PEP", "BR-EDD-HIGH-RISK-COUNTRY", "BR-EDD-ASSET-VEHICLE", "BR-EDD-SOW-UNCORROBORATED"):
        assert trig[rid].effect == "flag" and trig[rid].source.type == "public"


def test_pep_fires_on_any_indicator_even_if_none_declared(reasons):
    brother = [_f("pep.family_public_function", Text(value="brother is a deputy minister"), "pep/1"),
               _f("pep.none_declared", Flag(value=True))]
    assert result(evaluate(reasons, brother, AS_OF), "BR-EDD-PEP").outcome is Outcome.FIRE


def test_pep_passes_only_when_declared_none_and_no_indicator(reasons):
    assert result(evaluate(reasons, [_f("pep.none_declared", Flag(value=True))], AS_OF),
                  "BR-EDD-PEP").outcome is Outcome.PASS
    assert result(evaluate(reasons, [], AS_OF), "BR-EDD-PEP").outcome is Outcome.UNKNOWN


def test_high_risk_country_fires_on_a_listed_structure_jurisdiction(reasons):
    facts = [_f("identity.residence_country", Country(iso2="LU")),
             _f("structure.jurisdiction", Country(iso2="VG"), "structure/1")]
    r = result(evaluate(reasons, facts, AS_OF), "BR-EDD-HIGH-RISK-COUNTRY")
    assert r.outcome is Outcome.FIRE and len(r.fact_refs) == 1


def test_high_risk_country_passes_when_no_listed_country(reasons):
    facts = [_f("identity.residence_country", Country(iso2="LU")),
             _f("structure.jurisdiction", Country(iso2="LI"), "structure/1")]
    assert result(evaluate(reasons, facts, AS_OF), "BR-EDD-HIGH-RISK-COUNTRY").outcome is Outcome.PASS
    assert result(evaluate(reasons, [], AS_OF), "BR-EDD-HIGH-RISK-COUNTRY").outcome is Outcome.UNKNOWN


def test_asset_holding_vehicle_fires_on_foundation_or_trust(reasons):
    found = [_f("structure.type", Text(value="foundation"), "structure/2")]
    assert result(evaluate(reasons, found, AS_OF), "BR-EDD-ASSET-VEHICLE").outcome is Outcome.FIRE
    company = [_f("structure.type", Text(value="company"), "structure/1")]
    assert result(evaluate(reasons, company, AS_OF), "BR-EDD-ASSET-VEHICLE").outcome is Outcome.PASS


def _event(amount, currency="EUR", kind="business_sale", subject="wealth_event/1"):
    return [_f("wealth_event.type", Text(value=kind), subject),
            _f("wealth_event.amount", Money(amount=Decimal(amount), currency=currency), subject)]


def test_large_sow_without_its_document_fires(reasons):
    r = result(evaluate(reasons, _event("6000000"), AS_OF), "BR-EDD-SOW-UNCORROBORATED")
    assert r.outcome is Outcome.FIRE


def test_large_sow_with_the_matching_document_passes(reasons):
    facts = _event("6000000") + [doc("document.type", Text(value="sale_agreement"), "chk-09"),
                                 doc("document.present", Flag(value=True), "chk-09")]
    assert result(evaluate(reasons, facts, AS_OF), "BR-EDD-SOW-UNCORROBORATED").outcome is Outcome.PASS


def test_document_for_another_event_type_does_not_corroborate(reasons):
    facts = _event("6000000", kind="inheritance") + [doc("document.type", Text(value="sale_agreement"), "chk-09"),
                                                    doc("document.present", Flag(value=True), "chk-09")]
    assert result(evaluate(reasons, facts, AS_OF), "BR-EDD-SOW-UNCORROBORATED").outcome is Outcome.FIRE


def test_small_sow_passes_and_foreign_currency_is_unknown(reasons):
    assert result(evaluate(reasons, _event("1000000"), AS_OF), "BR-EDD-SOW-UNCORROBORATED").outcome is Outcome.PASS
    assert result(evaluate(reasons, _event("9000000", "CHF"), AS_OF),
                  "BR-EDD-SOW-UNCORROBORATED").outcome is Outcome.UNKNOWN


def test_list_check_needs_a_known_list(tmp_path, taxonomy):
    p = _write(tmp_path, "  - {id: X1, title: t, category: risk, effect: flag,"
                         " source: {type: public, ref: r, checked: false},"
                         " check: {kind: country_in_list, fields: [identity.nationality], list: nope}}\n")
    with pytest.raises(BounceReasonError, match="list"):
        load_bounce_reasons(taxonomy, p)


def test_value_in_check_rejects_values_outside_the_enum(tmp_path, taxonomy):
    p = _write(tmp_path, "  - {id: X1, title: t, category: risk, effect: flag,"
                         " source: {type: public, ref: r, checked: false},"
                         " check: {kind: value_in, field: structure.type, values: [spaceship]}}\n")
    with pytest.raises(BounceReasonError, match="spaceship"):
        load_bounce_reasons(taxonomy, p)
