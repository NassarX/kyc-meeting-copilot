"""Build cases/C01.yaml from the spike script, computing span offsets (never hand-typed)."""
import sys
from pathlib import Path
import yaml

U = [
 ("u-01","rm","Thank you for coming, Ms Marchetti-Okonkwo. Let me check the spelling: M-A-R-C-H-E-T-T-I, then a hyphen, O-K-O-N-K-W-O."),
 ("u-02","client","That is right. This is Dr Tomasz Wierzbicki, my accountant."),
 ("u-03","accountant","Pleased to meet you. I have worked with Isabelle since the fourteenth of March, twenty nineteen."),
 ("u-04","rm","Could you walk me through where your wealth comes from?"),
 ("u-05","client","Mostly from my company, Valdoria Holdings S.A. On the second of September, twenty twenty-two, I sold a forty percent stake for one point two five million Swiss francs."),
 ("u-06","rm","And the rest of the company?"),
 ("u-07","client","I kept sixty percent. The company paid me dividends of three point four million euros, no, sorry, two point four million euros."),
 ("u-08","accountant","It was two point four, yes."),
 ("u-09","rm","Where do you hold these assets now?"),
 ("u-10","client","A brokerage account with seven hundred eighty thousand dollars, and a foundation in Liechtenstein, which I set up on the third of April, twenty twenty-one."),
 ("u-11","rm","And your income today?"),
 ("u-12","client","Consulting. About ninety-five thousand Swiss francs a year. I moved to Luxembourg three years ago in June."),
 ("u-13","rm","Any borrowing?"),
 ("u-14","client","A mortgage at four and a quarter percent."),
 ("u-15","rm","Let me recap: Isabelle Marchetti-Okonkwo, and dividends of two point four million euros. Please correct me."),
]
text = {u: t for u, _, t in U}

def span(utt, quote):
    i = text[utt].find(quote)
    assert i >= 0 and text[utt].find(quote, i + 1) < 0, (utt, quote)
    return {"utt_id": utt, "start": i, "end": i + len(quote), "quote": quote}

def fact(field, value, spans, subject=None, derivation=None):
    d = {"field": field}
    if subject:
        d["subject_ref"] = subject
    d["value"] = value
    d["spans"] = [span(*s) for s in spans]
    if derivation:
        d["derivation"] = derivation
    return d

def money(a, c, p=None):
    return {"kind": "money", "amount": a, "currency": c, **({"period": p} if p else {})}


facts = [
 fact("identity.full_name", {"kind": "text", "value": "Isabelle Marchetti-Okonkwo"}, [("u-15", "Isabelle Marchetti-Okonkwo")]),
 fact("identity.residence_country", {"kind": "country", "iso2": "LU"}, [("u-12", "I moved to Luxembourg")]),
 fact("identity.residence_since", {"kind": "relative_date", "words": "three years ago in June", "anchor": "2026-11-07", "resolved": "2023-06-01"},
      [("u-12", "three years ago in June")], derivation="relative date resolved against the meeting date, month precision"),
 fact("relationship.person_present", {"kind": "text", "value": "Dr Tomasz Wierzbicki"}, [("u-02", "Dr Tomasz Wierzbicki")], "relationship/1"),
 fact("relationship.role", {"kind": "text", "value": "accountant"}, [("u-02", "my accountant")], "relationship/1"),
 fact("wealth_event.type", {"kind": "text", "value": "business_sale"}, [("u-05", "I sold a forty percent stake")], "wealth_event/1"),
 fact("wealth_event.date", {"kind": "date", "value": "2022-09-02"}, [("u-05", "the second of September, twenty twenty-two")], "wealth_event/1"),
 fact("wealth_event.amount", money("1250000", "CHF"), [("u-05", "one point two five million Swiss francs")], "wealth_event/1"),
 fact("wealth_event.counterparty", {"kind": "text", "value": "Valdoria Holdings S.A."}, [("u-05", "Valdoria Holdings S.A.")], "wealth_event/1",
      derivation="the stake sold was in the client's own company"),
 fact("wealth_event.ownership_pct", {"kind": "percent", "value": "40"}, [("u-05", "forty percent stake")], "wealth_event/1"),
 fact("wealth_event.type", {"kind": "text", "value": "dividends"}, [("u-07", "dividends")], "wealth_event/2"),
 fact("wealth_event.amount", money("2400000", "EUR"), [("u-07", "three point four million euros, no, sorry, two point four million euros"), ("u-08", "It was two point four, yes.")],
      "wealth_event/2", derivation="self-correction: the second figure stands, confirmed by the accountant and the recap"),
 fact("structure.type", {"kind": "text", "value": "company"}, [("u-05", "my company")], "structure/1"),
 fact("structure.name", {"kind": "text", "value": "Valdoria Holdings S.A."}, [("u-05", "Valdoria Holdings S.A.")], "structure/1"),
 fact("asset.type", {"kind": "text", "value": "brokerage_account"}, [("u-10", "A brokerage account")], "asset/1"),
 fact("asset.value", money("780000", "USD"), [("u-10", "seven hundred eighty thousand dollars")], "asset/1"),
 fact("structure.type", {"kind": "text", "value": "foundation"}, [("u-10", "a foundation")], "structure/2"),
 fact("structure.jurisdiction", {"kind": "country", "iso2": "LI"}, [("u-10", "Liechtenstein")], "structure/2"),
 fact("structure.established", {"kind": "date", "value": "2021-04-03"}, [("u-10", "the third of April, twenty twenty-one")], "structure/2"),
 fact("income.source", {"kind": "text", "value": "consulting"}, [("u-12", "Consulting")], "income/1"),
 fact("income.amount", money("95000", "CHF", "per_year"), [("u-12", "About ninety-five thousand Swiss francs a year")], "income/1",
      derivation="'about' kept as the stated figure"),
 fact("liability.type", {"kind": "text", "value": "mortgage"}, [("u-14", "A mortgage")], "liability/1"),
 fact("liability.rate", {"kind": "percent", "value": "4.25"}, [("u-14", "four and a quarter percent")], "liability/1"),
]

case = {
 "case_id": "C01",
 "title": "Business sale and dividends, simple (spike script: Marchetti-Okonkwo)",
 "origin": "author",
 "as_of_date": "2026-11-07",
 "lead": {"lead_ref": "lead-c01", "rm_id": "rm.alice"},
 "transcript": {"meeting_date": "2026-11-07", "utterances": [{"utt_id": u, "speaker": s, "text": t} for u, s, t in U]},
 "dossier": [
   {"field": "identity.full_name", "value": {"kind": "text", "value": "Isabelle Marchetti-Okonkwo"}},
   {"field": "identity.nationality", "value": {"kind": "country", "iso2": "IT"}},
 ],
 "checklist": [
   {"item_id": "chk-01", "document_type": "passport", "present": True, "issue_date": "2021-02-10", "expiry_date": "2031-02-09"},
   {"item_id": "chk-02", "document_type": "proof_of_address", "present": True, "issue_date": "2026-09-15"},
   {"item_id": "chk-03", "document_type": "sale_agreement", "present": False},
 ],
 "gold": {
   "facts": facts,
   "gaps": ["identity.date_of_birth", "identity.tax_residence", "wealth_event.date@wealth_event/2",
            "pep.none_declared", "expected.initial_funding_source", "expected.initial_funding_amount"],
   "contradictions": [],
   "bounce_reasons": ["BR-ID-DOB", "BR-EDD-ASSET-VEHICLE"],
 },
 "traps": [
   {"kind": "extraction_trap", "note": "self-corrected dividend: 3.4M must not be extracted; 2.4M stands", "refs": ["u-07", "u-08", "u-15"]},
   {"kind": "extraction_trap", "note": "relative date 'three years ago in June' must keep its words and resolve against the meeting date", "refs": ["u-12"]},
   {"kind": "missing_required", "note": "no date of birth anywhere", "refs": ["identity.date_of_birth"]},
 ],
 "seeded_drafts": [
   {"draft_id": "C01-S1", "field": "wealth_event.amount", "subject_ref": "wealth_event/2",
    "wrong_value": money("3400000", "EUR")},
 ],
}
header = ("# C01: synthetic meeting written by Claude as the capture test script. No real people or companies.\n"
          "# Synthetic people only (I12). Span offsets were computed from the text, not typed by hand.\n")
Path(sys.argv[1]).write_text(header + yaml.safe_dump(case, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
