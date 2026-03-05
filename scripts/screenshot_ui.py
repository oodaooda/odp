#!/usr/bin/env python3
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright


def main() -> int:
    ap = argparse.ArgumentParser(description="Capture UI screenshots")
    ap.add_argument("--url", action="append", required=True, help="URL to capture (repeatable)")
    ap.add_argument("--out", default="docs/ui_captures", help="Output directory")
    ap.add_argument("--wait", type=int, default=1000, help="Wait ms after load")
    args = ap.parse_args()

    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        for idx, url in enumerate(args.url, start=1):
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(args.wait)
            name = f"shot_{idx}.png"
            page.screenshot(path=str(out_dir / name), full_page=True)
            print(f"wrote {out_dir / name}")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
