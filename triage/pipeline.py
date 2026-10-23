"""Orchestration: validate -> preprocess -> one Jev call -> policy -> typed output with audit (P8)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from pydantic import ValidationError

from .jev_client import JevClient, JevResult, JevUnavailable
from .policy import Decision, decide, fail_safe
from .preprocess import Preprocessed, preprocess
from .questions import QUESTIONS, QUESTIONS_VERSION, build_state
from .schema import Audit, Eligibility, Flags, GrievanceIn, TriageOut
from .thresholds import Thresholds


def _to_output(
    gid: str, d: Decision, th: Thresholds, *, jev: JevResult | None, pre: Preprocessed | None,
    latency_ms: int, jev_failure: JevUnavailable | None = None,
) -> TriageOut:
    audit = Audit(
        model=jev.model if jev else None,
        model_requested=th.model,
        policy_version=th.policy_version,
        thresholds_version=th.version,
        thresholds=th.model_dump(exclude={"version", "policy_version", "model"}),
        jev_answers=jev.answers if jev else {},
        review_reasons=d.review_reasons,
        latency_ms=latency_ms,
        input_tokens=jev.input_tokens if jev else 0,
        output_tokens=jev.output_tokens if jev else 0,
        questions_version=QUESTIONS_VERSION,
        jev_attempts=jev.attempts if jev else (jev_failure.attempts if jev_failure else 0),
        jev_statuses=jev.statuses if jev else (jev_failure.statuses if jev_failure else []),
        cache_hit=jev.cache_hit if jev else False,
        derived=d.derived,
        preprocess=pre.as_audit() if pre else {},
    )
    return TriageOut(
        grievance_id=gid,
        eligibility=Eligibility(status=d.eligibility_status, project_id=d.project_id, reasons=d.eligibility_reasons),
        issues=d.issues,
        flags=Flags(**d.flags),
        urgency=d.urgency,
        route_to=d.route_to,
        also_notify=d.also_notify,
        redact_identity=d.redact_identity,
        action=d.action,
        review_reasons=d.review_reasons,
        audit=audit,
    )


async def triage_one(raw: dict[str, Any], client: JevClient, th: Thresholds) -> TriageOut:
    start = time.perf_counter()
    elapsed = lambda: int((time.perf_counter() - start) * 1000)  # noqa: E731

    try:
        g = GrievanceIn.model_validate(raw)
    except ValidationError as e:
        gid = str(raw.get("grievance_id") or "UNKNOWN") if isinstance(raw, dict) else "UNKNOWN"
        d = fail_safe("invalid_input")
        d.derived["validation_errors"] = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
        return _to_output(gid, d, th, jev=None, pre=None, latency_ms=elapsed())

    pre = preprocess(g.text, th.robustness)
    if pre.empty:  # nothing for Jev to judge
        return _to_output(g.grievance_id, fail_safe("unreadable_input"), th, jev=None, pre=pre, latency_ms=elapsed())

    try:
        jev = await client.ask(build_state(pre.text_for_jev, g.channel), QUESTIONS)
    except JevUnavailable as e:
        return _to_output(g.grievance_id, fail_safe(e.reason), th, jev=None, pre=pre, latency_ms=elapsed(), jev_failure=e)

    d = decide(jev.answers, pre, g.received_at, th)
    # latency_ms is the live Jev round trip (kept when replayed from cache, see audit.cache_hit)
    return _to_output(g.grievance_id, d, th, jev=jev, pre=pre, latency_ms=jev.latency_ms)


async def triage_many(rows: list[dict[str, Any]], client: JevClient, th: Thresholds) -> list[TriageOut]:
    return list(await asyncio.gather(*(triage_one(r, client, th) for r in rows)))
