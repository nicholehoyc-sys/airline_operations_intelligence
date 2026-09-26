"""Compare a freshly regenerated output/ltm_2026 snapshot with the shipped results/ltm_2026.

Usage (from the project root, after `python src/run_ltm.py`):
    python src/compare_results.py
Exit code 0 = identical within floating-point tolerance; 1 = differences found.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TABLES = {
    "carrier_metrics.csv": ["carrier"],
    "carrier_monthly.csv": ["carrier", "year", "month"],
    "aircraft_activity.csv.gz": ["carrier", "tail_num"],
    "dea_rankings.csv": ["carrier"],
    "dea_sensitivity.csv": ["carrier", "specification"],
}


def compare_table(new: pd.DataFrame, old: pd.DataFrame, keys: list[str], rtol: float) -> list[str]:
    problems = []
    if list(new.columns) != list(old.columns):
        return [f"columns differ: new-only {sorted(set(new.columns) - set(old.columns))}, "
                f"shipped-only {sorted(set(old.columns) - set(new.columns))}"]
    if len(new) != len(old):
        problems.append(f"row count {len(new):,} vs shipped {len(old):,}")
    merged = new.merge(old, on=keys, how="outer", suffixes=("_new", "_old"), indicator=True)
    unmatched = merged[merged["_merge"] != "both"]
    if len(unmatched):
        problems.append(f"{len(unmatched):,} keys present in only one file, e.g. "
                        f"{unmatched[keys].head(3).to_dict('records')}")
    both = merged[merged["_merge"] == "both"]
    for col in (c for c in new.columns if c not in keys):
        a, b = both[f"{col}_new"], both[f"{col}_old"]
        if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
            bad = ~np.isclose(a.astype(float), b.astype(float), rtol=rtol, atol=1e-9, equal_nan=True)
        else:
            bad = a.astype("string").fillna("") != b.astype("string").fillna("")
        if bad.any():
            problems.append(f"column '{col}': {int(bad.sum()):,} differing rows")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--new", type=Path, default=Path("output/ltm_2026"))
    parser.add_argument("--shipped", type=Path, default=Path("results/ltm_2026"))
    parser.add_argument("--rtol", type=float, default=1e-9)
    args = parser.parse_args()
    if not (args.new / "provenance.json").is_file():
        print(f"No regenerated snapshot at {args.new}. Run `python src/run_ltm.py` first.", file=sys.stderr)
        return 1

    failures = 0
    new_m = json.loads((args.new / "provenance.json").read_text())
    old_m = json.loads((args.shipped / "provenance.json").read_text())
    new_hash = {a["filename"]: (a["sha256"], a["rows"]) for a in new_m["archives"]}
    old_hash = {a["filename"]: (a["sha256"], a["rows"]) for a in old_m["archives"]}
    for name, (sha, rows) in old_hash.items():
        got = new_hash.get(name)
        if got is None:
            print(f"[FAIL] provenance: {name} missing from new run"); failures += 1
        elif got != (sha, rows):
            print(f"[FAIL] provenance: {name} hash/row count differs (BTS may have revised the file)"); failures += 1
    for key in ("scheduled_rows", "operated_rows", "carrier_count", "observed_carrier_tail_pairs", "dea_eligible_carriers"):
        if new_m.get(key) != old_m.get(key):
            print(f"[FAIL] provenance {key}: {new_m.get(key)} vs shipped {old_m.get(key)}"); failures += 1
    if not failures:
        print("[OK]   provenance: 12/12 archive SHA-256 hashes and row counts match")

    for filename, keys in TABLES.items():
        problems = compare_table(pd.read_csv(args.new / filename), pd.read_csv(args.shipped / filename), keys, args.rtol)
        if problems:
            failures += 1
            print(f"[FAIL] {filename}")
            for p in problems:
                print(f"         - {p}")
        else:
            print(f"[OK]   {filename}")

    print("\nRESULT:", "regenerated output matches the shipped snapshot" if not failures
          else f"{failures} check(s) differ; see above")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
