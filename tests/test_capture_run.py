"""Audio capture and the one-meeting entry point, with fakes: no model download, no API spend."""
from datetime import date
from pathlib import Path

import pytest

import kyc_copilot.capture as cap
import kyc_copilot.extract as ex
from kyc_copilot.eval.case_format import load_case
from kyc_copilot.eval.harness import run_capture
from kyc_copilot.rules import load_bounce_reasons
from kyc_copilot.run import process, read_transcript
from test_extract import FakeClient, ef

CASES = Path(__file__).parents[1] / "cases"
DAY = date(2026, 11, 7)


@pytest.fixture(autouse=True)
def tmp_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(cap, "CACHE_DIR", tmp_path / "asr")
    monkeypatch.setattr(ex, "CACHE_DIR", tmp_path / "llm")


def test_segments_become_unlabelled_utterances():
    t = cap.segments_to_transcript([{"text": " Hello. "}, {"text": "  "}, {"text": "I live in Zurich."}], DAY)
    assert [u.utt_id for u in t.utterances] == ["u-01", "u-02"]
    assert {u.speaker for u in t.utterances} == {"unknown"} and t.utterances[1].text == "I live in Zurich."


def test_transcripts_are_cached_by_audio_content(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"fake audio")
    calls = []

    def engine(path, model):
        calls.append(path)
        return [{"start": 0, "end": 1, "text": "I live in Zurich."}]

    first = cap.transcribe(audio, DAY, engine=engine)
    second = cap.transcribe(audio, DAY, engine=engine)
    assert len(calls) == 1 and first == second


def test_read_transcript_parses_speakers_and_keeps_colons_in_sentences(tmp_path):
    p = tmp_path / "m.txt"
    p.write_text("RM: Welcome.\nClient: The ratio was 3:1, roughly.\nJust a line with no label\n\n", encoding="utf-8")
    t = read_transcript(p, DAY)
    assert [(u.speaker, u.text) for u in t.utterances] == [
        ("rm", "Welcome."), ("client", "The ratio was 3:1, roughly."), ("unknown", "Just a line with no label")]


def test_unknown_speakers_get_a_note_only_when_labels_are_missing(taxonomy):
    case = load_case(CASES / "C01.yaml", taxonomy, load_bounce_reasons(taxonomy))
    assert "not available" not in ex.user_prompt(case)
    heard = case.model_copy(update={"transcript": cap.segments_to_transcript([{"text": "Hello."}], DAY)})
    assert "Speaker labels are not available" in ex.user_prompt(heard)


def test_process_returns_facts_flags_doubts_and_gaps(tmp_path, taxonomy):
    p = tmp_path / "m.txt"
    p.write_text("rm: Any public function?\nclient: My brother sits in the Bundestag.\n", encoding="utf-8")
    reply = ex.Extraction(facts=[ef("pep.family_public_function", "brother, member of the Bundestag", "u-02",
                                    "My brother sits in the Bundestag", "pep/1")])
    result = process(read_transcript(p, DAY), extractor=ex.ModelExtractor(taxonomy, client=FakeClient(reply)))
    fired = {f["reason_id"] for f in result.flags}
    assert {"BR-EDD-PEP", "BR-ID-DOB", "BR-DOC-ID-MISSING"} <= fired  # no DOB and no documents in this snippet
    assert "identity.date_of_birth" in result.gaps and result.doubts == ()
    d = result.to_dict()
    assert d["facts"][0]["spans"][0]["quote"] == "My brother sits in the Bundestag"
    assert "BR-EDD-PEP" in result.markdown()


def test_run_capture_scores_each_recording_against_the_case_gold(tmp_path, taxonomy):
    reasons = load_bounce_reasons(taxonomy)
    case = load_case(CASES / "C01.yaml", taxonomy, reasons)
    audio = tmp_path / "spike-01-baseline.wav"
    audio.write_bytes(b"x")
    def heard(a, d):
        return cap.segments_to_transcript([{"text": "I moved to Luxembourg three years ago in June."}], d)
    reply = ex.Extraction(facts=[ef("identity.residence_country", "LU", "u-01", "I moved to Luxembourg")])
    card = run_capture(case, [audio], ex.ModelExtractor(taxonomy, client=FakeClient(reply)), taxonomy, reasons,
                       transcribe=heard)
    s = card.cases["spike-01-baseline (whisper)"]
    assert s.tp == 1 and s.span_rejections == 0 and card.versions["transcript"] == "audio"


def test_capture_scores_a_device_transcript_next_to_whisper(tmp_path, taxonomy):
    # The spike scores Apple's own transcript (Voice Memos) and Whisper's on the same recording.
    reasons = load_bounce_reasons(taxonomy)
    case = load_case(CASES / "C01.yaml", taxonomy, reasons)
    apple = tmp_path / "spike-01-baseline.txt"
    apple.write_text("I moved to Luxembourg three years ago in June.\n", encoding="utf-8")
    audio = tmp_path / "spike-01-baseline.m4a"
    audio.write_bytes(b"x")
    def heard(a, d):
        return cap.segments_to_transcript([{"text": "I moved to Luxembourg three years ago in June."}], d)
    reply = ex.Extraction(facts=[ef("identity.residence_country", "LU", "u-01", "I moved to Luxembourg")])
    card = run_capture(case, [audio], ex.ModelExtractor(taxonomy, client=FakeClient(reply)), taxonomy, reasons,
                       transcribe=heard, transcripts=[apple])
    assert set(card.cases) == {"spike-01-baseline (whisper)", "spike-01-baseline (device)"}
    assert all(s.tp == 1 for s in card.cases.values())  # the same transcript text: one cached reply serves both


def test_device_transcript_is_split_into_sentences_without_inventing_speakers(tmp_path):
    from kyc_copilot.capture import read_device_transcript
    p = tmp_path / "apple.txt"
    p.write_text("Let me check the spelling: M-A-R-C-H. That is right! Where do you\nhold these assets now?", "utf-8")
    t = read_device_transcript(p, DAY)
    assert [u.text for u in t.utterances] == ["Let me check the spelling: M-A-R-C-H.", "That is right!",
                                             "Where do you hold these assets now?"]
    assert {u.speaker for u in t.utterances} == {"unknown"}


def test_a_long_phrase_before_a_colon_is_not_a_speaker(tmp_path):
    p = tmp_path / "m.txt"
    p.write_text("Let me check the spelling: M-A-R.\nDr Wierzbicki: It was two point four.\n", encoding="utf-8")
    t = read_transcript(p, DAY)
    assert [u.speaker for u in t.utterances] == ["unknown", "dr wierzbicki"]


def test_titles_and_company_suffixes_do_not_end_a_sentence(tmp_path):
    from kyc_copilot.capture import read_device_transcript
    p = tmp_path / "apple.txt"
    p.write_text("This is Dr. Tomasz Wierzbicki. Mostly from Valdoria Holdings S.A. On the second of September.", "utf-8")
    assert [u.text for u in read_device_transcript(p, DAY).utterances] == [
        "This is Dr. Tomasz Wierzbicki.", "Mostly from Valdoria Holdings S.A. On the second of September."]


# ---------- misheard values, layer 1: the transcriber's own doubt ----------

SEGS = [{"start": 0.0, "end": 3.0, "text": " I sold it for 1.25 million Swiss grams.",
         "words": [{"word": " I", "start": 0.0, "end": 0.2, "probability": 0.99},
                   {"word": " sold", "start": 0.2, "end": 0.5, "probability": 0.98},
                   {"word": " it", "start": 0.5, "end": 0.6, "probability": 0.99},
                   {"word": " for", "start": 0.6, "end": 0.8, "probability": 0.97},
                   {"word": " 1.25", "start": 0.8, "end": 1.4, "probability": 0.95},
                   {"word": " million", "start": 1.4, "end": 1.9, "probability": 0.96},
                   {"word": " Swiss", "start": 1.9, "end": 2.3, "probability": 0.9},
                   {"word": " grams.", "start": 2.3, "end": 3.0, "probability": 0.21}]}]


def test_word_scores_map_onto_the_utterance_text():
    t = cap.segments_to_transcript(SEGS, DAY)
    (u,) = t.utterances
    assert u.text == "I sold it for 1.25 million Swiss grams."
    grams = u.words[-1]
    assert u.text[grams.start:grams.end] == "grams." and grams.probability == 0.21 and grams.t_end == 3.0


def test_fact_quoting_a_doubtful_word_needs_confirmation(taxonomy):
    t = cap.segments_to_transcript(SEGS, DAY)
    case = load_case(CASES / "C01.yaml", taxonomy, load_bounce_reasons(taxonomy)).model_copy(update={"transcript": t})
    sure = ef("wealth_event.amount", "1250000", "u-01", "1.25 million", "wealth_event/1", currency="CHF")
    unsure = ef("wealth_event.type", "business_sale", "u-01", "I sold it", "wealth_event/1")
    garbled = ef("asset.custodian", "Swiss grams", "u-01", "Swiss grams", "asset/1")
    out = ex.ModelExtractor(taxonomy, client=FakeClient(ex.Extraction(facts=[sure, unsure, garbled]))).run(case)
    heard = [d for d in out.doubts if d.rule == "unclear_audio"]
    (d,) = heard
    flagged = {f.field for f in out.facts if f.fact_id in d.fact_ids}
    assert flagged == {"asset.custodian"} and "grams." in d.message and "0.21" in d.message


def test_typed_transcripts_have_no_word_scores_and_raise_no_audio_doubt(taxonomy):
    case = load_case(CASES / "C01.yaml", taxonomy, load_bounce_reasons(taxonomy))
    reply = ex.Extraction(facts=[ef("identity.residence_country", "LU", "u-12", "I moved to Luxembourg")])
    out = ex.ModelExtractor(taxonomy, client=FakeClient(reply)).run(case)
    assert not [d for d in out.doubts if d.rule == "unclear_audio"]


def test_audio_doubts_can_be_switched_off_for_a_before_after_comparison(taxonomy):
    t = cap.segments_to_transcript(SEGS, DAY)
    case = load_case(CASES / "C01.yaml", taxonomy, load_bounce_reasons(taxonomy)).model_copy(update={"transcript": t})
    garbled = ef("asset.custodian", "Swiss grams", "u-01", "Swiss grams", "asset/1")
    out = ex.ModelExtractor(taxonomy, client=FakeClient(ex.Extraction(facts=[garbled])), audio_doubts=False).run(case)
    assert not [d for d in out.doubts if d.rule == "unclear_audio"]
