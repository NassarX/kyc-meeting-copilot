# Scorecard: pipeline `model:claude-opus-5-5`, 6 case(s)

Versions: taxonomy tax-v0.2, bounce_reasons br-v0.2, extractor extract-prompt-v0.2/claude-opus-5-5/medium+plausibility-v0.2

| Metric | Value |
|---|---|
| precision | 0.96 |
| recall | 0.98 |
| critical_precision | 0.98 |
| critical_recall | 0.98 |
| silent_wrong_critical | 1 |
| span_rejections | 0 |
| missing_provenance | 0 |
| contradiction_recall | n/a |
| bounce_recall | 1.00 |
| bounce_false_fires | 1 |
| privacy_leaks | 0 |
| false_warnings | 7 |
| supersession_recall | 1.00 |

| Case | P | R | crit R | silent wrong | span rej | contra R | bounce R | missed | false fires | privacy leaks | false warn |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C01 | 1.00 | 0.96 | 0.92 | 0 | 0 | n/a | 1.00 | - | - | 0 | 0 |
| D01 | 1.00 | 1.00 | 1.00 | 0 | 0 | n/a | 1.00 | - | - | 0 | 0 |
| D02 | 0.84 | 0.95 | 0.92 | 1 | 0 | n/a | 1.00 | - | - | 0 | 1 |
| D03 | 0.97 | 0.97 | 1.00 | 0 | 0 | n/a | 1.00 | - | - | 0 | 1 |
| D04 | 1.00 | 1.00 | 1.00 | 0 | 0 | n/a | 1.00 | - | - | 0 | 4 |
| D05 | 0.96 | 1.00 | 1.00 | 0 | 0 | n/a | 1.00 | - | BR-EDD-PEP | 0 | 1 |

## Silent wrong values (check each: a real error, or wording the grader is strict about)

| Case | Field | Subject | Extracted | Expected |
|---|---|---|---|---|
| D02 | pep.family_public_function | pep/1 | Sister Agnieszka Kowalczyk, Deputy Minister of Infrastructure, Poland (appointed last year) | sister, deputy minister of infrastructure |

## Cost: extract-prompt-v0.2/claude-opus-5-5/medium+plausibility-v0.2

Calls: 6 (0 from cache). Spent: **$0.4697** of $1.00 cap.

| Case | Attempt | In | Out | Cache read | Cache write | USD | Cached |
|---|---|---|---|---|---|---|---|
| C01 | first | 618 | 3009 | 2356 | 0 | 0.0631 | no |
| D01 | first | 1331 | 2946 | 2356 | 0 | 0.0647 | no |
| D02 | first | 1550 | 3897 | 2356 | 0 | 0.0846 | no |
| D03 | first | 1589 | 4804 | 2356 | 0 | 0.1029 | no |
| D04 | first | 1258 | 3295 | 2356 | 0 | 0.0714 | no |
| D05 | first | 1622 | 3797 | 2356 | 0 | 0.0829 | no |
