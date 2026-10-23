"""Typed, versioned thresholds loaded from YAML (ED-009). Bad config fails at startup."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "thresholds.yaml"

Prob = float


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Band(_Strict):
    flag_at: Prob = Field(ge=0, le=1)
    review_low: Prob = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _order(self) -> "Band":
        if self.review_low > self.flag_at:
            raise ValueError("review_low must be <= flag_at")
        return self


class YesNo(_Strict):
    yes_at: Prob = Field(ge=0, le=1)
    no_at: Prob = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _order(self) -> "YesNo":
        if self.no_at > self.yes_at:
            raise ValueError("no_at must be <= yes_at")
        return self


class Safety(_Strict):
    sea_sh: Band
    reprisal_risk: Band
    threat_to_life: Band


class ProjectTh(_Strict):
    match: Prob = Field(ge=0, le=1)
    runner_up_max: Prob = Field(ge=0, le=1)
    none_max: Prob = Field(ge=0, le=1)


class UrgencyTh(_Strict):
    min_confidence: Prob = Field(ge=0, le=1)


class Robustness(_Strict):
    injection_review: Prob = Field(ge=0, le=1)
    coherent_min: Prob = Field(ge=0, le=1)
    english_min: Prob = Field(ge=0, le=1)
    min_chars: int = Field(ge=0)
    min_alpha_ratio: float = Field(ge=0, le=1)
    max_chars: int = Field(gt=0)


class Thresholds(_Strict):
    version: str
    policy_version: str
    model: str
    safety: Safety
    confidentiality_requested: Band
    issue: YesNo
    harm_alleged: YesNo
    project: ProjectTh
    urgency: UrgencyTh
    robustness: Robustness


def load_thresholds(path: str | Path | None = None) -> Thresholds:
    data = yaml.safe_load(Path(path or DEFAULT_PATH).read_text(encoding="utf-8"))
    return Thresholds.model_validate(data)
