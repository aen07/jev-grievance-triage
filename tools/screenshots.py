"""Regenerate README screenshots of the Streamlit UI (dev tool, not part of the service).

Needs the API and UI running (ideally TRIAGE_CACHE=replay for deterministic output) and
`pip install playwright`. Uses the locally installed Microsoft Edge (no browser download).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

UI = "http://localhost:8501"
OUT = Path(__file__).resolve().parent.parent / "docs" / "img"

SHOTS = [
    # (file, url, text that must be visible before capture, crop: (top_text, bottom_text) or None)
    ("ui_sample2_decision.png", f"{UI}/?case=G-2026-00433&run=1", "fields match", ("Start from a labelled", "Raw Jev answers")),
    ("ui_sample2_jev_answers.png", f"{UI}/?case=G-2026-00433&run=1", "Urgency score", ("Raw Jev answers", "Full JSON output")),
    ("ui_injection_T022.png", f"{UI}/?case=T-022&run=1", "fields match", ("Start from a labelled", "Raw Jev answers")),
]


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge")
        page = await browser.new_page(viewport={"width": 1400, "height": 4200}, device_scale_factor=1)
        for name, url, ready, crop in SHOTS:
            await page.goto(url)
            await page.get_by_text(ready).first.wait_for(timeout=60_000)
            await page.wait_for_timeout(2500)  # let charts finish drawing
            main_el = page.locator("[data-testid=\"stMainBlockContainer\"]").first
            top = await page.get_by_text(crop[0]).first.bounding_box()
            bottom = await page.get_by_text(crop[1]).first.bounding_box()
            box = await main_el.bounding_box()
            clip = {"x": box["x"], "y": top["y"] - 20, "width": box["width"], "height": bottom["y"] - top["y"] + 10}
            await page.screenshot(path=str(OUT / name), clip=clip, full_page=True)
            print("wrote", name, clip)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
