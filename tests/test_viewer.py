"""Demo viewer server: one route per input, all through kyc_copilot.run.process. Fakes only: no model, no spend."""
from datetime import date

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import kyc_copilot.capture as cap  # noqa: E402
import kyc_copilot.extract as ex  # noqa: E402
from kyc_copilot.viewer import create_app  # noqa: E402
from test_capture_run import SEGS  # noqa: E402
from test_extract import FakeClient, ef  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "CACHE_DIR", tmp_path / "llm")
    monkeypatch.setattr(cap, "CACHE_DIR", tmp_path / "asr")


def app_with(tmp_path, taxonomy, *replies, **kw):
    client = FakeClient(*replies)
    return TestClient(create_app(extractor=lambda cap_usd: ex.ModelExtractor(taxonomy, client=client, cap_usd=cap_usd),
                                 transcribe=lambda path, day: cap.segments_to_transcript(SEGS, day),
                                 audio_dir=tmp_path / "audio", spend_file=tmp_path / "spend.json", **kw))


def test_page_and_fonts_are_served(tmp_path, taxonomy):
    c = app_with(tmp_path, taxonomy)
    page = c.get("/")
    assert page.status_code == 200 and "Synthetic demo data" in page.text
    assert c.get("/static/fonts/source-serif-4-latin-wght-normal.woff2").status_code == 200


def test_pasted_transcript_runs_the_check(tmp_path, taxonomy):
    reply = ex.Extraction(facts=[ef("pep.family_public_function", "brother, member of parliament", "u-02",
                                    "My brother sits in parliament", "pep/1")])
    c = app_with(tmp_path, taxonomy, reply)
    r = c.post("/api/run", data={"transcript": "rm: Any public function?\nclient: My brother sits in parliament.",
                                 "meeting_date": "2026-11-07"})
    body = r.json()
    assert r.status_code == 200 and body["facts"][0]["spans"][0]["quote"] == "My brother sits in parliament"
    assert "BR-EDD-PEP" in {f["reason_id"] for f in body["flags"]} and body["audio_url"] is None


def test_uploaded_audio_is_transcribed_kept_for_playback_and_gives_clips(tmp_path, taxonomy):
    reply = ex.Extraction(facts=[ef("wealth_event.amount", "1250000", "u-01", "1.25 million", "wealth_event/1",
                                    currency="CHF")])
    c = app_with(tmp_path, taxonomy, reply)
    r = c.post("/api/run", data={"meeting_date": "2026-11-07"}, files={"audio": ("m.m4a", b"fake", "audio/mp4")})
    body = r.json()
    (fact,) = body["facts"]
    assert fact["critical"] and fact["clip"] == [0.8, 1.9]  # the words "1.25 million"
    assert c.get(body["audio_url"]).content == b"fake"


def test_sample_case_borrows_its_bank_file(tmp_path, taxonomy):
    reply = ex.Extraction(facts=[ef("identity.full_name", "Isabel Marchetti-Okonkwo", "u-15", "Isabelle Marchetti-Okonkwo")])
    body = app_with(tmp_path, taxonomy, reply).post("/api/sample").json()
    assert body["case"] == "C01" and any(c["field"] == "identity.full_name" for c in body["contradictions"])


def test_bad_input_is_a_clear_400(tmp_path, taxonomy):
    c = app_with(tmp_path, taxonomy)
    assert c.post("/api/run", data={"transcript": "   "}).status_code == 400
    assert c.get("/api/audio/../../etc/passwd").status_code == 404


def test_a_fact_quoted_twice_plays_only_its_shortest_quote():
    from types import SimpleNamespace as NS
    from kyc_copilot.run import RunResult
    t = cap.segments_to_transcript(SEGS, date(2026, 11, 7))
    u1, u2 = t.utterances[0], t.utterances[-1]
    fact = NS(provenance=[NS(span_offsets=[NS(utt_id=u1.utt_id, start=0, end=len(u1.text)),
                                           NS(utt_id=u2.utt_id, start=0, end=4)])])
    clip = RunResult._clip(NS(transcript=t), fact)
    assert clip and clip[0] >= u2.words[0].t_start  # the short quote in the last turn, not first-to-last


# ---------- handover: samples, password, budget ----------

def test_samples_are_listed_by_name_and_each_one_runs(tmp_path, taxonomy):
    c = app_with(tmp_path, taxonomy, ex.Extraction(facts=[]))
    listed = c.get("/api/samples").json()
    assert [x["id"] for x in listed] == ["C01", "D01", "D02", "D03", "D04", "D05"]
    assert all(x["title"] and x["blurb"] for x in listed)
    body = c.post("/api/sample/D02").json()
    assert body["sample"] == "D02" and body["case"] is None and "Kowalczyk-Amari" in body["transcript"][3]["text"]
    assert c.post("/api/sample/D99").status_code == 404


def test_a_password_protects_every_route_when_set(tmp_path, taxonomy):
    c = app_with(tmp_path, taxonomy, password="open sesame")
    r = c.get("/")
    assert r.status_code == 401 and r.headers["www-authenticate"].startswith("Basic")
    assert c.get("/static/fonts/source-serif-4-latin-wght-normal.woff2").status_code == 401
    assert c.get("/", auth=("demo", "wrong")).status_code == 401
    assert c.get("/", auth=("anyone", "open sesame")).status_code == 200
    assert app_with(tmp_path, taxonomy).get("/").status_code == 200  # no password set: open, as on localhost


def test_spend_is_recorded_and_a_used_up_budget_stops_new_spend_but_not_cached_runs(tmp_path, taxonomy):
    import json
    reply = ex.Extraction(facts=[ef("identity.residence_country", "CH", "u-01", "I live in Zurich")])
    c = app_with(tmp_path, taxonomy, reply, budget_usd=1.0)
    form = {"transcript": "client: I live in Zurich.", "meeting_date": "2026-11-07"}
    assert c.post("/api/run", data=form).status_code == 200
    assert json.loads((tmp_path / "spend.json").read_text())["spent_usd"] > 0  # the fake call was priced
    (tmp_path / "spend.json").write_text(json.dumps({"spent_usd": 1.0}))
    assert c.post("/api/run", data=form).status_code == 200  # same meeting: from cache, free
    r = c.post("/api/run", data={"transcript": "client: I live in Geneva.", "meeting_date": "2026-11-07"})
    assert r.status_code == 402 and "budget" in r.json()["detail"]
