"""Deterministic input checks that run before Jev (ED-011, ED-012)."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .thresholds import Robustness


@dataclass
class Preprocessed:
    text_for_jev: str
    empty: bool
    alpha_ratio: float
    ascii_alpha_share: float
    junk: bool
    truncated: bool
    original_chars: int

    def as_audit(self) -> dict:
        d = asdict(self)
        d.pop("text_for_jev")
        return d


def preprocess(text: str | None, th: Robustness) -> Preprocessed:
    raw = (text or "").strip()
    n = len(raw)
    non_space = [c for c in raw if not c.isspace()]
    alpha = [c for c in non_space if c.isalpha()]
    alpha_ratio = len(alpha) / len(non_space) if non_space else 0.0
    ascii_alpha_share = sum(c.isascii() for c in alpha) / len(alpha) if alpha else 0.0

    empty = n < th.min_chars
    junk = (not empty) and alpha_ratio < th.min_alpha_ratio
    truncated = n > th.max_chars
    return Preprocessed(
        text_for_jev=raw[: th.max_chars],
        empty=empty,
        alpha_ratio=round(alpha_ratio, 3),
        ascii_alpha_share=round(ascii_alpha_share, 3),
        junk=junk,
        truncated=truncated,
        original_chars=n,
    )
