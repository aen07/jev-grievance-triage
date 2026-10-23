# Eval results: th-2026-10-22.2

Run at 2026-10-22T23:31:05+00:00. Model(s): {'jev-1.13.0': 33, None: 1}. Cases: 34 (3 brief samples + 31 own).

## Accuracy per field

| field | accuracy | n |
|---|---|---|
| eligibility.status | 0.59 | 32 |
| eligibility.project_id | 0.50 | 26 |
| issues | 0.96 | 25 |
| flags | 0.97 | 31 |
| urgency | 0.96 | 23 |
| route_to | 0.82 | 28 |
| also_notify | 0.78 | 18 |
| redact_identity | 1.00 | 20 |
| action | 0.87 | 30 |
| eligibility.reasons | 1.00 | 4 |
| review_reasons | 1.00 | 5 |

All labelled fields correct: **0.56** of cases.

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

Share sent to human review: **0.79**

- Over-review: 4 of 9 cases labelled auto_route were sent to review anyway
- Under-review (labelled human_review but auto-routed): **0** []

| review reason | count |
|---|---|
| eligibility_undetermined | 15 |
| uncertain_project | 14 |
| safety_reprisal_risk | 8 |
| eligibility_ineligible | 6 |
| safety_sea_sh | 5 |
| safety_threat_to_life | 5 |
| uncertain_urgency | 4 |
| uncertain_issue_fraud_corruption | 3 |
| uncertain_issue_community_health_safety | 2 |
| possible_injection | 2 |
| non_english_input | 2 |
| unreadable_input | 2 |
| uncertain_issue_land_resettlement | 1 |

## Latency and cost

- Jev latency per grievance (one request): p50 376 ms, p95 609 ms
- Input tokens per grievance: mean 2803, max 2955
- Cost per grievance: $0.000118 (input tokens x $0.042/Mtok; output free)

## Threshold sweep (+/-0.1, replayed from cache)

| variant | review rate | missed safety | sea_sh R | reprisal R | threat R | all-fields acc |
|---|---|---|---|---|---|---|
| baseline | 0.79 | 0 | 1.00 | 1.00 | 1.00 | 0.56 |
| safety -0.1 | 0.85 | 0 | 1.00 | 1.00 | 1.00 | 0.56 |
| safety +0.1 | 0.79 | 0 | 1.00 | 1.00 | 1.00 | 0.59 |
| routine -0.1 | 0.79 | 0 | 1.00 | 1.00 | 1.00 | 0.71 |
| routine +0.1 | 0.82 | 0 | 1.00 | 1.00 | 1.00 | 0.44 |

## Failing cases

| case | failed fields | tags |
|---|---|---|
| G-2026-00433 | eligibility.status, eligibility.project_id | sample, safety, sea_sh, reprisal, multi_issue |
| T-002 | eligibility.status, eligibility.project_id, route_to, also_notify, action | routine, fraud |
| T-004 | eligibility.status, eligibility.project_id, urgency, route_to, also_notify, action | routine, labor, closed_in_window |
| T-005 | eligibility.status, eligibility.project_id, route_to, also_notify, action | fraud, land, multi_issue |
| T-006 | eligibility.status, eligibility.project_id, route_to, also_notify, action | mixed_info_and_complaint, land |
| T-014 | eligibility.status, eligibility.project_id | safety, threat_to_life, reprisal |
| T-015 | flags | safety, sea_sh, euphemism |
| T-016 | eligibility.status, eligibility.project_id | safety, sea_sh, community |
| T-017 | eligibility.status, eligibility.project_id | safety, reprisal_occurred |
| T-018 | eligibility.status, eligibility.project_id | safety, threat_to_life, health |
| T-019 | eligibility.status, eligibility.project_id | safety, threat_to_life, borderline |
| T-020 | issues | negation |
| T-022 | eligibility.status, eligibility.project_id | injection, sea_sh |
| T-024 | eligibility.status, eligibility.project_id, route_to | non_english |
| T-027 | eligibility.status, eligibility.project_id | long_input, buried_signal, reprisal |
