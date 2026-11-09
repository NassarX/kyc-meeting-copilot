# D02 PEP in passing and a changed answer: what the check should catch

The note the meeting was written from. The scored answer is `cases/D02.yaml`; where they differ, the case file is the reference.

Meeting date: 2026-11-09. Client: Dariusz Piotr Kowalczyk-Amari. RM and client only.

## Test points
1. Family PEP, first downplayed. The client says "nobody in politics", then calls the sister's job "a civil service thing", then admits she was appointed deputy minister of infrastructure last year.
2. Changed answer on tax residence. Monaco early on, then near the end "for this year I'm still filing in Poland".
3. With the corrected answer, tax residence (PL) differs from residence (MC).

## Facts it should find (* = critical)
- identity.full_name*: Dariusz Piotr Kowalczyk-Amari
- identity.date_of_birth*: 1979-11-22
- identity.nationality*: PL
- identity.residence_country*: MC; identity.residence_since: 2025-09 ("since September last year")
- identity.tax_residence*: MC, superseded; then PL, current
- wealth_event/1: type business_sale; date* 2023-06; amount* EUR 3,200,000 (before tax); counterparty* Halderveen Software Partners; ownership_pct* 60
- asset/1: real estate near Zakopane, PL, value* about EUR 400,000
- income/1: advisory board fees, amount* EUR 90,000 per year
- pep.family_public_function*: sister (Agnieszka Kowalczyk), deputy minister of infrastructure, Poland
- pep.none_declared*: may be extracted as true from "Nobody in politics". The family PEP fact must still win (see flags).
- expected.initial_funding_amount*: EUR 2,000,000; expected.initial_funding_source: sale proceeds at a bank in Warsaw
- expected.annual_flows: about EUR 90,000 per year in

## Flags expected
- BR-EDD-PEP: fire, on pep.family_public_function. The rule lets an indicator beat a declaration of none.
- BR-TAX-RESIDENCE-DIFFERS: fire (MC vs PL, using the current answer).
- BR-DOC-ID-MISSING: fires on every paste (no checklist). Not a finding.
- Must not fire: BR-EDD-LARGE-FUNDING (EUR 2M), BR-EDD-SOW-UNCORROBORATED (3.2M is under EUR 5M), BR-EDD-HIGH-RISK-COUNTRY.

## Gaps
- None.

## Doubts
- changed_answer on identity.tax_residence: first MC, then PL. Confirm which stands.
- No funding doubt: EUR 2M is under the EUR 3.6M of stated sources and assets.

## Must not
- Must not drop the PEP because the client said "not politics" or "technocrat".
- Must not treat the PEP denial and the sister's role as two values of one field: they are different fields, so this shows as a flag, not a contradiction.
- Unsure: whether the extractor marks pep.none_declared superseded after the admission. Either is acceptable as long as BR-EDD-PEP fires.
