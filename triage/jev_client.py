"""Thin Jev client: pinned model, explicit 429/529 retry, record/replay cache (ED-002, ED-012, ED-013, ED-015).

Retries are done here rather than by the SDK so that the number of attempts and the
statuses seen end up in the audit block.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from typesafe_sdk import (
    AsyncTypeSafeClient,
    RetryPolicy,
    TypeSafeAPIConnectionError,
    TypeSafeAPIError,
    TypeSafeError,
)

CacheMode = Literal["off", "live", "record", "replay"]
RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504, 529})
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / ".jev_cache"


class JevUnavailable(Exception):
    """Jev could not answer after all retries; the pipeline fails safe to human review."""

    def __init__(self, reason: str, attempts: int, statuses: list[int | str]):
        super().__init__(f"{reason} after {attempts} attempt(s): {statuses}")
        self.reason = reason
        self.attempts = attempts
        self.statuses = statuses


@dataclass
class JevResult:
    model: str
    answers: dict[str, Any]
    input_tokens: int
    output_tokens: int
    latency_ms: int
    attempts: int = 1
    statuses: list[int | str] = field(default_factory=list)
    cache_hit: bool = False


@dataclass
class RetryConfig:
    max_attempts: int = 5
    backoff_initial: float = 0.5
    backoff_max: float = 8.0
    timeout_s: float = 30.0


def cache_key(model: str, state: Any, questions: dict[str, Any]) -> str:
    blob = json.dumps({"model": model, "state": state, "questions": questions}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class JevClient:
    def __init__(
        self,
        model: str,
        *,
        cache_mode: CacheMode = "live",
        cache_dir: Path = DEFAULT_CACHE_DIR,
        retry: RetryConfig | None = None,
        max_concurrency: int = 8,
    ):
        self.model = model
        self.cache_mode = cache_mode
        self.cache_dir = Path(cache_dir)
        self.retry = retry or RetryConfig()
        self._sem = asyncio.Semaphore(max_concurrency)
        self._client: AsyncTypeSafeClient | None = None

    async def __aenter__(self) -> "JevClient":
        if self.cache_mode != "replay":
            if not os.environ.get("TYPESAFE_API_KEY"):
                raise RuntimeError("TYPESAFE_API_KEY is not set (use --cache replay to run offline from the cache)")
            self._client = AsyncTypeSafeClient(
                model=self.model,
                retry=RetryPolicy(max_retries=0),  # we retry ourselves to record attempts
                timeout=self.retry.timeout_s,
            )
            await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client is not None:
            await self._client.__aexit__(*exc)

    # ------------------------------------------------------------ cache

    def _path(self, key: str) -> Path:
        return self.cache_dir / key[:2] / f"{key}.json"

    def _load(self, key: str) -> dict[str, Any] | None:
        p = self._path(key)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def _save(self, key: str, payload: dict[str, Any]) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    # ------------------------------------------------------------ call

    async def ask(self, state: Any, questions: dict[str, Any]) -> JevResult:
        key = cache_key(self.model, state, questions)
        if self.cache_mode in ("live", "replay", "record"):
            cached = self._load(key) if self.cache_mode != "record" else None
            if cached is not None:
                return JevResult(**{**cached, "cache_hit": True})
            if self.cache_mode == "replay":
                raise JevUnavailable("cache_miss_in_replay", 0, [])

        result = await self._call_with_retry(state, questions)
        if self.cache_mode in ("live", "record"):
            payload = {k: v for k, v in result.__dict__.items() if k != "cache_hit"}
            self._save(key, payload)
        return result

    async def _call_with_retry(self, state: Any, questions: dict[str, Any]) -> JevResult:
        assert self._client is not None
        statuses: list[int | str] = []
        start = time.perf_counter()
        for attempt in range(1, self.retry.max_attempts + 1):
            retry_after: float | None = None
            try:
                async with self._sem:
                    resp = await self._client.system_one(state=state, questions=questions, model=self.model)
                return JevResult(
                    model=resp.model,
                    answers={k: v.model_dump(mode="json") for k, v in resp.answers.items()},
                    input_tokens=resp.usage.input_tokens if resp.usage else 0,
                    output_tokens=resp.usage.output_tokens if resp.usage else 0,
                    latency_ms=int((time.perf_counter() - start) * 1000),
                    attempts=attempt,
                    statuses=statuses + [200],
                )
            except TypeSafeAPIError as e:
                statuses.append(e.status)
                if e.status not in RETRYABLE_STATUSES:
                    raise JevUnavailable(f"jev_http_{e.status}", attempt, statuses) from e
                retry_after = _retry_after_seconds(e)
            except TypeSafeAPIConnectionError as e:  # includes timeouts
                statuses.append(type(e).__name__)
            except TypeSafeError as e:
                statuses.append(type(e).__name__)
                raise JevUnavailable("jev_error", attempt, statuses) from e

            if attempt < self.retry.max_attempts:
                backoff = min(self.retry.backoff_max, self.retry.backoff_initial * 2 ** (attempt - 1))
                delay = retry_after if retry_after is not None else backoff * (1 + random.uniform(-0.25, 0.25))
                await asyncio.sleep(min(delay, self.retry.backoff_max))
        raise JevUnavailable("jev_unavailable", self.retry.max_attempts, statuses)


def _retry_after_seconds(e: TypeSafeAPIError) -> float | None:
    try:
        v = e.headers.get("retry-after") if e.headers is not None else None
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
