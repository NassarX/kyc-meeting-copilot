"""Step 5 extraction plumbing, with a fake client: no network, no spend."""
from pathlib import Path
from types import SimpleNamespace

import pytest

import kyc_copilot.extract as ex
from kyc_copilot.domain.enums import FactStatus
from kyc_copilot.eval.case_format import load_case
from kyc_copilot.eval.harness import score_case
from kyc_copilot.rules import load_bounce_reasons

TOY = Path(__file__).parent / "fixtures" / "toy_case.yaml"


def ef(field, value, utt, quote, subject=None, **kw):
    base = dict(currency=None, period=None, date_precision=None, relative_words=None, confidence=None, superseded=False)
    return ex.ExtractedFact(field=field, subject_ref=subject, value=value, spans=[ex.ExtractedSpan(utt_id=utt,
                            quote=quote)], **{**base, **kw})


class FakeClient:
    """Returns queued Extractions; records every request."""
    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []
        self.messages = self

    def parse(self, **kw):
        self.requests.append(kw)
        usage = SimpleNamespace(input_tokens=1000, output_tokens=500, cache_read_input_tokens=0,
                                cache_creation_input_tokens=0)
        return SimpleNamespace(stop_reason="end_turn", parsed_output=self.replies.pop(0), usage=usage)


@pytest.fixture
def toy(taxonomy):
    return load_case(TOY, taxonomy, load_bounce_reasons(taxonomy))


@pytest.fixture(autouse=True)
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "CACHE_DIR", tmp_path / "cache")


def gold_reply():
    return ex.Extraction(facts=[
        ef("wealth_event.amount", "2400000", "u-02", "3.4 million, sorry, 2.4 million euros", "wealth_event/1",
           currency="EUR", period="one_off"),
        ef("identity.tax_residence", "FR", "u-03", "tax resident in France")])


def test_correct_reply_scores_like_gold(taxonomy, toy):
    m = ex.ModelExtractor(taxonomy, client=FakeClient(gold_reply()))
    s = score_case(toy, m.run(toy), load_bounce_reasons(taxonomy), taxonomy)
    assert s.recall == 1.0 and s.precision == 1.0 and s.span_rejections == 0


def test_offsets_are_computed_from_the_quote_not_trusted(taxonomy, toy):
    out = ex.ModelExtractor(taxonomy, client=FakeClient(gold_reply())).run(toy)
    span = next(f for f in out.facts if f.field == "identity.tax_residence").provenance[0].span_offsets[0]
    text = next(u.text for u in toy.transcript.utterances if u.utt_id == "u-03")
    assert text[span.start:span.end] == "tax resident in France"


def test_bad_quote_is_retried_once_then_kept_if_fixed(taxonomy, toy):
    bad = ex.Extraction(facts=[ef("identity.tax_residence", "FR", "u-03", "resident of France")])
    fixed = ex.Extraction(facts=[ef("identity.tax_residence", "FR", "u-03", "tax resident in France")])
    client = FakeClient(bad, fixed)
    m = ex.ModelExtractor(taxonomy, client=client)
    out = m.run(toy)
    assert len(client.requests) == 2 and "failed checks" in client.requests[1]["messages"][0]["content"]
    assert [f.field for f in out.facts] == ["identity.tax_residence"] and m.rejected[toy.case_id] == []


def test_quote_still_wrong_after_retry_is_dropped_and_reported(taxonomy, toy):
    bad = ex.Extraction(facts=[ef("identity.tax_residence", "FR", "u-03", "resident of France")])
    m = ex.ModelExtractor(taxonomy, client=FakeClient(bad, bad))
    assert m.run(toy).facts == () and "not in u-03" in m.rejected[toy.case_id][0]


def test_unknown_field_and_bad_enum_are_rejected(taxonomy, toy):
    reply = ex.Extraction(facts=[ef("identity.shoe_size", "42", "u-03", "France"),
                                 ef("wealth_event.type", "lottery", "u-02", "2.4 million euros", "wealth_event/1")])
    m = ex.ModelExtractor(taxonomy, client=FakeClient(reply, ex.Extraction(facts=[])))
    assert m.run(toy).facts == () and len(m.rejected[toy.case_id]) == 0  # retry returned nothing new
    assert len(m.calls) == 2


def test_relative_date_keeps_the_words(taxonomy, toy):
    v = ex.to_value("date", ef("identity.residence_since", "2023-06-01", "u-01", "x",
                               relative_words="three years ago in June"), toy.transcript.meeting_date)
    assert v.kind == "relative_date" and v.words == "three years ago in June" and str(v.resolved) == "2023-06-01"


def test_cache_means_rescoring_costs_nothing(taxonomy, toy):
    m1 = ex.ModelExtractor(taxonomy, client=FakeClient(gold_reply()))
    m1.run(toy)
    m2 = ex.ModelExtractor(taxonomy, client=FakeClient())  # no replies queued: a real call would fail
    m2.run(toy)
    assert m1.spent > 0 and m2.spent == 0 and m2.calls[0].cached


def test_spend_cap_stops_before_the_call(taxonomy, toy):
    m = ex.ModelExtractor(taxonomy, cap_usd=0.01, client=FakeClient(gold_reply()))
    with pytest.raises(ex.SpendCapReached):
        m.run(toy)
    assert m.client.requests == []


def test_cost_uses_the_price_table(taxonomy, toy):
    m = ex.ModelExtractor(taxonomy, client=FakeClient(gold_reply()))
    m.run(toy)
    assert m.spent == pytest.approx((1000 * 4.00 + 500 * 20.00) / 1e6)


def test_system_prompt_is_stable_and_has_no_case_data(taxonomy, toy):
    a, b = ex.system_prompt(taxonomy), ex.system_prompt(taxonomy)
    assert a == b and toy.case_id not in a and "document.type" not in a


def test_fact_in_a_dossier_conflict_is_marked_contradicted(taxonomy, toy):
    reply = ex.Extraction(facts=[ef("identity.residence_country", "BE", "u-03", "France")])
    out = ex.ModelExtractor(taxonomy, client=FakeClient(reply)).run(toy)
    # the toy dossier holds LU; the transcript-derived BE is a contradiction, never a silent value
    assert out.facts[0].status is FactStatus.CONTRADICTED
    assert out.contradictions == (("identity.residence_country", None),)


def test_key_comes_from_env_never_hardcoded(monkeypatch, tmp_path):
    monkeypatch.setenv(ex.KEY_VAR, "test-key")
    assert ex.api_key() == "test-key"
    monkeypatch.delenv(ex.KEY_VAR)
    monkeypatch.setattr(ex, "REPO_ROOT", tmp_path)
    with pytest.raises(RuntimeError, match=ex.KEY_VAR):
        ex.api_key()


def test_quote_match_ignores_case_and_extra_whitespace_and_returns_raw_offsets():
    text = "I live in   Monaco, and I am tax resident in Monaco."
    start, end = ex.locate(text, "live in monaco")
    assert text[start:end] == "live in   Monaco"
    assert ex.locate(text, "lives in Monaco") is None
