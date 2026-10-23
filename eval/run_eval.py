"""Evaluate the pipeline on data/testset.jsonl.

Prints and writes (eval/results/):
- accuracy per decision field (only over cases where that field is labelled)
- precision / recall per safety flag, and per issue label
- share of cases sent to human review, and missed safety cases
- latency and cost per grievance
- a +/-0.1 sweep of the main thresholds, replayed from the Jev cache (no extra API calls)

Usage:
  python -m eval.run_eval                 # live: calls Jev for anything not cached, records responses
  python -m eval.run_eval --cache replay  # fully offline from .jev_cache
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from triage.jev_client import JevClient
from triage.env import load_env
from triage.pipeline import triage_many
from triage.schema import ISSUES, TriageOut
from triage.thresholds import Thresholds, load_thresholds

ROOT = Path(__file__).resolve().parent.parent
TESTSET = ROOT / "data" / "testset.jsonl"
RESULTS = ROOT / "eval" / "results"
PRICE_PER_MTOK = 0.042  # USD, jev-1.13 input tokens; output tokens are free
SAFETY = ("sea_sh", "reprisal_risk", "threat_to_life")
FLAGS = (*SAFETY, "confidentiality_requested")


def load_cases() -> list[dict[str, Any]]:
    return [json.loads(l) for l in TESTSET.read_text(encoding="utf-8").splitlines() if l.strip()]


def _ok(expected: Any, actual: Any) -> bool:
    return actual in expected if isinstance(expected, list) else actual == expected


def field_checks(exp: dict[str, Any], out: TriageOut) -> dict[str, bool]:
    c: dict[str, bool] = {}
    if "status" in exp:
        c["eligibility.status"] = _ok(exp["status"], out.eligibility.status)
    if "project_id" in exp:
        c["eligibility.project_id"] = out.eligibility.project_id == exp["project_id"]
    if "reasons_include" in exp:
        c["eligibility.reasons"] = set(exp["reasons_include"]) <= set(out.eligibility.reasons)
    if "issues" in exp:
        c["issues"] = set(exp["issues"]) == set(out.issues)
    elif "issues_include" in exp:
        c["issues"] = set(exp["issues_include"]) <= set(out.issues)
    if "flags" in exp:
        got = out.flags.model_dump()
        c["flags"] = all(got[k] == v for k, v in exp["flags"].items())
    if "urgency" in exp:
        c["urgency"] = _ok(exp["urgency"], out.urgency)
    if "route_to" in exp:
        c["route_to"] = _ok(exp["route_to"], out.route_to)
    if "also_notify" in exp:
        c["also_notify"] = set(exp["also_notify"]) == set(out.also_notify)
    elif "also_notify_include" in exp:
        c["also_notify"] = set(exp["also_notify_include"]) <= set(out.also_notify)
    if "redact_identity" in exp:
        c["redact_identity"] = out.redact_identity == exp["redact_identity"]
    if "action" in exp:
        c["action"] = out.action == exp["action"]
    if "review_reasons_include" in exp:
        c["review_reasons"] = set(exp["review_reasons_include"]) <= set(out.review_reasons)
    return c


def prf(tp: int, fp: int, fn: int) -> tuple[float | None, float | None]:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    return p, r


def metrics(cases: list[dict[str, Any]], outs: list[TriageOut]) -> dict[str, Any]:
    per_field: dict[str, list[bool]] = {}
    failures: list[dict[str, Any]] = []
    flag_counts = {f: Counter() for f in FLAGS}
    issue_counts = {i: Counter() for i in ISSUES}
    missed_safety: list[str] = []

    for case, out in zip(cases, outs):
        exp = case["expected"]
        checks = field_checks(exp, out)
        for k, v in checks.items():
            per_field.setdefault(k, []).append(v)
        bad = [k for k, v in checks.items() if not v]
        if bad:
            failures.append({"id": out.grievance_id, "failed": bad, "tags": case["tags"]})

        got = out.flags.model_dump()
        for f, want in exp.get("flags", {}).items():
            key = ("tp" if got[f] else "fn") if want else ("fp" if got[f] else "tn")
            flag_counts[f][key] += 1
        if any(exp.get("flags", {}).get(f) for f in SAFETY) and out.action != "human_review":
            missed_safety.append(out.grievance_id)

        if "issues" in exp:  # exact labels only
            for i in ISSUES:
                want, have = i in exp["issues"], i in out.issues
                issue_counts[i]["tp" if want and have else "fn" if want else "fp" if have else "tn"] += 1

    lat = [o.audit.latency_ms for o in outs if o.audit.model]
    tok = [o.audit.input_tokens for o in outs if o.audit.model]
    return {
        "n": len(outs),
        "field_accuracy": {k: {"acc": sum(v) / len(v), "n": len(v)} for k, v in per_field.items()},
        "all_fields_correct": sum(1 for c, o in zip(cases, outs) if all(field_checks(c["expected"], o).values())) / len(outs),
        "flags": {f: dict(zip(("precision", "recall"), prf(c["tp"], c["fp"], c["fn"]))) | dict(c) for f, c in flag_counts.items()},
        "issues": {i: dict(zip(("precision", "recall"), prf(c["tp"], c["fp"], c["fn"]))) | dict(c) for i, c in issue_counts.items()},
        "human_review_rate": sum(o.action == "human_review" for o in outs) / len(outs),
        "over_review": {  # labelled auto_route, but sent to a person anyway (reviewer workload we could save)
            "n_expected_auto": (n_auto := sum(c["expected"].get("action") == "auto_route" for c in cases)),
            "sent_to_review": sum(c["expected"].get("action") == "auto_route" and o.action == "human_review" for c, o in zip(cases, outs)),
        },
        "under_review": [o.grievance_id for c, o in zip(cases, outs) if c["expected"].get("action") == "human_review" and o.action == "auto_route"],
        "missed_safety_cases": missed_safety,
        "review_reason_counts": dict(Counter(r for o in outs for r in o.review_reasons).most_common()),
        "latency_ms": {"p50": statistics.median(lat), "p95": sorted(lat)[max(0, int(len(lat) * 0.95) - 1)], "mean": statistics.mean(lat)} if lat else {},
        "input_tokens": {"mean": statistics.mean(tok), "max": max(tok)} if tok else {},
        "cost_usd_per_grievance": (statistics.mean(tok) * PRICE_PER_MTOK / 1e6) if tok else None,
        "models": dict(Counter(o.audit.model for o in outs)),
        "failures": failures,
    }


def shifted(th: Thresholds, target: str, delta: float) -> Thresholds:
    d = th.model_dump()
    clamp = lambda x: round(min(1.0, max(0.0, x + delta)), 3)  # noqa: E731
    if target == "safety":
        for f in SAFETY:
            d["safety"][f] = {k: clamp(v) for k, v in d["safety"][f].items()}
    elif target == "routine":
        for k in ("issue", "harm_alleged"):
            d[k] = {kk: clamp(v) for kk, v in d[k].items()}
        d["project"]["match"] = clamp(d["project"]["match"])
    d["version"] = f"{th.version}+{target}{delta:+.1f}"
    return Thresholds.model_validate(d)


async def run(th: Thresholds, cache: str, cases: list[dict[str, Any]]) -> list[TriageOut]:
    async with JevClient(th.model, cache_mode=cache) as client:
        return await triage_many([c["input"] for c in cases], client, th)


def fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def render(m: dict[str, Any], sweep: list[dict[str, Any]], th: Thresholds) -> str:
    L = [f"# Eval results: {th.version}", "",
         f"Run at {datetime.now(timezone.utc).isoformat(timespec='seconds')}. Model(s): {m['models']}. "
         f"Cases: {m['n']} (3 brief samples + {m['n'] - 3} own).", "",
         "## Accuracy per field", "", "| field | accuracy | n |", "|---|---|---|"]
    L += [f"| {k} | {v['acc']:.2f} | {v['n']} |" for k, v in m["field_accuracy"].items()]
    L += ["", f"All labelled fields correct: **{m['all_fields_correct']:.2f}** of cases.", "",
          "## Safety and confidentiality flags", "", "| flag | precision | recall | tp | fp | fn |", "|---|---|---|---|---|---|"]
    L += [f"| {f} | {fmt(v['precision'])} | {fmt(v['recall'])} | {v.get('tp', 0)} | {v.get('fp', 0)} | {v.get('fn', 0)} |" for f, v in m["flags"].items()]
    L += ["", f"Missed safety cases (expected safety flag, but auto-routed): **{len(m['missed_safety_cases'])}** {m['missed_safety_cases']}", "",
          "## Issue labels (cases with exact labels)", "", "| issue | precision | recall | tp | fp | fn |", "|---|---|---|---|---|---|"]
    L += [f"| {i} | {fmt(v['precision'])} | {fmt(v['recall'])} | {v.get('tp', 0)} | {v.get('fp', 0)} | {v.get('fn', 0)} |" for i, v in m["issues"].items()]
    ov = m["over_review"]
    L += ["", "## Human review", "", f"Share sent to human review: **{m['human_review_rate']:.2f}**", "",
          f"- Over-review: {ov['sent_to_review']} of {ov['n_expected_auto']} cases labelled auto_route were sent to review anyway",
          f"- Under-review (labelled human_review but auto-routed): **{len(m['under_review'])}** {m['under_review']}", "",
          "| review reason | count |", "|---|---|"]
    L += [f"| {r} | {c} |" for r, c in m["review_reason_counts"].items()]
    L += ["", "## Latency and cost", "",
          f"- Jev latency per grievance (one request): p50 {m['latency_ms'].get('p50', 'n/a')} ms, p95 {m['latency_ms'].get('p95', 'n/a')} ms",
          f"- Input tokens per grievance: mean {m['input_tokens'].get('mean', 0):.0f}, max {m['input_tokens'].get('max', 0)}",
          f"- Cost per grievance: ${m['cost_usd_per_grievance'] or 0:.6f} (input tokens x $0.042/Mtok; output free)", "",
          "## Threshold sweep (+/-0.1, replayed from cache)", "",
          "| variant | review rate | missed safety | sea_sh R | reprisal R | threat R | all-fields acc |", "|---|---|---|---|---|---|---|"]
    for s in sweep:
        f = s["m"]["flags"]
        L.append(f"| {s['name']} | {s['m']['human_review_rate']:.2f} | {len(s['m']['missed_safety_cases'])} | "
                 f"{fmt(f['sea_sh']['recall'])} | {fmt(f['reprisal_risk']['recall'])} | {fmt(f['threat_to_life']['recall'])} | {s['m']['all_fields_correct']:.2f} |")
    L += ["", "## Failing cases", "", "| case | failed fields | tags |", "|---|---|---|"]
    L += [f"| {f['id']} | {', '.join(f['failed'])} | {', '.join(f['tags'])} |" for f in m["failures"]] or ["| none | | |"]
    return "\n".join(L) + "\n"


async def main_async(args: argparse.Namespace) -> None:
    cases = load_cases()
    th = load_thresholds(args.thresholds)
    outs = await run(th, args.cache, cases)
    m = metrics(cases, outs)

    sweep = [{"name": "baseline", "m": m}]
    for target in ("safety", "routine"):
        for delta in (-0.1, +0.1):
            t2 = shifted(th, target, delta)
            sweep.append({"name": f"{target} {delta:+.1f}", "m": metrics(cases, await run(t2, "replay", cases))})

    RESULTS.mkdir(parents=True, exist_ok=True)
    report = render(m, sweep, th)
    (RESULTS / "eval_report.md").write_text(report, encoding="utf-8")
    (RESULTS / "eval_metrics.json").write_text(json.dumps({"baseline": m, "sweep": [{"name": s["name"], **{k: s["m"][k] for k in ("human_review_rate", "missed_safety_cases", "flags", "all_fields_correct")}} for s in sweep]}, indent=2, default=str), encoding="utf-8")
    with (RESULTS / "outputs.jsonl").open("w", encoding="utf-8") as f:
        for o in outs:
            f.write(o.model_dump_json() + "\n")
    print(report)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", choices=["live", "record", "replay"], default="live")
    ap.add_argument("--thresholds", default=None)
    load_env()
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
