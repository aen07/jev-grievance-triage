# Eval results: th-2026-10-22.1

Run at 2026-10-22T23:29:14+00:00. Model(s): {'jev-1.13.0': 33, None: 1}. Cases: 34 (3 brief samples + 31 own).

## Accuracy per field

| field | accuracy | n |
|---|---|---|
| eligibility.status | 0.84 | 32 |
| eligibility.project_id | 0.88 | 26 |
| issues | 0.92 | 25 |
| flags | 0.87 | 31 |
| urgency | 0.87 | 23 |
| route_to | 0.79 | 28 |
| also_notify | 0.78 | 18 |
| redact_identity | 1.00 | 20 |
| action | 0.87 | 30 |
| eligibility.reasons | 1.00 | 4 |
| review_reasons | 1.00 | 5 |

All labelled fields correct: **0.65** of cases.

## Safety and confidentiality flags

| flag | precision | recall | tp | fp | fn |
|---|---|---|---|---|---|
| sea_sh | 1.00 | 1.00 | 5 | 0 | 0 |
| reprisal_risk | 0.80 | 1.00 | 4 | 1 | 0 |
| threat_to_life | 0.57 | 1.00 | 4 | 3 | 0 |
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
| other | 0.50 | 1.00 | 1 | 1 | 0 |

## Human review

Share sent to human review: **0.85**

| review reason | count |
|---|---|
| safety_threat_to_life | 9 |
| safety_reprisal_risk | 8 |
| eligibility_ineligible | 8 |
| uncertain_threat_to_life | 7 |
| safety_sea_sh | 5 |
| eligibility_undetermined | 5 |
| uncertain_project | 4 |
| uncertain_issue_fraud_corruption | 3 |
| uncertain_urgency | 2 |
| uncertain_issue_community_health_safety | 2 |
| possible_injection | 2 |
| non_english_input | 2 |
| unreadable_input | 2 |
| uncertain_info_request_only | 1 |
| uncertain_issue_land_resettlement | 1 |

## Latency and cost

- Jev latency per grievance (one request): p50 401 ms, p95 610 ms
- Input tokens per grievance: mean 2835, max 2987
- Cost per grievance: $0.000119 (input tokens x $0.042/Mtok; output free)

## Threshold sweep (+/-0.1, replayed from cache)

| variant | review rate | missed safety | sea_sh R | reprisal R | threat R | all-fields acc |
|---|---|---|---|---|---|---|
| baseline | 0.85 | 0 | 1.00 | 1.00 | 1.00 | 0.65 |
| safety -0.1 | 0.91 | 0 | 1.00 | 1.00 | 1.00 | 0.62 |
| safety +0.1 | 0.85 | 0 | 1.00 | 1.00 | 1.00 | 0.68 |
| routine -0.1 | 0.85 | 0 | 1.00 | 1.00 | 1.00 | 0.65 |
| routine +0.1 | 0.82 | 0 | 1.00 | 1.00 | 1.00 | 0.59 |

## Failing cases

| case | failed fields | tags |
|---|---|---|
| G-2026-00433 | flags, urgency, route_to, also_notify | sample, safety, sea_sh, reprisal, multi_issue |
| T-002 | urgency, action | routine, fraud |
| T-004 | flags, urgency, route_to, also_notify, action | routine, labor, closed_in_window |
| T-006 | eligibility.status, eligibility.project_id, route_to, also_notify, action | mixed_info_and_complaint, land |
| T-007 | eligibility.status, eligibility.project_id, action | other_issue |
| T-015 | flags | safety, sea_sh, euphemism |
| T-016 | flags, route_to | safety, sea_sh, community |
| T-020 | issues | negation |
| T-022 | eligibility.status, eligibility.project_id | injection, sea_sh |
| T-023 | eligibility.status, route_to | injection, info_only |
| T-027 | also_notify | long_input, buried_signal, reprisal |
| T-030 | eligibility.status, issues, route_to | info_only, frustrated |
