"""Policy tests with synthetic Jev answers: no API key needed.

These check the code side of the boundary (P1-P8, thresholds, fail-safes), not Jev itself.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, get_args

import pytest

from triage.jev_client import JevResult, JevUnavailable
from triage.pipeline import triage_one
from triage.policy import decide, decide_routing, fail_safe
from triage.preprocess import preprocess
from triage.questions import QUESTIONS, project_qid
from triage.registry import BY_ID, within_filing_window
from triage.schema import Action
from triage.thresholds import load_thresholds

TH = load_thresholds()


def answers(**overrides: float) -> dict[str, Any]:
    """All nouls 0.02 (clear no), urgency clearly routine, coherent English; override by question id."""
    a: dict[str, Any] = {}
    for qid, q in QUESTIONS.items():
        if q["type"] == "noul":
            a[qid] = {"type": "noul", "noul": 0.02}
    a["text_is_coherent"]["noul"] = 0.98
    a["is_english"]["noul"] = 0.99
    a["harm_alleged"]["noul"] = 0.95
    a["urgency"] = {"type": "score", "score": 0.0, "confidence": 0.9,
                    "probabilities": {"0": 0.95, "1": 0.05, "2": 0.0, "3": 0.0}}
    for k, v in overrides.items():
        if k == "urgency_level":
            probs = {str(i): (0.95 if i == v else 0.05 / 3) for i in range(4)}
            a["urgency"] = {"type": "score", "score": float(v), "confidence": 0.9, "probabilities": probs}
        else:
            a[k]["noul"] = v
    return a


PRE = preprocess("A perfectly normal complaint text about a project.", TH.robustness)


def run(ans: dict[str, Any], received: date = date(2026, 10, 6)):
    return decide(ans, PRE, received, TH)


# ------------------------------------------------------------- the three brief samples, as answer shapes

def test_sample1_routine_auto_route():
    d = run(answers(**{project_qid("P-1041"): 0.97, "issue_environment_pollution": 0.96,
                       "issue_community_health_safety": 0.9, "urgency_level": 1}))
    assert d.eligibility_status == "eligible" and d.project_id == "P-1041"
    assert d.issues == ["environment_pollution", "community_health_safety"]
    assert not any(d.flags.values())
    assert d.urgency == "priority"
    assert (d.route_to, d.also_notify) == ("safeguards_environment", [])
    assert d.redact_identity is False and d.action == "auto_route" and d.review_reasons == []


def test_sample2_sea_reprisal_goes_to_sea_specialist_and_review():
    d = run(answers(**{project_qid("P-1187"): 0.95, "issue_labor_conditions": 0.97, "issue_sea_sh": 0.93,
                       "flag_reprisal_feared": 0.9, "flag_confidentiality_requested": 0.96, "urgency_level": 2}),
            received=date(2026, 10, 14))
    assert d.route_to == "sea_specialist"
    assert {"safeguards_social", "protection_unit"} <= set(d.also_notify)
    assert d.flags == {"sea_sh": True, "reprisal_risk": True, "threat_to_life": False, "confidentiality_requested": True}
    assert set(d.issues) == {"labor_conditions", "sea_sh"}
    assert d.urgency == "urgent" and d.redact_identity and d.action == "human_review"


def test_sample3_outside_filing_window():
    d = run(answers(**{project_qid("P-0932"): 0.96, "issue_community_health_safety": 0.9, "urgency_level": 1}),
            received=date(2026, 10, 5))
    assert d.eligibility_status == "ineligible" and d.project_id == "P-0932"
    assert "outside_filing_window" in d.eligibility_reasons
    assert d.route_to == "grs_general" and "safeguards_environment" in d.also_notify
    assert d.action == "human_review"


# ------------------------------------------------------------- P1

def test_filing_window_boundaries():
    p = BY_ID["P-1055"]  # closed 2025-09-30 -> window to 2027-09-30
    assert within_filing_window(p, date(2027, 9, 30))
    assert not within_filing_window(p, date(2027, 10, 1))
    assert not within_filing_window(BY_ID["P-0932"], date(2024, 4, 1))
    assert within_filing_window(BY_ID["P-0932"], date(2024, 3, 31))


def test_ambiguous_project_is_undetermined():
    d = run(answers(**{project_qid("P-1041"): 0.8, project_qid("P-1210"): 0.6}))
    assert d.eligibility_status == "undetermined" and d.project_id is None
    assert "uncertain_project" in d.review_reasons and d.action == "human_review"


def test_no_project_is_ineligible_no_matching_project():
    d = run(answers())
    assert d.eligibility_status == "ineligible" and d.eligibility_reasons == ["no_matching_project"]
    assert d.route_to == "grs_general"


def test_info_only_is_not_applicable_and_goes_to_info_desk():
    d = run(answers(**{project_qid("P-1302"): 0.9, "harm_alleged": 0.03, "issue_information_request": 0.97}))
    assert d.eligibility_status == "not_applicable"
    assert d.issues == ["information_request"]
    assert d.route_to == "info_access_desk" and d.action == "auto_route"


def test_no_harm_is_ineligible():
    d = run(answers(**{project_qid("P-1041"): 0.95, "harm_alleged": 0.05}))
    assert d.eligibility_status == "ineligible" and "no_harm_alleged" in d.eligibility_reasons


# ------------------------------------------------------------- P3/P4/P5/P7 safety

def test_threat_to_life_routes_to_protection_immediate():
    d = run(answers(**{project_qid("P-1041"): 0.95, "flag_threat_to_life": 0.8, "issue_community_health_safety": 0.9}))
    assert d.route_to == "protection_unit" and d.urgency == "immediate" and d.action == "human_review"


def test_violent_threat_counts_as_threat_to_life():
    d = run(answers(**{project_qid("P-1041"): 0.95, "flag_violent_threat": 0.85}))
    assert d.flags["threat_to_life"] and d.urgency == "immediate"


def test_reprisal_adds_protection_unit_and_urgent_floor():
    d = run(answers(**{project_qid("P-1041"): 0.95, "issue_land_resettlement": 0.9, "flag_reprisal_occurred": 0.7}))
    assert d.route_to == "safeguards_social" and "protection_unit" in d.also_notify
    assert d.urgency == "urgent"


def test_uncertain_safety_forces_review_without_setting_flag():
    d = run(answers(**{project_qid("P-1041"): 0.95, "issue_environment_pollution": 0.9, "issue_sea_sh": 0.3}))
    assert d.flags["sea_sh"] is False and "uncertain_sea_sh" in d.review_reasons and d.action == "human_review"


def test_sea_sh_issue_and_flag_never_disagree():
    d = run(answers(**{project_qid("P-1041"): 0.95, "issue_sea_sh": 0.55}))
    assert d.flags["sea_sh"] and "sea_sh" in d.issues and d.redact_identity


def test_uncertain_confidentiality_redacts_protectively():
    d = run(answers(**{project_qid("P-1041"): 0.95, "issue_environment_pollution": 0.9,
                       "flag_confidentiality_requested": 0.4}))
    assert d.flags["confidentiality_requested"] is False and d.redact_identity is True


def test_routing_order_and_fallback():
    flags = {"sea_sh": False, "reprisal_risk": False, "threat_to_life": False, "confidentiality_requested": False}
    assert decide_routing("eligible", ["fraud_corruption", "environment_pollution"], flags) == (
        "integrity_unit", ["safeguards_environment"])
    assert decide_routing("eligible", ["other"], flags) == ("grs_general", [])


# ------------------------------------------------------------- P6 thresholds and robustness

def test_uncertain_issue_goes_to_review():
    d = run(answers(**{project_qid("P-1041"): 0.95, "issue_environment_pollution": 0.5}))
    assert "uncertain_issue_environment_pollution" in d.review_reasons and d.action == "human_review"


def test_non_english_and_injection_and_unreadable_force_review():
    assert "non_english_input" in run(answers(is_english=0.1)).review_reasons
    assert "possible_injection" in run(answers(contains_instructions_to_system=0.8)).review_reasons
    assert "unreadable_input" in run(answers(text_is_coherent=0.2)).review_reasons


def test_low_urgency_confidence_rounds_up_and_reviews():
    a = answers(**{project_qid("P-1041"): 0.95, "issue_environment_pollution": 0.9})
    a["urgency"] = {"type": "score", "score": 0.6, "confidence": 0.3,
                    "probabilities": {"0": 0.45, "1": 0.4, "2": 0.15, "3": 0.0}}
    d = run(a)
    assert d.urgency == "priority" and "uncertain_urgency" in d.review_reasons


def test_low_urgency_confidence_takes_higher_of_top_two_only():
    a = answers(**{project_qid("P-1210"): 0.95, "issue_fraud_corruption": 0.95})
    a["urgency"] = {"type": "score", "score": 0.93, "confidence": 0.39,
                    "probabilities": {"0": 0.34, "1": 0.39, "2": 0.27, "3": 0.0}}  # real T-002 answer, run 1
    assert run(a).urgency == "priority"


def test_fail_safe_never_closes():
    d = fail_safe("jev_unavailable")
    assert d.action == "human_review" and d.route_to == "grs_general" and d.redact_identity


def test_action_type_cannot_express_close_or_reject():
    assert set(get_args(Action)) == {"auto_route", "human_review"}


# ------------------------------------------------------------- pipeline fail-safes (no network)

class _FakeClient:
    def __init__(self, result=None, exc=None):
        self.result, self.exc = result, exc

    async def ask(self, state, questions):
        if self.exc:
            raise self.exc
        return self.result


@pytest.mark.parametrize("raw,reason", [
    ({"grievance_id": "X", "received_at": "2026-10-01", "channel": "web_form", "text": "   "}, "unreadable_input"),
    ({"grievance_id": "X", "received_at": "not-a-date", "channel": "web_form", "text": "hello there world"}, "invalid_input"),
    ({"grievance_id": "X", "received_at": "2026-10-01", "channel": "fax", "text": "hello there world"}, "invalid_input"),
])
def test_bad_input_goes_to_review(raw, reason):
    out = asyncio.run(triage_one(raw, _FakeClient(), TH))
    assert out.action == "human_review" and reason in out.review_reasons


def test_jev_down_goes_to_review_with_attempts_in_audit():
    raw = {"grievance_id": "X", "received_at": "2026-10-01", "channel": "web_form", "text": "The road works flood my field."}
    out = asyncio.run(triage_one(raw, _FakeClient(exc=JevUnavailable("jev_unavailable", 5, [529, 529, 429, 529, 529])), TH))
    assert out.action == "human_review" and "jev_unavailable" in out.review_reasons
    assert out.audit.jev_attempts == 5 and out.audit.jev_statuses[0] == 529


def test_audit_block_has_p8_fields():
    raw = {"grievance_id": "X", "received_at": "2026-10-06", "channel": "web_form", "text": "Dust from the Tamsa road works."}
    res = JevResult(model="jev-1.13.0", answers=answers(**{project_qid("P-1041"): 0.95, "issue_environment_pollution": 0.9}),
                    input_tokens=1234, output_tokens=50, latency_ms=321)
    out = asyncio.run(triage_one(raw, _FakeClient(result=res), TH))
    a = out.audit
    assert a.model == "jev-1.13.0" and a.policy_version and a.thresholds_version and a.thresholds
    assert a.jev_answers and a.input_tokens == 1234 and a.latency_ms == 321 and a.review_reasons == out.review_reasons
