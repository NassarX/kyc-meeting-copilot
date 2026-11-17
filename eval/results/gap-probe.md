# Gap probe: words Whisper invents in long gaps

17 Nov 2026. Synthetic speech (macOS `say`) of the 12 private case scripts (C01–C12), each with four 30-second gaps: digital silence, quiet pink, loud brown and faint white noise. A second copy has room noise throughout. Transcribed with local Whisper large-v3-turbo, using today's settings (`current`) and `hallucination_silence_threshold=2` (`hst2`). No API calls. Tool: `eval/tools/gap_probe.py`. Run it on the public cases with `build cases/D01.yaml OUT/D01`.

The transcripts stay with the private cases. In this run the noise was unseeded; the tool now seeds it. A first C01 run that invented the sentence "These numbers will pass down at home for $708" was overwritten and is not included.

```
| Case | Audio | Setting | Words in gaps | Script recall | Gap text |
|---|---|---|---|---|---|
| C01 | gapped | current | 15 | 0.731 | and the the the the the the the the the the the the the the |
| C01 | gapped | hst2 | 0 | 0.746 |  |
| C01 | gapped-noisy | current | 1 | 0.746 | A |
| C01 | gapped-noisy | hst2 | 0 | 0.746 |  |
| C02 | gapped | current | 0 | 0.938 |  |
| C02 | gapped | hst2 | 0 | 0.938 |  |
| C02 | gapped-noisy | current | 0 | 0.901 |  |
| C02 | gapped-noisy | hst2 | 0 | 0.901 |  |
| C03 | gapped | current | 0 | 0.921 |  |
| C03 | gapped | hst2 | 0 | 0.921 |  |
| C03 | gapped-noisy | current | 0 | 0.921 |  |
| C03 | gapped-noisy | hst2 | 0 | 0.921 |  |
| C04 | gapped | current | 0 | 0.916 |  |
| C04 | gapped | hst2 | 0 | 0.894 |  |
| C04 | gapped-noisy | current | 0 | 0.916 |  |
| C04 | gapped-noisy | hst2 | 0 | 0.916 |  |
| C05 | gapped | current | 0 | 0.872 |  |
| C05 | gapped | hst2 | 0 | 0.872 |  |
| C05 | gapped-noisy | current | 0 | 0.880 |  |
| C05 | gapped-noisy | hst2 | 0 | 0.860 |  |
| C06 | gapped | current | 4 | 0.911 | The Round 6 Terry |
| C06 | gapped | hst2 | 1 | 0.882 | The |
| C06 | gapped-noisy | current | 2 | 0.919 | The you. |
| C06 | gapped-noisy | hst2 | 2 | 0.919 | The you. |
| C07 | gapped | current | 1 | 0.839 | Peter |
| C07 | gapped | hst2 | 1 | 0.839 | Peter |
| C07 | gapped-noisy | current | 1 | 0.818 | Peter |
| C07 | gapped-noisy | hst2 | 1 | 0.818 | Peter |
| C08 | gapped | current | 0 | 0.925 |  |
| C08 | gapped | hst2 | 0 | 0.901 |  |
| C08 | gapped-noisy | current | 0 | 0.925 |  |
| C08 | gapped-noisy | hst2 | 0 | 0.896 |  |
| C09 | gapped | current | 1 | 0.910 | Guida |
| C09 | gapped | hst2 | 0 | 0.910 |  |
| C09 | gapped-noisy | current | 1 | 0.910 | you. |
| C09 | gapped-noisy | hst2 | 1 | 0.897 | you. |
| C10 | gapped | current | 0 | 0.913 |  |
| C10 | gapped | hst2 | 0 | 0.896 |  |
| C10 | gapped-noisy | current | 0 | 0.913 |  |
| C10 | gapped-noisy | hst2 | 0 | 0.902 |  |
| C11 | gapped | current | 0 | 0.876 |  |
| C11 | gapped | hst2 | 0 | 0.836 |  |
| C11 | gapped-noisy | current | 0 | 0.887 |  |
| C11 | gapped-noisy | hst2 | 0 | 0.847 |  |
| C12 | gapped | current | 0 | 0.901 |  |
| C12 | gapped | hst2 | 0 | 0.884 |  |
| C12 | gapped-noisy | current | 0 | 0.901 |  |
| C12 | gapped-noisy | hst2 | 0 | 0.884 |  |

current / gapped: words in gaps 21, cases with any 4/12, mean script recall 0.888

current / gapped-noisy: words in gaps 5, cases with any 4/12, mean script recall 0.886

hst2 / gapped: words in gaps 2, cases with any 2/12, mean script recall 0.877

hst2 / gapped-noisy: words in gaps 4, cases with any 3/12, mean script recall 0.876

Segments under today's settings: 22 invented (mostly inside a gap), 541 real.
- mean word probability < 0.6: catches 11/22 invented, flags 5/541 real
- mean word probability < 0.7: catches 14/22 invented, flags 12/541 real
- mean word probability < 0.75: catches 15/22 invented, flags 14/541 real
- mean word probability < 0.8: catches 16/22 invented, flags 23/541 real
- any word < 0.5 (the existing rule): catches 11/22 invented, touches 38/541 real

Invented segments:
- C01: "and" (mean 0.00, lowest word 0.00)
- C01: "the" (mean 0.07, lowest word 0.07)
- C01: "the" (mean 0.00, lowest word 0.00)
- C01: "the" (mean 0.04, lowest word 0.04)
- C01: "the" (mean 0.30, lowest word 0.30)
- C01: "the" (mean 0.51, lowest word 0.51)
- C01: "the" (mean 0.64, lowest word 0.64)
- C01: "the" (mean 0.73, lowest word 0.73)
- C01: "the" (mean 0.78, lowest word 0.78)
- C01: "the" (mean 0.82, lowest word 0.82)
- C01: "the" (mean 0.85, lowest word 0.85)
- C01: "the" (mean 0.87, lowest word 0.87)
- C01: "the" (mean 0.90, lowest word 0.90)
- C01: "the" (mean 0.93, lowest word 0.93)
- C01: "the" (mean 0.98, lowest word 0.98)
- C06: "Story Round 6" (mean 0.01, lowest word 0.00)
- C06: "Terry" (mean 0.00, lowest word 0.00)
- C06: "Thank you." (mean 0.56, lowest word 0.12)
- C07: "Peter Vandenberg" (mean 0.61, lowest word 0.37)
- C07: "Peter Vandenberg" (mean 0.68, lowest word 0.54)
- C09: "Guida" (mean 0.00, lowest word 0.00)
- C09: "Thank you." (mean 0.56, lowest word 0.12)
```
