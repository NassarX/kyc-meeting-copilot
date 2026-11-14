# Scorecard: pipeline `model:claude-opus-5-5`, 1 case(s)

Versions: taxonomy tax-v0.2, bounce_reasons br-v0.2, extractor extract-prompt-v0.2/claude-opus-5-5/medium+plausibility-v0.2, transcript noisy

| Metric | Value |
|---|---|
| precision | 0.86 |
| recall | 0.86 |
| critical_precision | 0.77 |
| critical_recall | 0.77 |
| silent_wrong_critical | 3 |
| span_rejections | 0 |
| missing_provenance | 0 |
| contradiction_recall | n/a |
| bounce_recall | 1.00 |
| bounce_false_fires | 0 |
| privacy_leaks | 0 |
| false_warnings | 0 |
| supersession_recall | n/a |

| Case | P | R | crit R | silent wrong | span rej | contra R | bounce R | missed | false fires | privacy leaks | false warn |
|---|---|---|---|---|---|---|---|---|---|---|---|
| D01 | 0.86 | 0.86 | 0.77 | 3 | 0 | n/a | 1.00 | - | - | 0 | 0 |

## Cost: extract-prompt-v0.2/claude-opus-5-5/medium+plausibility-v0.2

Calls: 1 (0 from cache). Spent: **$0.0664** of $0.50 cap.

| Case | Attempt | In | Out | Cache read | Cache write | USD | Cached |
|---|---|---|---|---|---|---|---|
| D01 | first | 1330 | 3032 | 2356 | 0 | 0.0664 | no |
