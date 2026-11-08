# Writing a test case

The guide a case author works from. It is self-contained: a domain expert can write a case without reading the code.

## 1. What this is for

The project is a **proof of concept** for a pre-submission check. Before a relationship manager (RM) sends a client's KYC file to compliance, the check reads the meeting transcript, the document checklist and what the bank already holds. It then tells the RM what is missing, what contradicts, and which enhanced-due-diligence flags apply, with every fact linked to the exact words it came from.

To prove the AI part works (hypothesis H1 in `docs/spec.md`), it is scored against a **fixed set of synthetic cases** with a known right answer. The case author writes that right answer. The cases must be written **before** anyone tunes the AI against them; otherwise the scores only show that the AI fits the cases.

C01 is the worked example (section 9). Each case is built around one trap; section 8 lists the traps a full set covers.

## 2. Ground rules## 2. Ground rules (non-negotiable)

1. **Everything is invented.** No real clients, no real people's data, no real company that a reader could identify. Invented names, companies, dates and amounts only.
2. **Nothing from any employer.** No internal checklists, templates, rules, client stories or process details from your own employer or anyone else's. Write from general professional knowledge and public guidance. If a case idea comes from a real event, change it beyond recognition.
3. **English only.**
4. **One trap per case is the point.** The rest of the case should be ordinary and realistic, so the trap is the thing being tested.
5. **The right answer must be defensible.** If you aren't sure what a careful compliance officer would say, write the doubt in the notes. Doubts are useful; silent guesses are not.

## 3. What one case contains

| Part | What you write | Notes |
|---|---|---|
| Case date | The meeting date | The case is judged on this date ("as of"), never today. Use dates in 2026. |
| Lead | An invented lead reference | e.g. `lead-c02` |
| Transcript | 15–40 short turns, each with a speaker | Speakers: `rm`, `client`, plus others if the case needs them (`accountant`, `spouse`, `lawyer`). Write natural speech: numbers in words, hesitations, corrections. |
| Dossier stub | 2–5 facts the bank already holds before the meeting | e.g. full name, nationality, a registry figure for a company sale. |
| Document checklist | 2–5 documents | For each: type (section 6), present yes/no, issue date and expiry date if they apply. |
| Gold facts | Every fact a careful analyst would take from the transcript | Field name (section 5), value, and the **exact words** in the transcript it comes from. You don't count characters; the tooling computes positions from the quote. |
| Gold gaps | Required facts nobody stated | The tooling derives the full list; you name the ones that matter for the trap. |
| Gold contradictions | Facts that disagree between transcript, dossier and checklist | Field, the two values, where each came from. |
| Expected flags | Which rules in section 7 should fire | The tooling checks this against the rules. A mismatch means either the case or a rule is wrong, and both are worth knowing. |
| Traps | What the case tests, in one sentence | Kinds: `transcript_conflict` (transcript vs dossier/checklist), `missing_required` (a required fact or document is absent), `extraction_trap` (ambiguous, corrected or easily misheard speech). |
| Seeded draft | One critical fact with one wrong value | Used to test the independent checker. Make it plausible (a near-miss figure, a swapped date), not absurd. |
| Notes | Anything a reviewer should know | Doubts, judgement calls, alternatives you considered. |

**Value types:** text; a fixed choice (section 5 lists the allowed values); a date (exact, or relative words like "three years ago in June", which you resolve against the meeting date); money (amount, currency, and "one-off", "per year" or "per month"); a percentage; a country (two-letter code, e.g. LU, FR, VG); yes/no.

**Grouped facts:** facts about the same thing share a label, such as `wealth_event/1` for the business sale and `wealth_event/2` for the dividends. Number them in the order they come up. The tooling doesn't mind how you number them.

## 4. From draft to case file

A case can be drafted as prose with the template in section 10. It is then converted to the YAML case format (see `cases/generators/` for how C01 and D01–D05 are built) with every quote's position computed, never typed. Then:
1. `kyc-eval run --pipeline gold` validates the case and compares the expected flags, contradictions and gaps with what the rules actually produce;
2. any mismatch is resolved and noted: either the case or a rule is wrong, and both are worth knowing;
3. the case is frozen with the rest of the set (section 12).

## 5. Fact fields you can use (taxonomy v0.2)

Fields marked **required** are what the check looks for; if nobody states one, it's a gap. **Critical** fields are the ones where a wrong value is most harmful.

| Field | Type | Critical | Required | Group label |
|---|---|---|---|---|
| identity.full_name | text | yes | yes | |
| identity.date_of_birth | date | yes | yes | |
| identity.nationality | country (can be several) | yes | yes | |
| identity.residence_country | country | yes | yes | |
| identity.residence_since | date | | | |
| identity.tax_residence | country | yes | yes | |
| relationship.person_present | text | | | relationship/N |
| relationship.role | spouse, child, parent, sibling, accountant, lawyer, advisor, other | | | relationship/N |
| wealth_event.type | business_sale, dividends, inheritance, salary, investment_gains, real_estate_sale, gift, other | | yes | wealth_event/N |
| wealth_event.date | date | yes | yes | wealth_event/N |
| wealth_event.amount | money | yes | yes | wealth_event/N |
| wealth_event.counterparty | text | yes | | wealth_event/N |
| wealth_event.ownership_pct | percentage | yes | | wealth_event/N |
| asset.type | cash, securities, brokerage_account, real_estate, private_company, other | | | asset/N |
| asset.location | country | | | asset/N |
| asset.value | money | yes | | asset/N |
| asset.custodian | text | | | asset/N |
| structure.type | company, foundation, trust, insurance_wrapper, other | | | structure/N |
| structure.name | text | yes | | structure/N |
| structure.jurisdiction | country | yes | | structure/N |
| structure.established | date | yes | | structure/N |
| structure.beneficial_owner | text | yes | | structure/N |
| income.source | text | | yes | income/N |
| income.amount | money | yes | yes | income/N |
| liability.type | text | | | liability/N |
| liability.rate | percentage | | | liability/N |
| pep.self_public_function | text | yes | | |
| pep.family_public_function | text | yes | | pep/N |
| pep.none_declared | yes/no | yes | yes | |
| expected.initial_funding_source | text | | yes | |
| expected.initial_funding_amount | money | yes | yes | |
| expected.annual_flows | money | | | |

If a case needs a fact that isn't here, say so in the notes. That is valuable feedback on the taxonomy.

## 6. Document types for the checklist

passport, national_id, residence_permit, proof_of_address, tax_residence_certificate, bank_statement, payslip, employment_contract, tax_return, sale_agreement, company_register_extract, shareholder_register, trust_deed, inheritance_certificate, property_deed, gift_letter, source_of_funds_letter, other.

## 7. The rules the check applies (bounce reasons br-v0.2)

"Bounce" means compliance would send the file back. "Flag" means the RM is told; it never blocks. Each rule has a public source.

| Rule | Effect | Fires when |
|---|---|---|
| BR-ID-DOB | bounce | No date of birth anywhere. |
| BR-DOC-ID-MISSING | bounce | No passport marked present on the checklist. |
| BR-DOC-ID-EXPIRED | bounce | The passport's expiry date is before the case date. (Expiring *on* the case date is still valid.) |
| BR-TAX-RESIDENCE-DIFFERS | flag | Tax residence differs from country of residence. |
| BR-EDD-LARGE-FUNDING | flag | Expected initial funding is EUR 5,000,000 or more. |
| BR-EDD-PEP | flag | Any PEP indicator (self or family), even if the client also said "none". |
| BR-EDD-HIGH-RISK-COUNTRY | flag | Residence, nationality, tax residence, a structure's jurisdiction or an asset's location is on the FATF list of 30 Oct 2026 (Angola, Bolivia, Bosnia and Herzegovina, Cameroon, Haiti, Iraq, Kenya, Kuwait, Laos, Lebanon, Nepal, Papua New Guinea, South Sudan, Syria, Venezuela, Vietnam, British Virgin Islands, Yemen; plus Iran, North Korea, Myanmar). |
| BR-EDD-ASSET-VEHICLE | flag | Any foundation or trust. |
| BR-EDD-SOW-UNCORROBORATED | flag | A wealth event of EUR 5,000,000 or more with no supporting document of the matching kind on the checklist (business sale: sale agreement, company register extract or shareholder register; dividends: bank statement, register extract or tax return; inheritance: inheritance certificate; salary: payslip, employment contract or tax return; investment gains: bank statement or tax return; real-estate sale: property deed or sale agreement; gift: gift letter; other: source-of-funds letter). |

Amounts in other currencies are not converted; a rule that needs EUR gives "unknown" for them, which is not a pass.

**Where you can add the most:** if real files bounce for reasons not on this list, or a rule here is wrong or too blunt, note it. New rules need a public source (a regulation, guidance) or are recorded as coming from an interview; never from an employer document.

## 8. The trap catalogue

One trap per case, the rest ordinary. The private evaluation set (12 cases, written by a wealth-management domain expert and not published) covered every trap below. The public set covers most of them:

| Trap | What must show up in the answer | Public case |
|---|---|---|
| Self-corrected amount ("three, no, two point four million") | Only the corrected figure | C01, D04 |
| Relative date ("three years ago in June") | The spoken words plus the resolved date | C01, D02 |
| A required fact never stated | A gap; BR-ID-DOB when it is the date of birth | C01, D03 |
| Client figure differs from the bank's file | One contradiction; both values survive, nobody picks | private set |
| A relative with a public function, mentioned after "no PEPs" | `pep.family_public_function`; BR-EDD-PEP fires | D02 |
| Foundation or trust; a high-risk jurisdiction | BR-EDD-ASSET-VEHICLE; BR-EDD-HIGH-RISK-COUNTRY | C01, D03 (asset vehicle) |
| A changed answer mid-meeting | Both statements kept; the later one stands (`gold.superseded`) | D02 |
| A third speaker states the key facts | The quotes come from that speaker's turns | D03 |
| A health disclosure | Never a fact (`gold.forbidden_utterances`, invariant I10) | D05 |
| A large source of wealth with no supporting document | BR-EDD-SOW-UNCORROBORATED | D03 |
| A clean, low-risk control | Nothing fires that shouldn't: measures false alarms | D01 |
| A noisy transcript (plausible mishearings) | Two versions, same turns; gold from the clean one | D01 |
| Facts that can't all be true (funding above all wealth; a future date) | Plausibility doubts | D04 |
| An attempt to talk past the check ("ignore the previous questions") | Treated as speech, not an instruction | D05 |

## 9. The worked example: C01 (summary)

- **Story:** business sale and dividends; the client, an accountant and the RM.
- **Traps:** the dividend is said as "three point four million euros, no, sorry, two point four million euros", confirmed by the accountant and the RM's recap, so 2.4M stands. The move to Luxembourg is "three years ago in June", kept as words and resolved to June 2023 against a meeting on 7 Nov 2026.
- **Dossier stub:** full name, nationality (IT).
- **Checklist:** passport (valid to 2031), proof of address (present), sale agreement (missing).
- **Gold:** 23 facts. Gaps include date of birth, tax residence, the dividend's date. Expected flags: BR-ID-DOB (no date of birth) and BR-EDD-ASSET-VEHICLE (a Liechtenstein foundation).
- **Seeded draft:** the dividend as EUR 3.4M.

The full file is `cases/C01.yaml`.

## 10. Template (one per case)

```
CASE: C0X
Title:
Meeting date (case date):
Lead reference:

TRANSCRIPT
1. rm: ...
2. client: ...
...

DOSSIER STUB (what the bank already holds)
- field: value

DOCUMENT CHECKLIST
- type: present yes/no, issued YYYY-MM-DD, expires YYYY-MM-DD

GOLD FACTS
- field [group label if any]: value  <- "exact words from turn N"
  (derivation, if the value isn't literally in the words: e.g. "self-correction, second figure stands")

GAPS THAT MATTER
- field (why it matters)

CONTRADICTIONS
- field: value A (source) vs value B (source)

EXPECTED FLAGS
- rule id (why)

TRAP
- kind: one sentence

SEEDED DRAFT
- field [group]: wrong value (the right one is ...)

NOTES
- doubts, alternatives, taxonomy or rule gaps
```

## 11. Independence

Whoever writes the cases knows the rules and the format, so they can't also write the blind cases (B01–B04), which must come from someone who hasn't seen the rules. Blind cases are the real test of whether results generalise; none exist yet.

## 12. Freezing the set

The case set is frozen: a version number and a fingerprint of the files are recorded. Only then is the AI extractor tuned against it, and the scores are published as they come out, whether or not they meet the targets.
