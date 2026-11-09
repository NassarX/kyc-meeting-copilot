# D04 implausible numbers: what the check should catch

The note the meeting was written from. The scored answer is `cases/D04.yaml`; where they differ, the case file is the reference.

Meeting date: 2026-11-09. Client: Beatriz Helena Moreira Lindgren. RM and client only.

## Test points
1. Funding is larger than every stated CHF source: CHF 4.5M planned against a CHF 2.4M sale plus a CHF 600k brokerage account (CHF 3.0M).
2. The sale is dated February 2027 (12 Feb 2027), after the meeting date.
3. Mid-sentence correction: "three, no, sorry, two point four million Swiss francs". Only 2.4M should be kept.

## Facts it should find (* = critical)
- identity.full_name*: Beatriz Helena Moreira Lindgren
- identity.date_of_birth*: 1971-08-09
- identity.nationality*: BR
- identity.residence_country*: CH; identity.residence_since: 2008
- identity.tax_residence*: CH
- wealth_event/1: type business_sale; date* 2027-02-12; amount* CHF 2,400,000; counterparty* Orvana Praxisgruppe; ownership_pct* 100
- asset/1: brokerage account, value* CHF 600,000
- liability/1: mortgage, rate 1.4
- income/1: consulting for the buyer, amount* CHF 180,000 per year
- income/2: dividends, amount* about CHF 15,000 per year
- pep.none_declared*: true
- expected.initial_funding_amount*: CHF 4,500,000; expected.initial_funding_source: sale proceeds and brokerage account
- expected.annual_flows: about CHF 100,000 per year

## Flags expected
- BR-DOC-ID-MISSING: fires on every paste (no checklist). Not a finding.
- BR-EDD-LARGE-FUNDING and BR-EDD-SOW-UNCORROBORATED: unknown, not fired. Their lines are in EUR and the PoC has no FX, so a CHF amount can't be compared.
- Must not fire: BR-TAX-RESIDENCE-DIFFERS, BR-EDD-PEP, BR-EDD-HIGH-RISK-COUNTRY, BR-EDD-ASSET-VEHICLE.

## Gaps
- None.

## Doubts
- funding_exceeds_sources: CHF 4.5M is more than the CHF 3.0M of stated sources and assets.
- date_in_future: wealth_event.date 2027-02-12 is after 2026-11-09.

## Must not
- Must not store CHF 3,000,000 as the sale amount, and must not raise a changed_answer doubt for it: a slip corrected on the spot is not a changed answer.
- Must not "fix" the date to 2026 on its own. It should keep 2027 and let the doubt ask the RM.
