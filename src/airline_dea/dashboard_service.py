"""Load the single provenance-backed recent LTM analytical snapshot for the dashboard."""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

from .descriptive import DescriptiveAnalytics


class DashboardDataService:
    FILES = ("carrier_metrics.csv", "carrier_monthly.csv", "dea_rankings.csv",
             "dea_sensitivity.csv", "aircraft_activity.csv.gz", "provenance.json")

    def __init__(self, project_root: Path):
        self.root = Path(project_root)

    def snapshot_dir(self) -> Path:
        """Prefer locally regenerated results; otherwise use the checked-in snapshot."""
        for base in ("output", "results"):
            candidate = self.root / base / "ltm_2026"
            if all((candidate / name).is_file() for name in self.FILES):
                return candidate
        raise FileNotFoundError("No complete LTM snapshot; run `python src/run_ltm.py` or restore results/ltm_2026")

    def load(self) -> dict: # Load and validate the LTM snapshot data for the dashboard before displaying it
        folder = self.snapshot_dir()
        manifest = json.loads((folder / "provenance.json").read_text())
        if manifest.get("period") != "ltm_2026" or (manifest.get("start"), manifest.get("end")) != (
                "2025-08-01", "2026-07-31"):
            raise ValueError("Snapshot reporting period does not match LTM July 2026")
        archives = manifest.get("archives", [])
        if len(archives) != 12 or any(len(str(a.get("sha256", ""))) != 64 for a in archives):
            raise ValueError("Snapshot is missing the 12 source archive hashes")
        data = {"manifest": manifest}
        for filename in self.FILES:
            if filename != "provenance.json":
                data[filename.split(".")[0]] = pd.read_csv(folder / filename)
        carrier, aircraft = data["carrier_metrics"], data["aircraft_activity"]
        if int(carrier.scheduled_flights.sum()) != manifest["scheduled_rows"] or (
                int(carrier.operated_flights.sum()) != manifest["operated_rows"]):
            raise ValueError("Carrier flight totals disagree with source provenance")
        if len(carrier) != manifest["carrier_count"] or len(aircraft) != manifest["observed_carrier_tail_pairs"]:
            raise ValueError("Carrier/tail counts disagree with source provenance")
        DescriptiveAnalytics(carrier, aircraft)  # Reconcile recorded activity before displaying it.
        ranking, sensitivity = data["dea_rankings"], data["dea_sensitivity"]
        eligible = set(carrier.loc[carrier.dea_eligible, "carrier"])
        if set(ranking.carrier) != eligible or set(sensitivity.carrier) != eligible:
            raise ValueError("DEA outputs do not match the eligible reporting population")
        if not ranking.efficiency.between(0, 1.000001).all() or not sensitivity.efficiency.between(0, 1.000001).all():
            raise ValueError("DEA scores outside the CCR score range")
        baseline = sensitivity.loc[sensitivity.specification == "baseline"].set_index("carrier").efficiency
        actual = ranking.set_index("carrier").efficiency
        if set(baseline.index) != eligible or not (baseline.reindex(actual.index) - actual).abs().le(1e-6).all():
            raise ValueError("Primary DEA results disagree with baseline sensitivity")
        data["descriptive"] = DescriptiveAnalytics(carrier, aircraft)
        return data
