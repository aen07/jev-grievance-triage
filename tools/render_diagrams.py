"""Render docs/diagrams/*.mmd (Mermaid source) to docs/img/diagrams/*.png for the README.

Dev tool. Uses Playwright with the locally installed Microsoft Edge and mermaid.js from the
jsDelivr CDN (same engine GitHub uses), at 2x pixel density on a white background.

    python tools/render_diagrams.py            # all diagrams
    python tools/render_diagrams.py 07-routing # only names containing "07-routing"
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "diagrams"
OUT = ROOT / "docs" / "img" / "diagrams"
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs"

PAGE = f"""<!doctype html><html><head><meta charset="utf-8">
<style>body{{margin:0;background:#fff;font-family:'Segoe UI',Arial,sans-serif}} #box{{display:inline-block;padding:24px;background:#fff}}</style>
</head><body><div id="box"></div>
<script type="module">
import mermaid from '{MERMAID}';
mermaid.initialize({{startOnLoad:false, theme:'default', securityLevel:'loose',
  flowchart:{{htmlLabels:true, curve:'basis'}}, themeVariables:{{fontSize:'15px'}}}});
window.renderDiagram = async (src) => {{
  const {{svg}} = await mermaid.render('d' + Date.now(), src);
  document.getElementById('box').innerHTML = svg;
  const el = document.querySelector('#box svg');
  const vb = el.viewBox.baseVal;            // natural size from the viewBox, not the container
  el.removeAttribute('style');
  el.setAttribute('width', Math.ceil(vb.width));
  el.setAttribute('height', Math.ceil(vb.height));
  return true;
}};
window.ready = true;
</script></body></html>"""


async def main(filter_: str | None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in SRC.glob("*.mmd") if not filter_ or filter_ in p.stem)
    sizes = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge")
        page = await browser.new_page(viewport={"width": 2400, "height": 1200}, device_scale_factor=2)
        await page.set_content(PAGE)
        await page.wait_for_function("window.ready === true", timeout=30_000)
        for f in files:
            await page.evaluate("src => window.renderDiagram(src)", f.read_text(encoding="utf-8"))
            await page.wait_for_timeout(300)
            box = page.locator("#box")
            bb = await box.bounding_box()
            await box.screenshot(path=str(OUT / f"{f.stem}.png"))
            sizes[f.stem] = [round(bb["width"]), round(bb["height"])]
            print(f"{f.stem}.png  {sizes[f.stem][0]}x{sizes[f.stem][1]} css px (2x pixels)")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
