"""Probe: what happens if Jev is asked the filing-window question directly? (evidence for ED-007)

Not part of the pipeline. Asks the same date question over several (received, closing) pairs
whose correct answers are known, and prints Jev's probability next to the code's answer.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date

from triage.env import load_env
from triage.jev_client import JevClient
from triage.registry import add_months

PAIRS = [  # (received_at, closing_date)
    ("2026-10-05", "2022-03-31"),  # brief Test 3: 4.5 years after closing -> outside
    ("2024-03-31", "2022-03-31"),  # exactly 24 months -> inside
    ("2024-04-01", "2022-03-31"),  # 24 months + 1 day -> outside
    ("2027-09-30", "2025-09-30"),  # exactly 24 months -> inside
    ("2026-10-02", "2025-09-30"),  # 12 months -> inside
    ("2028-01-15", "2025-09-30"),  # 27.5 months -> outside
]

TEXT = "The drains built by the project are cracked and water comes into our houses."


async def main() -> None:
    load_env()
    rows = []
    async with JevClient("jev-1.13.0", cache_mode="live") as client:
        for received, closing in PAIRS:
            state = {"grievance_text": TEXT, "received_at": received, "project_closing_date": closing}
            q = {"in_window": {"type": "noul", "instructions":
                 "Was the grievance (`received_at`) received no later than 24 months after `project_closing_date`?"}}
            r = await client.ask(state, q)
            truth = date.fromisoformat(received) <= add_months(date.fromisoformat(closing), 24)
            rows.append({"received_at": received, "closing": closing, "jev_p_in_window": r.answers["in_window"]["noul"],
                         "code_in_window": truth, "model": r.model})
    for row in rows:
        print(json.dumps(row))


if __name__ == "__main__":
    asyncio.run(main())
