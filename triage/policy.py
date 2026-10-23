"""Policy rules P1-P8 as pure functions of (Jev probabilities, preprocessing, thresholds).

No I/O and no model calls here: every field can be traced to a probability, a threshold and a rule.
Review reason codes are stable strings, documented in README.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .preprocess import Preprocessed
from .questions import ISSUE_QUESTIONS, PROJECT_QUESTIONS, project_qid
from .registry import BY_ID, REGISTRY, within_filing_window
from .schema import ISSUES, Issue, Unit
from .thresholds import Band, Thresholds, YesNo

URGENCY_LEVELS = ("routine", "priority", "urgent", "immediate")
SAFETY_FLAGS = ("sea_sh", "reprisal_risk", "threat_to_life")


@dataclass
class Decision:
    eligibility_status: str
    project_id: str | None
    eligibility_reasons: list[str]
    issues: list[Issue]
    flags: dict[str, bool]
    urgency: str
    route_to: Unit
    also_notify: list[Unit]
    redact_identity: bool
    action: str
    review_reasons: list[str]
    derived: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------- answer readers

def noul_p(answers: dict[str, Any], qid: str) -> float:
    return float(answers[qid]["noul"])


def yes_no(p: float, band: YesNo) -> str:
    if p >= band.yes_at:
        return "yes"
    if p <= band.no_at:
        return "no"
    return "uncertain"


def flag_state(p: float, band: Band) -> str:
    if p >= band.flag_at:
        return "on"
    if p >= band.review_low:
        return "uncertain"
    return "off"


# ---------------------------------------------------------------- P1 eligibility

def decide_project(answers: dict[str, Any], th: Thresholds) -> tuple[str, str | None, dict[str, float]]:
    """Returns (outcome, project_id, probs); outcome in {"match", "none", "ambiguous"}."""
    probs = {p.project_id: noul_p(answers, project_qid(p.project_id)) for p in REGISTRY}
    ranked = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
    (top_id, top_p), (_, second_p) = ranked[0], ranked[1]
    if top_p >= th.project.match and second_p <= th.project.runner_up_max:
        return "match", top_id, probs
    if top_p <= th.project.none_max:
        return "none", None, probs
    return "ambiguous", None, probs


def decide_eligibility(
    answers: dict[str, Any], received_at: date, th: Thresholds, reasons: list[str], derived: dict[str, Any]
) -> tuple[str, str | None, list[str]]:
    outcome, project_id, probs = decide_project(answers, th)
    harm = yes_no(noul_p(answers, "harm_alleged"), th.harm_alleged)
    asks_info = yes_no(noul_p(answers, "issue_information_request"), th.issue)
    derived.update(project_outcome=outcome, project_probs=probs, harm_alleged=harm, asks_info=asks_info)

    if harm == "uncertain":
        reasons.append("uncertain_harm_alleged")

    # P1: requests information AND alleges no harm -> not_applicable (info desk). Combined in code (ED-027).
    if asks_info == "yes" and harm == "no":
        return "not_applicable", project_id, []

    if outcome == "ambiguous":
        reasons.append("uncertain_project")
        return "undetermined", None, []

    elig_reasons: list[str] = []
    if outcome == "none":
        elig_reasons.append("no_matching_project")
    if harm == "no":
        elig_reasons.append("no_harm_alleged")
    if project_id is not None:
        project = BY_ID[project_id]
        in_window = within_filing_window(project, received_at)
        derived["filing_window_ok"] = in_window
        if not in_window:
            elig_reasons.append("outside_filing_window")
    return ("ineligible" if elig_reasons else "eligible"), project_id, elig_reasons


# ---------------------------------------------------------------- P2 issues, P3 flags

def decide_flags(answers: dict[str, Any], th: Thresholds, reasons: list[str], derived: dict[str, Any]) -> tuple[dict[str, bool], bool]:
    raw = {
        "sea_sh": noul_p(answers, "issue_sea_sh"),
        "reprisal_risk": max(noul_p(answers, "flag_reprisal_feared"), noul_p(answers, "flag_reprisal_occurred")),
        "threat_to_life": max(noul_p(answers, "flag_threat_to_life"), noul_p(answers, "flag_violent_threat")),
    }
    flags: dict[str, bool] = {}
    for name in SAFETY_FLAGS:
        state = flag_state(raw[name], getattr(th.safety, name))
        flags[name] = state == "on"
        if state == "uncertain":
            reasons.append(f"uncertain_{name}")

    conf_state = flag_state(noul_p(answers, "flag_confidentiality_requested"), th.confidentiality_requested)
    flags["confidentiality_requested"] = conf_state == "on"
    # Protective default: an uncertain confidentiality request redacts, but does not by itself force review.
    protective_redact = conf_state == "uncertain"
    derived.update(flag_probs=raw, confidentiality_state=conf_state)
    return flags, protective_redact


def decide_issues(
    answers: dict[str, Any], flags: dict[str, bool], status: str, th: Thresholds, reasons: list[str]
) -> list[Issue]:
    found: list[Issue] = []
    for issue in ISSUES:
        if issue == "other":
            continue
        if issue == "sea_sh":  # same question as the flag, same (safety) threshold, so they never disagree
            if flags["sea_sh"]:
                found.append(issue)
            continue
        state = yes_no(noul_p(answers, f"issue_{issue}"), th.issue)
        if state == "yes":
            found.append(issue)
        elif state == "uncertain":
            reasons.append(f"uncertain_issue_{issue}")
    substantive = [i for i in found if i != "information_request"]
    if not substantive and status != "not_applicable":
        found.append("other")
    return found


# ---------------------------------------------------------------- P4 urgency

def decide_urgency(answers: dict[str, Any], flags: dict[str, bool], th: Thresholds, reasons: list[str], derived: dict[str, Any]) -> str:
    ans = answers["urgency"]
    probs = {int(k): float(v) for k, v in ans["probabilities"].items()}
    base = max(probs, key=probs.get)
    if float(ans.get("confidence", 0.0)) < th.urgency.min_confidence:
        reasons.append("uncertain_urgency")
        # conservative: the more severe of the two most likely levels (ED-029)
        top2 = sorted(probs, key=probs.get, reverse=True)[:2]
        base = max(top2)
    level = base
    if flags["sea_sh"] or flags["reprisal_risk"]:
        level = max(level, URGENCY_LEVELS.index("urgent"))
    if flags["threat_to_life"]:
        level = URGENCY_LEVELS.index("immediate")
    derived.update(urgency_base=URGENCY_LEVELS[base], urgency_after_floors=URGENCY_LEVELS[level])
    return URGENCY_LEVELS[level]


# ---------------------------------------------------------------- P5 routing

def decide_routing(status: str, issues: list[Issue], flags: dict[str, bool]) -> tuple[Unit, list[Unit]]:
    iss = set(issues)
    only_info = status == "not_applicable" or iss == {"information_request"}
    table: list[tuple[bool, Unit]] = [
        (flags["threat_to_life"], "protection_unit"),
        (flags["sea_sh"], "sea_specialist"),
        (status in ("ineligible", "undetermined"), "grs_general"),
        ("fraud_corruption" in iss, "integrity_unit"),
        (bool(iss & {"environment_pollution", "community_health_safety"}), "safeguards_environment"),
        (bool(iss & {"land_resettlement", "labor_conditions"}), "safeguards_social"),
        (only_info, "info_access_desk"),
    ]
    applying: list[Unit] = []
    for cond, unit in table:
        if cond and unit not in applying:
            applying.append(unit)
    if not applying:
        applying.append("grs_general")  # row 8: anything else
    route_to, also = applying[0], applying[1:]
    if flags["reprisal_risk"] and route_to != "protection_unit" and "protection_unit" not in also:
        also.append("protection_unit")
    return route_to, also


# ---------------------------------------------------------------- P6/P7 and assembly

def decide(
    answers: dict[str, Any], pre: Preprocessed, received_at: date, th: Thresholds
) -> Decision:
    reasons: list[str] = []
    derived: dict[str, Any] = {}
    rb = th.robustness

    # robustness signals
    if pre.junk or noul_p(answers, "text_is_coherent") < rb.coherent_min:
        reasons.append("unreadable_input")
    if noul_p(answers, "is_english") < rb.english_min or pre.ascii_alpha_share < 0.6:
        reasons.append("non_english_input")
    if noul_p(answers, "contains_instructions_to_system") >= rb.injection_review:
        reasons.append("possible_injection")
    if pre.truncated:
        reasons.append("input_truncated")

    status, project_id, elig_reasons = decide_eligibility(answers, received_at, th, reasons, derived)
    flags, protective_redact = decide_flags(answers, th, reasons, derived)
    issues = decide_issues(answers, flags, status, th, reasons)
    urgency = decide_urgency(answers, flags, th, reasons, derived)
    route_to, also = decide_routing(status, issues, flags)

    # P6: mandatory review conditions
    for name in SAFETY_FLAGS:
        if flags[name]:
            reasons.append(f"safety_{name}")
    if status in ("ineligible", "undetermined"):
        reasons.append(f"eligibility_{status}")

    redact = flags["confidentiality_requested"] or flags["sea_sh"] or protective_redact  # P7
    reasons = list(dict.fromkeys(reasons))
    return Decision(
        eligibility_status=status,
        project_id=project_id,
        eligibility_reasons=elig_reasons,
        issues=issues,
        flags=flags,
        urgency=urgency,
        route_to=route_to,
        also_notify=also,
        redact_identity=redact,
        action="human_review" if reasons else "auto_route",
        review_reasons=reasons,
        derived=derived,
    )


def fail_safe(reason: str, extra_reasons: list[str] | None = None) -> Decision:
    """Used when Jev cannot answer or the input cannot be judged: never closes, always a person."""
    reasons = list(dict.fromkeys([reason, *(extra_reasons or []), "eligibility_undetermined"]))
    return Decision(
        eligibility_status="undetermined",
        project_id=None,
        eligibility_reasons=[],
        issues=[],
        flags={"sea_sh": False, "reprisal_risk": False, "threat_to_life": False, "confidentiality_requested": False},
        urgency="priority",
        route_to="grs_general",
        also_notify=[],
        redact_identity=True,  # we could not check for a confidentiality request, so protect by default
        action="human_review",
        review_reasons=reasons,
        derived={"fail_safe": reason},
    )


# Sanity: question ids used above exist in questions.py
assert all(f"issue_{i}" in ISSUE_QUESTIONS for i in ISSUES if i != "other")
assert len(PROJECT_QUESTIONS) == len(REGISTRY)
