# D01 clean: what the check should catch

The note the meeting was written from. The scored answer is `cases/D01.yaml`; where they differ, the case file is the reference.

Meeting date: 2026-11-09. Client: Ingrid Solveig Halvorsen-Matos. RM and client only.

## Test points
1. Baseline: every required fact is said once, clearly. Nothing should look wrong.
2. Residence and tax residence are the same country, so no tax mismatch flag.
3. Funding (EUR 1.2M) is well under the stated sources, so no funding doubt.

## Facts it should find (* = critical)
- identity.full_name*: Ingrid Solveig Halvorsen-Matos
- identity.date_of_birth*: 1984-03-14
- identity.nationality*: NO
- identity.residence_country*: LU; identity.residence_since: 2016-09
- identity.tax_residence*: LU
- wealth_event/1: type inheritance; date* 2019-04; amount* EUR 1,800,000; counterparty* the estate via the notary practice Lindqvist and Aamodt (fictional) is acceptable, or none
- asset/1: cash and bond funds, value* EUR 1,600,000, at "my current bank" (no name)
- income/1: source salary, director of engineering at Veltrona Systems; amount* EUR 210,000 per year (a bonus of about EUR 20,000 may appear as a second income or be left out)
- pep.none_declared*: true
- expected.initial_funding_amount*: EUR 1,200,000; expected.initial_funding_source: inheritance money at current bank
- expected.annual_flows: EUR 60,000 per year

## Flags expected
- BR-DOC-ID-MISSING only. It fires on every pasted transcript because a paste has no document checklist (the passport is only promised). Not a finding about this client.
- BR-DOC-ID-EXPIRED: unknown (no passport on file), not fired.
- Must not fire: BR-TAX-RESIDENCE-DIFFERS, BR-EDD-PEP, BR-EDD-LARGE-FUNDING (1.2M is under EUR 5M), BR-EDD-SOW-UNCORROBORATED, BR-EDD-HIGH-RISK-COUNTRY, BR-EDD-ASSET-VEHICLE, BR-ID-DOB.

## Gaps
- None. If a "salary" wealth_event shows up with no date, that is a stray gap from the extractor, not from the transcript.

## Doubts
- None.

## Must not
- No contradictions. No facts about the parents or brother beyond the PEP denial.
