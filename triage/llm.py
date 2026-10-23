"""Optional post-decision LLM layer (ED-010).

Runs only AFTER TriageOut is final. Its output is stored under `llm_outputs`, labelled
`llm_generated: true`, and is never read back by the pipeline. If the key or package is
missing, it is skipped and triage is unaffected.
"""

from __future__ import annotations

import os
from typing import Any

from .schema import TriageOut

LLM_MODEL = "claude-haiku-4-5"

ACK_PROMPT = """You draft a short, plain-language acknowledgment letter from the Meridian Development Bank grievance office \
to a person who filed a grievance. Rules:
- Thank them, confirm receipt and the reference number, and state the response time: {deadline}.
- Do not promise any outcome. Do not mention internal units, routing, scores, flags or AI.
- {identity_rule}
- If they raised fear of retaliation, say retaliation is not tolerated and how to contact the office confidentially.
- Max 120 words. No placeholders other than the reference number given.

Reference: {gid}
Grievance (for context only, do not quote it back):
<<<
{text}
>>>"""

REVIEW_PROMPT = """Summarise this grievance for a human reviewer in at most 3 bullet points, in English. \
If it is not in English, first give a faithful English translation (label it "Translation:"). \
Do not add judgments about eligibility, urgency or routing.
<<<
{text}
>>>"""

DEADLINES = {"routine": "within 30 days", "priority": "within 10 days", "urgent": "within 72 hours", "immediate": "within 24 hours"}


def _client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        return None
    return anthropic.AsyncAnthropic()


async def add_llm_outputs(out: TriageOut, text: str) -> TriageOut:
    client = _client()
    if client is None:
        out.llm_outputs = {"llm_generated": False, "skipped": "ANTHROPIC_API_KEY not set or anthropic not installed"}
        return out

    identity_rule = (
        "Do not use the complainant's name or any identifying detail."
        if out.redact_identity else "Address them neutrally (no name is needed)."
    )
    results: dict[str, Any] = {"llm_generated": True, "model": LLM_MODEL, "note": "Not used in the triage decision."}
    try:
        ack = await client.messages.create(
            model=LLM_MODEL, max_tokens=400,
            messages=[{"role": "user", "content": ACK_PROMPT.format(
                deadline=DEADLINES[out.urgency], identity_rule=identity_rule, gid=out.grievance_id, text=text)}],
        )
        results["acknowledgment_letter"] = ack.content[0].text
        if out.action == "human_review":
            rev = await client.messages.create(
                model=LLM_MODEL, max_tokens=400,
                messages=[{"role": "user", "content": REVIEW_PROMPT.format(text=text)}],
            )
            results["reviewer_summary"] = rev.content[0].text
    except Exception as e:  # LLM failure must never affect triage
        results["error"] = f"{type(e).__name__}: {e}"
    out.llm_outputs = results
    return out
