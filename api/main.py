"""HTTP API over the triage pipeline (ED-034). Thin layer: no policy logic lives here.

Run:  uvicorn api.main:app --port 8000
Env:  TYPESAFE_API_KEY (or .env), TRIAGE_CACHE=live|replay|off|record (default live)
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from pydantic import BaseModel

from triage.env import load_env
from triage.jev_client import JevClient
from triage.llm import add_llm_outputs
from triage.pipeline import triage_many, triage_one
from triage.questions import QUESTIONS, QUESTIONS_VERSION
from triage.registry import REGISTRY, filing_deadline
from triage.schema import TriageOut
from triage.thresholds import Thresholds, load_thresholds

ROOT = Path(__file__).resolve().parent.parent
TESTSET = ROOT / "data" / "testset.jsonl"
MAX_BATCH = 200


class Health(BaseModel):
    status: str
    jev_ready: bool
    error: str | None = None
    model_pinned: str
    cache_mode: str
    policy_version: str
    thresholds_version: str
    questions_version: str
    n_questions: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_env()
    app.state.th = load_thresholds()
    app.state.cache_mode = os.environ.get("TRIAGE_CACHE", "live")
    app.state.client = None
    app.state.error = None
    client = JevClient(app.state.th.model, cache_mode=app.state.cache_mode)
    try:
        await client.__aenter__()
        app.state.client = client
    except RuntimeError as e:  # missing key: start anyway so /health can say why
        app.state.error = str(e)
    yield
    if app.state.client is not None:
        await app.state.client.__aexit__(None, None, None)


app = FastAPI(
    title="MDB grievance triage (Jev)",
    version="0.1.0",
    description="One grievance in, one auditable triage decision out. Jev answers typed questions; code applies P1-P8.",
    lifespan=lifespan,
)


def _client() -> JevClient:
    if app.state.client is None:
        raise HTTPException(503, detail=f"Jev client not ready: {app.state.error}")
    return app.state.client


def _th() -> Thresholds:
    return app.state.th


@app.get("/health", response_model=Health)
async def health() -> Health:
    th = _th()
    return Health(
        status="ok" if app.state.client else "degraded",
        jev_ready=app.state.client is not None,
        error=app.state.error,
        model_pinned=th.model,
        cache_mode=app.state.cache_mode,
        policy_version=th.policy_version,
        thresholds_version=th.version,
        questions_version=QUESTIONS_VERSION,
        n_questions=len(QUESTIONS),
    )


@app.post("/triage", response_model=TriageOut, response_model_exclude_none=False)
async def triage(
    grievance: dict[str, Any] = Body(..., examples=[{
        "grievance_id": "G-2026-00401", "received_at": "2026-10-06", "channel": "web_form",
        "text": "Since August the quarry trucks for the Northern Corridor road works drive past our village school in Tamsa...",
    }]),
    with_llm: bool = Query(False, description="Add the labelled post-decision LLM letter / reviewer summary"),
) -> TriageOut:
    """Triage one grievance. Invalid input is not rejected: it comes back as human_review with reason invalid_input."""
    out = await triage_one(grievance, _client(), _th())
    if with_llm:
        out = await add_llm_outputs(out, str(grievance.get("text", "")))
    return out


@app.post("/triage/batch", response_model=list[TriageOut])
async def triage_batch(grievances: list[dict[str, Any]] = Body(...)) -> list[TriageOut]:
    if len(grievances) > MAX_BATCH:
        raise HTTPException(413, detail=f"at most {MAX_BATCH} grievances per request")
    return await triage_many(grievances, _client(), _th())


@app.get("/config")
async def config() -> dict[str, Any]:
    th = _th()
    return {
        "thresholds": th.model_dump(),
        "questions_version": QUESTIONS_VERSION,
        "registry": [
            {"project_id": p.project_id, "name": p.name, "country": p.country, "location": p.location,
             "status": p.status, "closing_date": p.closing_date.isoformat(), "filing_deadline": filing_deadline(p).isoformat()}
            for p in REGISTRY
        ],
    }


@app.get("/questions")
async def questions() -> dict[str, Any]:
    """The exact Jev questions sent with every grievance."""
    return {"questions_version": QUESTIONS_VERSION, "questions": QUESTIONS}


@app.post("/admin/reload-thresholds")
async def reload_thresholds() -> dict[str, str]:
    """Re-read config/thresholds.yaml without a restart (for a live threshold change). Invalid YAML is refused."""
    try:
        app.state.th = load_thresholds()
    except Exception as e:
        raise HTTPException(400, detail=f"thresholds not reloaded, keeping {app.state.th.version}: {e}") from e
    return {"thresholds_version": app.state.th.version, "policy_version": app.state.th.policy_version}


@app.get("/samples")
async def samples() -> list[dict[str, Any]]:
    """Labelled test cases (input + expected) for the UI."""
    return [json.loads(line) for line in TESTSET.read_text(encoding="utf-8").splitlines() if line.strip()]
