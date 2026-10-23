# Eval results: th-2026-10-22.3

Run at 2026-10-22T23:34:25+00:00. Model(s): {'jev-1.13.0': 33, None: 1}. Cases: 34 (3 brief samples + 31 own).

## Accuracy per field

| field | accuracy | n |
|---|---|---|
| eligibility.status | 0.97 | 32 |
| eligibility.project_id | 0.96 | 26 |
| issues | 0.96 | 25 |
| flags | 0.97 | 31 |
| urgency | 0.96 | 23 |
| route_to | 0.96 | 28 |
| also_notify | 0.94 | 18 |
| redact_identity | 1.00 | 20 |
| action | 0.90 | 30 |
| eligibility.reasons | 1.00 | 4 |
| review_reasons | 1.00 | 5 |

All labelled fields correct: **0.85** of cases.

## Safety and confidentiality flags

| flag | precision | recall | tp | fp | fn |
|---|---|---|---|---|---|
| sea_sh | 1.00 | 1.00 | 5 | 0 | 0 |
| reprisal_risk | 0.80 | 1.00 | 4 | 1 | 0 |
| threat_to_life | 1.00 | 1.00 | 4 | 0 | 0 |
| confidentiality_requested | 1.00 | 1.00 | 3 | 0 | 0 |

Missed safety cases (expected safety flag, but auto-routed): **0** []

## Issue labels (cases with exact labels)

| issue | precision | recall | tp | fp | fn |
|---|---|---|---|---|---|
| environment_pollution | 1.00 | 1.00 | 2 | 0 | 0 |
| land_resettlement | 1.00 | 1.00 | 3 | 0 | 0 |
| labor_conditions | 1.00 | 1.00 | 3 | 0 | 0 |
| community_health_safety | 0.50 | 1.00 | 1 | 1 | 0 |
| sea_sh | 1.00 | 1.00 | 2 | 0 | 0 |
| fraud_corruption | 1.00 | 1.00 | 2 | 0 | 0 |
| information_request | 1.00 | 1.00 | 3 | 0 | 0 |
| other | 1.00 | 1.00 | 1 | 0 | 0 |

## Human review

Share sent to human review: **0.76**

- Over-review: 3 of 9 cases labelled auto_route were sent to review anyway
- Under-review (labelled human_review but auto-routed): **0** []

| review reason | count |
|---|---|
| safety_reprisal_risk | 8 |
| eligibility_ineligible | 7 |
| safety_sea_sh | 5 |
| safety_threat_to_life | 5 |
| uncertain_issue_fraud_corruption | 3 |
| uncertain_urgency | 2 |
| eligibility_undetermined | 2 |
| possible_injection | 2 |
| non_english_input | 2 |
| unreadable_input | 2 |
| uncertain_project | 1 |
| uncertain_issue_community_health_safety | 1 |
| uncertain_issue_land_resettlement | 1 |

## Latency and cost

- Jev latency per grievance (one request): p50 391 ms, p95 571 ms
- Input tokens per grievance: mean 2784, max 2936
- Cost per grievance: $0.000117 (input tokens x $0.042/Mtok; output free)

## Threshold sweep (+/-0.1, replayed from cache)

| variant | review rate | missed safety | sea_sh R | reprisal R | threat R | all-fields acc |
|---|---|---|---|---|---|---|
| baseline | 0.76 | 0 | 1.00 | 1.00 | 1.00 | 0.85 |
| safety -0.1 | 0.82 | 0 | 1.00 | 1.00 | 1.00 | 0.85 |
| safety +0.1 | 0.76 | 0 | 1.00 | 1.00 | 1.00 | 0.88 |
| routine -0.1 | 0.76 | 0 | 1.00 | 1.00 | 1.00 | 0.85 |
| routine +0.1 | 0.74 | 0 | 1.00 | 1.00 | 1.00 | 0.82 |

## Failing cases

| case | failed fields | tags |
|---|---|---|
| T-002 | action | routine, fraud |
| T-004 | urgency, action | routine, labor, closed_in_window |
| T-006 | eligibility.status, eligibility.project_id, route_to, also_notify, action | mixed_info_and_complaint, land |
| T-015 | flags | safety, sea_sh, euphemism |
| T-020 | issues | negation |
