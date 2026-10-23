"""CLI: `triage one` for a single grievance, `triage batch` for JSONL."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from .jev_client import JevClient
from .env import load_env
from .llm import add_llm_outputs
from .pipeline import triage_many, triage_one
from .thresholds import load_thresholds


def _read_one(arg: str) -> dict[str, Any]:
    if arg == "-":
        return json.loads(sys.stdin.read())
    p = Path(arg)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return json.loads(arg)


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # unparseable line still produces an output (invalid_input -> human_review)
            rows.append({"grievance_id": f"LINE-{n}", "_raw": line})
    return rows


async def _run(args: argparse.Namespace) -> int:
    th = load_thresholds(args.thresholds)
    async with JevClient(th.model, cache_mode=args.cache, max_concurrency=args.concurrency) as client:
        if args.cmd == "one":
            raw = _read_one(args.input)
            out = await triage_one(raw, client, th)
            if args.with_llm:
                out = await add_llm_outputs(out, raw.get("text", ""))
            print(out.model_dump_json(indent=2))
        else:
            rows = _read_jsonl(args.input)
            outs = await triage_many(rows, client, th)
            if args.with_llm:
                outs = [await add_llm_outputs(o, r.get("text", "")) for o, r in zip(outs, rows)]
            dest = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
            try:
                for o in outs:
                    dest.write(o.model_dump_json() + "\n")
            finally:
                if args.output:
                    dest.close()
            n_rev = sum(o.action == "human_review" for o in outs)
            print(f"triaged {len(outs)} grievances, {n_rev} to human review", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="triage", description="MDB grievance triage with Jev")
    ap.add_argument("--thresholds", default=None, help="path to thresholds.yaml (default: config/thresholds.yaml)")
    ap.add_argument("--cache", choices=["off", "live", "record", "replay"], default="live",
                    help="live: use cache if present else call Jev; replay: offline only; off: always call")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--with-llm", action="store_true", help="add labelled LLM letter/summary AFTER the decision")
    sub = ap.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("one", help="triage one grievance (JSON string, file path, or - for stdin)")
    one.add_argument("input")
    batch = sub.add_parser("batch", help="triage a JSONL file, one grievance per line")
    batch.add_argument("input")
    batch.add_argument("-o", "--output", default=None)
    args = ap.parse_args(argv)
    load_env()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
