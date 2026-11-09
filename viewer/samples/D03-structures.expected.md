# D03 structures with an accountant: what the check should catch

The note the meeting was written from. The scored answer is `cases/D03.yaml`; where they differ, the case file is the reference.

Meeting date: 2026-11-09. Client: Aurelio Kenji Bastien-Nakamura. Third party: accountant Henrike Valtersson.

## Test points
1. Two layers: Tessaro Holdings Limited (company, Jersey) is owned 100% by the Alvermont Foundation (Liechtenstein). The foundation is the legal owner of the company; the client is the beneficial owner of both.
2. The accountant states most structure facts. Facts from a third party present still count.
3. Gap: the client's date of birth is never asked or said.
4. Large EUR amounts: the sale (EUR 14.1M) and the funding (EUR 6M) pass the EUR 5M lines.

## Facts it should find (* = critical)
- identity.full_name*: Aurelio Kenji Bastien-Nakamura
- identity.nationality*: CA
- identity.residence_country*: AE; identity.residence_since: 2020-03
- identity.tax_residence*: AE
- relationship/1: person_present Henrike Valtersson, role accountant
- wealth_event/1: type business_sale; date* 2022-10; amount* EUR 14,100,000 (the client's "fourteen million, roughly" refined to 14.1); counterparty* Marlowe Ridge Capital; ownership_pct* 35
- structure/1: type company; name* Tessaro Holdings Limited; jurisdiction* JE; established* 2014; beneficial_owner* Aurelio Bastien-Nakamura
- structure/2: type foundation; name* Alvermont Foundation; jurisdiction* LI; established* 2019-06; beneficial_owner* Aurelio Bastien-Nakamura (first beneficiary; children second)
- asset/1: real estate, PT (Lisbon), value* EUR 1,900,000, held by the foundation
- asset/2: cash and bonds in Tessaro, LI, value* EUR 11,000,000, custodian "a private bank in Vaduz"
- income/1: dividend from Tessaro, amount* EUR 400,000 per year
- income/2: board seat, amount* about EUR 30,000 per year
- pep.none_declared*: true
- expected.initial_funding_amount*: EUR 6,000,000; expected.initial_funding_source: Tessaro's account in Vaduz

## Flags expected
- BR-ID-DOB: fire (bounce). Date of birth missing.
- BR-EDD-ASSET-VEHICLE: fire, structure.type foundation.
- BR-EDD-LARGE-FUNDING: fire, EUR 6M is at least EUR 5M.
- BR-EDD-SOW-UNCORROBORATED: fire, a EUR 14.1M business sale with no sale agreement, register extract or shareholder register on file (they are only promised).
- BR-DOC-ID-MISSING: fires on every paste (no checklist). Not a finding.
- Must not fire: BR-EDD-HIGH-RISK-COUNTRY (CA, AE, JE, LI, PT are not on the list), BR-TAX-RESIDENCE-DIFFERS, BR-EDD-PEP.

## Gaps
- identity.date_of_birth.

## Doubts
- None. Funding EUR 6M is under the stated EUR sources and assets.

## Must not
- Must not name the foundation, or Tessaro, as a beneficial owner. The foundation is the legal owner of Tessaro; the beneficial owner is the client.
- Must not guess a date of birth.
- Must not raise a contradiction between "fourteen million, roughly" and "fourteen point one": that is a refinement, confirmed by the accountant. If it does, note it as noise.
