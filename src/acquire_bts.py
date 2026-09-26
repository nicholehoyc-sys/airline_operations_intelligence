"""Retrieve original BTS monthly reporting-carrier ZIPs or emit manual URLs.

Use outside restricted environments; never confuse a blocked download with data.
"""
from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path

from airline_dea.ltm_pipeline import BTSArchiveInventory, LTM_2026, NATIONAL_2013


def fetch(inventory: BTSArchiveInventory) -> int:
    import requests
    inventory.source_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for entry in inventory.entries():
        target = inventory.source_dir / entry["filename"]
        if target.is_file():
            print(f"EXISTS {target.name}")
            continue
        part = target.with_name(target.name + ".part")
        print(f"GET {entry['url']}", flush=True)
        try:
            with requests.get(entry["url"], timeout=(15, 120), stream=True, headers={"User-Agent": "AirlineResearch/1.0"}) as resp:
                resp.raise_for_status()
                with part.open("wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
            import zipfile
            if not zipfile.is_zipfile(part):
                raise ValueError("HTTP response was not a ZIP file")
            with zipfile.ZipFile(part) as zf:
                if zf.testzip() is not None:
                    raise ValueError("archive contains a corrupt member")
            part.replace(target)
            print(f"SAVED {target.name} ({target.stat().st_size:,} bytes)")
        except (requests.RequestException, OSError, ValueError) as exc:
            failures += 1
            part.unlink(missing_ok=True)
            print(f"FAILED {target.name}: {exc}", file=sys.stderr)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch BTS original monthly flight ZIP archives")
    parser.add_argument("--period", choices=("ltm_2026", "national_2013"), default="ltm_2026")
    parser.add_argument("--source-dir", type=Path, default=Path("data/raw/bts_reporting"))
    parser.add_argument("--list-urls", action="store_true")
    args = parser.parse_args()
    period = LTM_2026 if args.period == "ltm_2026" else NATIONAL_2013
    inventory = BTSArchiveInventory(args.source_dir, period)
    if args.list_urls:
        print("\n".join(e["url"] for e in inventory.entries()))
        return 0
    failures = fetch(inventory)
    if failures:
        print(f"{failures} download(s) failed. Manual links: python src/acquire_bts.py --period {period.name} --list-urls", file=sys.stderr)
        return 1
    inventory.verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
