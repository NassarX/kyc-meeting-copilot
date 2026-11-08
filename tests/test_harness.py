"""M1 eval harness (beta 0 step 3): gold facts, case consistency, code graders, scorecard, CLI."""
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from kyc_copilot.domain.enums import FactStatus
from kyc_copilot.domain.models import Money, SpanOffset, Text
from kyc_copilot.eval.case_format import CaseFile, load_case
from kyc_copilot.eval.harness import (EmptyStub, GoldStub, PipelineOutput, consistency_problems, derived_gaps,
                                  gold_facts, input_facts, main, run_cases, score_case, values_match)
from kyc_copilot.rules import load_bounce_reasons

TOY = Path(__file__).parent / "fixtures" / "toy_case.yaml"
CASES = Path(__file__).parents[1] / "cases"


@pytest.fixture
def reasons(taxonomy):
    return load_bounce_reasons(taxonomy)


@pytest.fixture
def toy(taxonomy, reasons):
    return load_case(TOY, taxonomy, reasons)


# ---------- building facts from a case ----------

def test_input_facts_come_from_dossier_and_checklist(toy):
    facts = input_facts(toy)
    fields = {f.field for f in facts}
    assert {"identity.full_name", "identity.residence_country"} <= fields
    assert {"document.type", "document.present", "document.expiry_date"} <= fields
    assert all(f.case_id == toy.case_id for f in facts)


def test_gold_facts_carry_their_spans(toy):
    (amount, tax) = gold_facts(toy)
    assert amount.field == "wealth_event.amount"
    (prov,) = amount.provenance
    assert prov.span_offsets[0].utt_id == "u-02" and prov.extractor_version == "gold"


# ---------- case consistency: the author's expectations match the rules ----------

def test_toy_case_is_consistent(toy, reasons, taxonomy):
    assert consistency_problems(toy, reasons, taxonomy) == []


def test_expected_bounce_reason_that_does_not_fire_is_reported(toy, reasons, taxonomy):
    bad = toy.model_copy(update={"gold": toy.gold.model_copy(update={
        "bounce_reasons": toy.gold.bounce_reasons + ("BR-EDD-LARGE-FUNDING",)})})
    assert any("BR-EDD-LARGE-FUNDING" in p and "expected" in p for p in consistency_problems(bad, reasons, taxonomy))


def test_fired_reason_missing_from_gold_is_reported(toy, reasons, taxonomy):
    bad = toy.model_copy(update={"gold": toy.gold.model_copy(update={"bounce_reasons": ("BR-ID-DOB",)})})
    problems = consistency_problems(bad, reasons, taxonomy)
    assert any("BR-DOC-ID-EXPIRED" in p and "not listed" in p for p in problems)


def test_gold_gap_must_really_be_missing(toy, reasons, taxonomy):
    bad = toy.model_copy(update={"gold": toy.gold.model_copy(update={"gaps": ("identity.tax_residence",)})})
    assert any("identity.tax_residence" in p for p in consistency_problems(bad, reasons, taxonomy))


def test_missing_required_field_not_listed_as_gap_is_reported(toy, reasons, taxonomy):
    # Gaps are checked both ways, like bounce reasons and contradictions: dropping a real gap must not pass.
    bad = toy.model_copy(update={"gold": toy.gold.model_copy(update={
        "gaps": tuple(g for g in toy.gold.gaps if g != "identity.date_of_birth")})})
    assert any("identity.date_of_birth" in p and "not listed" in p for p in consistency_problems(bad, reasons,
                                                                                                taxonomy))


def test_derived_gaps_cover_ungrouped_and_grouped_required_fields(toy, taxonomy):
    gaps = derived_gaps(input_facts(toy) + gold_facts(toy), taxonomy)
    assert "identity.date_of_birth" in gaps
    assert "wealth_event.date@wealth_event/1" in gaps  # the group exists but lacks a required field
    assert "identity.tax_residence" not in gaps



def test_a_declared_public_function_answers_the_pep_question(toy, taxonomy):
    """D02 (demo sample): the client withdrew "nobody in politics" and named a minister sister. Asking them for a
    no-PEP declaration would be wrong; the question is answered. With neither, the gap stays."""
    from kyc_copilot.eval.harness import _fact
    base = [f for f in input_facts(toy) + gold_facts(toy) if not f.field.startswith("pep.")]
    prov = gold_facts(toy)[0].provenance[0]
    sister = _fact(toy, "pep.family_public_function", "pep/1", Text(value="sister, deputy minister"), prov, "test")
    assert "pep.none_declared" in derived_gaps(base, taxonomy)
    assert "pep.none_declared" not in derived_gaps(base + [sister], taxonomy)


# ---------- value matching ----------

def test_values_match_normalises_text_and_money():
    assert values_match(Text(value="Ana  Toy-Example"), Text(value="ana toy-example"))
    assert values_match(Money(amount=Decimal("2400000.00"), currency="EUR"), Money(amount=Decimal("2400000"),
                                                                                   currency="EUR"))
    assert not values_match(Money(amount=Decimal("2400000"), currency="EUR"),
                            Money(amount=Decimal("2400000"), currency="CHF"))


# ---------- free-text matching (8 Nov, after run 1: rewording was scored as a silent wrong value) ----------

def test_critical_text_with_the_same_content_words_matches(taxonomy):
    from kyc_copilot.eval.harness import grade_match
    assert grade_match("pep.family_public_function", Text(value="brother, member of the Bundestag"),
                       Text(value="brother is a member of the Bundestag"), taxonomy)
    assert grade_match("wealth_event.counterparty", Text(value="his father's estate"),
                       Text(value="Father's estate"), taxonomy)


def test_critical_text_missing_or_reordered_words_does_not_match(taxonomy):
    from kyc_copilot.eval.harness import grade_match
    assert not grade_match("structure.beneficial_owner", Text(value="Matthias Egger and his two children"),
                           Text(value="Matthias Egger"), taxonomy)  # a partial owner is still wrong
    assert not grade_match("identity.full_name", Text(value="Ana Toy-Example"), Text(value="Example-Toy Ana"),
                           taxonomy)


def test_descriptive_text_matches_when_one_contains_the_other(taxonomy):
    from kyc_copilot.eval.harness import grade_match
    assert grade_match("income.source", Text(value="salary"), Text(value="Salary as logistics manager"), taxonomy)
    assert grade_match("expected.initial_funding_source", Text(value="the flat sale proceeds"),
                       Text(value="Proceeds from sale of flat in Cork"), taxonomy)
    assert not grade_match("income.source", Text(value="optics consulting"), Text(value="dividends"), taxonomy)


def test_enums_and_typed_values_stay_exact(taxonomy):
    from kyc_copilot.eval.harness import grade_match
    assert not grade_match("wealth_event.type", Text(value="dividends"), Text(value="dividends paid"), taxonomy)
    assert not grade_match("wealth_event.amount", Money(amount=Decimal("1800000"), currency="EUR"),
                           Money(amount=Decimal("1900000"), currency="EUR"), taxonomy)


def test_reworded_critical_value_is_not_counted_as_silent_wrong(toy, reasons, taxonomy):
    d = yaml.safe_load(TOY.read_text(encoding="utf-8"))
    d["transcript"]["utterances"][2]["text"] += " My brother sits in parliament."
    u = d["transcript"]["utterances"][2]["text"]
    q = "My brother sits in parliament"
    d["gold"]["facts"].append({"field": "pep.family_public_function", "subject_ref": "pep/1",
                               "value": {"kind": "text", "value": "brother, member of parliament"},
                               "spans": [{"utt_id": "u-03", "start": u.index(q), "end": u.index(q) + len(q),
                                          "quote": q}]})
    d["gold"]["bounce_reasons"].append("BR-EDD-PEP")
    case = CaseFile.model_validate(d)
    out = GoldStub().run(case)
    reworded = tuple(f.model_copy(update={"value": Text(value="brother is a member of parliament")})
                     if f.field == "pep.family_public_function" else f for f in out.facts)
    s = score_case(case, PipelineOutput(facts=reworded), reasons, taxonomy)
    assert s.silent_wrong_critical == 0 and s.recall == 1.0


# ---------- graders ----------

def test_gold_stub_scores_perfectly(toy, reasons, taxonomy):
    s = score_case(toy, GoldStub().run(toy), reasons, taxonomy)
    assert s.precision == 1.0 and s.recall == 1.0 and s.critical_recall == 1.0
    assert s.silent_wrong_critical == 0 and s.span_rejections == 0 and s.missing_provenance == 0
    assert s.bounce_recall == 1.0 and s.bounce_false_fires == ()


def test_empty_stub_finds_nothing_from_the_transcript(toy, reasons, taxonomy):
    s = score_case(toy, EmptyStub().run(toy), reasons, taxonomy)
    assert s.recall == 0.0 and s.precision is None  # nothing predicted: precision undefined, not 1.0
    assert "BR-TAX-RESIDENCE-DIFFERS" in s.bounce_missed  # needs the extracted tax residence


def test_wrong_critical_value_counts_as_silent_wrong(toy, reasons, taxonomy):
    out = GoldStub().run(toy)
    wrong = out.facts[0].model_copy(update={"value": Money(amount=Decimal("3400000"), currency="EUR")})
    s = score_case(toy, PipelineOutput(facts=(wrong,) + out.facts[1:]), reasons, taxonomy)
    assert s.silent_wrong_critical == 1 and s.precision == 0.5 and s.recall == 0.5



def test_scorecard_names_each_silent_wrong_value_so_it_can_be_checked(toy, reasons, taxonomy):
    out = GoldStub().run(toy)
    wrong = out.facts[0].model_copy(update={"value": Money(amount=Decimal("3400000"), currency="EUR")})
    s = score_case(toy, PipelineOutput(facts=(wrong,) + out.facts[1:]), reasons, taxonomy)
    ((field, subject, got, expected),) = s.silent_wrong
    assert field == wrong.field and "3400000" in got and "3400000" not in expected
    from kyc_copilot.eval.harness import Scorecard
    card = Scorecard(pipeline="test", versions={}, cases={toy.case_id: s})
    md = card.markdown()
    assert "## Silent wrong values" in md and "3400000" in md


def test_wrong_value_marked_contradicted_is_not_silent(toy, reasons, taxonomy):
    out = GoldStub().run(toy)
    flagged = out.facts[0].model_copy(update={"value": Money(amount=Decimal("3400000"), currency="EUR"),
                                              "status": FactStatus.CONTRADICTED})
    s = score_case(toy, PipelineOutput(facts=(flagged,) + out.facts[1:]), reasons, taxonomy)
    assert s.silent_wrong_critical == 0


def test_fact_whose_span_does_not_match_the_transcript_is_rejected(toy, reasons, taxonomy):
    out = GoldStub().run(toy)
    f = out.facts[1]
    bad_prov = f.provenance[0].model_copy(update={"span_offsets": (SpanOffset(utt_id="u-03", start=0, end=4,
                                                                             quote="Paris"),)})
    s = score_case(toy, PipelineOutput(facts=(out.facts[0], f.model_copy(update={"provenance": (bad_prov,)}))),
                   reasons, taxonomy)
    assert s.span_rejections == 1 and s.recall == 0.5  # a rejected fact does not count as found


def test_contradiction_recall(taxonomy, reasons):
    d = yaml.safe_load(TOY.read_text(encoding="utf-8"))
    d["gold"]["contradictions"] = [{"field": "identity.residence_country", "values": [
        {"kind": "country", "iso2": "LU"}, {"kind": "country", "iso2": "BE"}], "sources": ["dossier", "transcript"]}]
    case = CaseFile.model_validate(d)
    assert score_case(case, EmptyStub().run(case), reasons, taxonomy).contradiction_recall == 0.0
    assert score_case(case, GoldStub().run(case), reasons, taxonomy).contradiction_recall == 1.0


# ---------- scorecard and CLI ----------

def test_run_cases_aggregates_and_reports_problems(tmp_path, taxonomy, reasons):
    (tmp_path / "T00.yaml").write_text(TOY.read_text(encoding="utf-8"), encoding="utf-8")
    card = run_cases(tmp_path, GoldStub(), taxonomy, reasons)
    assert card.problems == {} and len(card.cases) == 1
    assert card.totals["recall"] == 1.0
    assert "T00" in card.markdown() and "| recall |" in card.markdown().lower()
    assert "tax-v0.2" in card.markdown() and reasons.version in card.markdown()  # versions used


def test_cli_exit_codes(tmp_path, capsys):
    (tmp_path / "T00.yaml").write_text(TOY.read_text(encoding="utf-8"), encoding="utf-8")
    assert main(["run", "--cases", str(tmp_path), "--pipeline", "gold"]) == 0
    assert "T00" in capsys.readouterr().out
    bad = yaml.safe_load(TOY.read_text(encoding="utf-8"))
    bad["gold"]["bounce_reasons"] = ["BR-ID-DOB"]
    (tmp_path / "T01.yaml").write_text(yaml.safe_dump(bad, sort_keys=False).replace("case_id: T00", "case_id: T01"),
                                       encoding="utf-8")
    assert main(["run", "--cases", str(tmp_path), "--pipeline", "gold"]) == 1


# ---------- the real case set ----------

def case_files():
    return sorted(CASES.glob("*.yaml")) if CASES.exists() else []


@pytest.mark.parametrize("path", case_files(), ids=lambda p: p.stem)
def test_every_case_loads_is_consistent_and_gold_scores_perfectly(path, taxonomy, reasons):
    case = load_case(path, taxonomy, reasons)
    assert path.stem == case.case_id
    assert consistency_problems(case, reasons, taxonomy) == []
    s = score_case(case, GoldStub().run(case), reasons, taxonomy)
    assert s.recall == 1.0 and s.precision == 1.0 and s.bounce_recall in (1.0, None)


# ---------- group alignment: an extractor may number groups differently ----------

def _renumber(facts, mapping):
    return tuple(f.model_copy(update={"subject_ref": mapping.get(f.subject_ref, f.subject_ref)}) for f in facts)


def test_swapped_group_numbers_still_score_perfectly(taxonomy, reasons):
    case = load_case(CASES / "C01.yaml", taxonomy, reasons)
    out = GoldStub().run(case)
    swapped = _renumber(out.facts, {"wealth_event/1": "wealth_event/2", "wealth_event/2": "wealth_event/1",
                                    "structure/1": "structure/9"})
    s = score_case(case, PipelineOutput(facts=swapped), reasons, taxonomy)
    assert s.precision == 1.0 and s.recall == 1.0 and s.silent_wrong_critical == 0


def test_alignment_does_not_hide_a_wrong_value(taxonomy, reasons):
    case = load_case(CASES / "C01.yaml", taxonomy, reasons)
    out = GoldStub().run(case)
    wrong = tuple(f.model_copy(update={"value": Money(amount=Decimal("3400000"), currency="EUR")})
                  if (f.field, f.subject_ref) == ("wealth_event.amount", "wealth_event/2") else f for f in out.facts)
    renumbered = _renumber(wrong, {"wealth_event/2": "wealth_event/7"})
    s = score_case(case, PipelineOutput(facts=renumbered), reasons, taxonomy)
    assert s.silent_wrong_critical == 1 and s.recall < 1.0


# ---------- gold contradictions must be what reconcile finds (step 4) ----------

def test_gold_contradiction_reconcile_does_not_find_is_reported(toy, reasons, taxonomy):
    from kyc_copilot.eval.case_format import GoldContradiction
    from kyc_copilot.domain.models import Country
    k = GoldContradiction(field="identity.residence_country", values=(Country(iso2="LU"), Country(iso2="BE")),
                          sources=("dossier", "transcript"))
    bad = toy.model_copy(update={"gold": toy.gold.model_copy(update={"contradictions": (k,)})})
    assert any("identity.residence_country" in p and "reconcile" in p for p in consistency_problems(bad, reasons,
                                                                                                    taxonomy))


def test_conflict_reconcile_finds_must_be_listed_in_gold(toy, reasons, taxonomy):
    d = yaml.safe_load(TOY.read_text(encoding="utf-8"))
    d["dossier"].append({"field": "identity.tax_residence", "value": {"kind": "country", "iso2": "LU"}})
    case = CaseFile.model_validate(d)
    problems = consistency_problems(case, reasons, taxonomy)
    assert any("identity.tax_residence" in p and "not listed" in p for p in problems)


# ---------- privacy (I10): facts must not quote special-category disclosures ----------

def _with_forbidden(utts):
    d = yaml.safe_load(TOY.read_text(encoding="utf-8"))
    d["gold"]["forbidden_utterances"] = utts
    return d


def test_fact_quoting_a_forbidden_utterance_is_a_privacy_leak(taxonomy, reasons):
    case = CaseFile.model_validate(_with_forbidden(["u-03"]))  # u-03 holds the toy's tax residence quote
    s = score_case(case, GoldStub().run(case), reasons, taxonomy)
    assert s.privacy_leaks == 1


def test_no_forbidden_utterances_means_no_leaks(toy, reasons, taxonomy):
    assert score_case(toy, GoldStub().run(toy), reasons, taxonomy).privacy_leaks == 0


def test_forbidden_utterance_must_exist_and_gold_may_not_quote_it(taxonomy, reasons, tmp_path):
    from kyc_copilot.eval.case_format import CaseFormatError
    p = tmp_path / "T00.yaml"
    p.write_text(yaml.safe_dump(_with_forbidden(["u-99"])), encoding="utf-8")
    with pytest.raises(CaseFormatError, match="u-99"):
        load_case(p, taxonomy, reasons)
    p.write_text(yaml.safe_dump(_with_forbidden(["u-03"])), encoding="utf-8")
    with pytest.raises(CaseFormatError, match="forbidden"):
        load_case(p, taxonomy, reasons)


# ---------- noisy runs (D01): the pipeline reads the noisy transcript, scored against the clean gold ----------

def test_noisy_run_reads_the_noisy_transcript_and_skips_cases_without_one(tmp_path, taxonomy, reasons):
    seen = []

    class Spy:
        name = "spy"

        def run(self, case):
            seen.append((case.case_id, case.transcript.utterances[1].text))
            return PipelineOutput()

    d = yaml.safe_load(TOY.read_text(encoding="utf-8"))
    (tmp_path / "T00.yaml").write_text(yaml.safe_dump(d), encoding="utf-8")
    noisy = yaml.safe_load(TOY.read_text(encoding="utf-8"))
    noisy["case_id"] = "T01"
    noisy["noisy_transcript"] = {**noisy["transcript"], "utterances": [
        {**u, "text": u["text"].replace("2.4", "2.9")} for u in noisy["transcript"]["utterances"]]}
    (tmp_path / "T01.yaml").write_text(yaml.safe_dump(noisy), encoding="utf-8")
    card = run_cases(tmp_path, Spy(), taxonomy, reasons, noisy=True)
    assert [c for c, _ in seen] == ["T01"] and "2.9" in seen[0][1]
    assert list(card.cases) == ["T01"] and card.versions["transcript"] == "noisy"
