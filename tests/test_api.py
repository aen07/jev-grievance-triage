"""API tests, offline: TRIAGE_CACHE=replay serves recorded Jev answers from .jev_cache (no key needed)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def client():
    mp = pytest.MonkeyPatch()
    mp.setenv("TRIAGE_CACHE", "replay")
    from api.main import app

    with TestClient(app) as c:
        yield c
    mp.undo()


def sample(i: int) -> dict:
    return json.loads((ROOT / "samples" / f"test{i}.json").read_text(encoding="utf-8"))


def test_health_reports_versions(client):
    h = client.get("/health").json()
    assert h["jev_ready"] and h["model_pinned"] == "jev-1.13.0" and h["n_questions"] == 23


def test_brief_samples_via_api(client):
    outs = client.post("/triage/batch", json=[sample(1), sample(2), sample(3)]).json()
    assert [(o["route_to"], o["action"]) for o in outs] == [
        ("safeguards_environment", "auto_route"),
        ("sea_specialist", "human_review"),  # non-negotiable
        ("grs_general", "human_review"),
    ]
    assert outs[1]["audit"]["model"] == "jev-1.13.0"


def test_invalid_input_is_reviewed_not_rejected(client):
    r = client.post("/triage", json={"grievance_id": "X", "received_at": "nope", "channel": "fax"})
    assert r.status_code == 200 and r.json()["action"] == "human_review" and "invalid_input" in r.json()["review_reasons"]


def test_batch_limit(client):
    assert client.post("/triage/batch", json=[sample(1)] * 201).status_code == 413
