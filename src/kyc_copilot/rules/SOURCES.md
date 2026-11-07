# Bounce reason sources: verification trail

Checked 8 Nov 2026 against the texts below. Public sources only.

| Reason | Claim in `bounce_reasons.yaml` | Read in | Result |
|---|---|---|---|
| BR-ID-DOB | AMLR Art. 22(1)(a)(ii): place and full date of birth | EUR-Lex, Regulation (EU) 2024/1624, HTML text (`CELEX:32024R1624`) | Verified. Paragraph corrected from 22(1)(a) to 22(1)(a)(ii). |
| BR-DOC-ID-MISSING | AMLR Art. 22(6)(a): identity document, passport or equivalent | Same | Verified. 22(6)(b) also allows eID; the PoC does not model it. |
| BR-DOC-ID-EXPIRED | An expired ID makes the file bounce | AMLR Art. 22 and 26 (same); draft AMLA RTS on CDD, Art. 6, as parsed on springlex.eu (draft 2) | **Not stated in law.** AMLR asks for an identity document and up-to-date data (Art. 26(2)); the draft RTS Art. 6(1) asks that the document show its expiry date. Neither says an expired document is refused. Kept as a bounce on common practice; to confirm with practitioners. Draft RTS wording may change. |
| BR-TAX-RESIDENCE-DIFFERS | CRS Section IV(A): confirm reasonableness of self-certification against AML/KYC information | OECD CRS text as published in South African Notice R. 6886 of 2025 (acts.co.za). OECD's own PDF not read. | Verified on a faithful copy. Earlier ref said "Commentary on Section IV"; corrected to the Standard's Section IV(A). |
| BR-EDD-LARGE-FUNDING | EBA risk factor guidelines, wealth management: very high-value transactions; AMLR Art. 34(5) | EBA/GL/2021/02 consolidated (amended by EBA/GL/2023/03), PDF from eba.europa.eu; AMLR on EUR-Lex | **Corrected twice.** Wealth management is Guideline 12 (para. 12.4), not 9. The EUR 5M line is **not** purely a demo choice: AMLR Art. 34(5) uses EUR 5M (handled) together with EUR 50M (total assets) for higher-risk relationships. The PoC flags on the EUR 5M part only. |

| BR-EDD-PEP | AMLR Art. 42(1) EDD for PEPs incl. source of wealth and funds; Art. 46 family and close associates | AMLR on EUR-Lex | Verified (8 Nov 2026). |
| BR-EDD-HIGH-RISK-COUNTRY | Annex III (3)(a): FATF increased monitoring is a higher-risk factor; Art. 34(3) | AMLR on EUR-Lex; FATF list of 30 Oct 2026 via assessment-legal.com and a search summary of fatf-gafi.org, fincrimecentral.com and others | Annex III verified. **List verified second-hand:** fatf-gafi.org returns 403 to automated access. 18 under increased monitoring incl. Virgin Islands (UK); call for action Iran, DPRK, Myanmar. Re-check by hand before a public demo. The EU's own list (Art. 29 delegated act) is not yet used. |
| BR-EDD-ASSET-VEHICLE | Annex III (1)(c): personal asset-holding vehicles | AMLR on EUR-Lex | Factor verified. **Inferred:** treating every client foundation or trust as one is a PoC simplification. Liechtenstein itself is not on any high-risk list, so a Liechtenstein-foundation case rests on this factor. |
| BR-EDD-SOW-UNCORROBORATED | Art. 34(4)(c) source of wealth in EDD; Art. 34(5) EUR 5M | AMLR on EUR-Lex | Articles verified. Which document corroborates which event type is a PoC choice. |

What would change a result: the final AMLA RTS text in the Official Journal (expiry), or the OECD's own CRS PDF disagreeing with the South African copy.
