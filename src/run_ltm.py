"""Recompute the single validated LTM July 2026 analytical period from BTS archives.

No NYC 2013 sample, maintenance scenarios, or underutilization flags are generated.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from airline_dea.ltm_pipeline import (
    BTSArchiveInventory,
    BTSMonthlyReader,
    LTM_2026,
    PeriodAnalyzer,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path("data/raw/bts_reporting"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--minimum-operated", type=int, default=10_000)
    parser.add_argument("--chunk-size", type=int, default=150_000)
    args = parser.parse_args()
    if args.minimum_operated < 1 or args.chunk_size < 1:
        parser.error("--minimum-operated and --chunk-size must be positive")

    inventory = BTSArchiveInventory(args.source_dir, LTM_2026)
    # PeriodAnalyzer.process() performs inventory CRC / month preflight once,
    # before writing results. Do not decompress every archive twice here.
    try:
        manifest = PeriodAnalyzer(LTM_2026, BTSMonthlyReader(args.chunk_size)).process(
            inventory, args.output_dir / LTM_2026.name, minimum_operated=args.minimum_operated
        )
    except (FileNotFoundError, ValueError) as exc:
        parser.exit(1, f"LTM source validation failed: {exc}\n")
    print(f"{manifest['period']}: {manifest['scheduled_rows']:,} scheduled records; "
          f"{manifest['dea_eligible_carriers']} DEA-eligible reporting carriers")


if __name__ == "__main__":
    main()
