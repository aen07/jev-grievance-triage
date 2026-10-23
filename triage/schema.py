"""Pydantic models for input, output and audit (ED-008).

The output shape follows the brief exactly; fields may be added, never removed or renamed.
`action` is a Literal of the two allowed values, so no code path can emit close/reject.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Channel = Literal["web_form", "email", "hotline_transcript", "letter_ocr"]
EligibilityStatus = Literal["eligible", "ineligible", "undetermined", "not_applicable"]
Urgency = Literal["routine", "priority", "urgent", "immediate"]
Action = Literal["auto_route", "human_review"]
Unit = Literal[
    "protection_unit",
    "sea_specialist",
    "grs_general",
    "integrity_unit",
    "safeguards_environment",
    "safeguards_social",
    "info_access_desk",
]
Issue = Literal[
    "environment_pollution",
    "land_resettlement",
    "labor_conditions",
    "community_health_safety",
    "sea_sh",
    "fraud_corruption",
    "information_request",
    "other",
]

ISSUES: tuple[Issue, ...] = (
    "environment_pollution",
    "land_resettlement",
    "labor_conditions",
    "community_health_safety",
    "sea_sh",
    "fraud_corruption",
    "information_request",
    "other",
)


class GrievanceIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    grievance_id: str = Field(min_length=1)
    received_at: date
    channel: Channel
    text: str = ""


class Eligibility(BaseModel):
    status: EligibilityStatus
    project_id: str | None = None
    reasons: list[str] = Field(default_factory=list)


class Flags(BaseModel):
    sea_sh: bool = False
    reprisal_risk: bool = False
    threat_to_life: bool = False
    confidentiality_requested: bool = False


class Audit(BaseModel):
    model: str | None
    model_requested: str
    policy_version: str
    thresholds_version: str
    thresholds: dict[str, Any]
    jev_answers: dict[str, Any]
    review_reasons: list[str]
    latency_ms: int
    input_tokens: int
    output_tokens: int = 0
    questions_version: str = ""
    jev_attempts: int = 0
    jev_statuses: list[int | str] = Field(default_factory=list)
    cache_hit: bool = False
    derived: dict[str, Any] = Field(default_factory=dict)
    preprocess: dict[str, Any] = Field(default_factory=dict)


class TriageOut(BaseModel):
    grievance_id: str
    eligibility: Eligibility
    issues: list[Issue]
    flags: Flags
    urgency: Urgency
    route_to: Unit
    also_notify: list[Unit]
    redact_identity: bool
    action: Action
    review_reasons: list[str]
    audit: Audit
    llm_outputs: dict[str, Any] | None = None
