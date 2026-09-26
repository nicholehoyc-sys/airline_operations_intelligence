"""Descriptive measures must not be confused with verified aircraft availability."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import json

import numpy as np
import pandas as pd

from airline_dea.descriptive import CoverageCriteria, DescriptiveAnalytics
from airline_dea.dashboard_service import DashboardDataService

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "results" / "ltm_2026"


class DescriptiveValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.carrier = pd.read_csv(SNAPSHOT / "carrier_metrics.csv")
        cls.aircraft = pd.read_csv(SNAPSHOT / "aircraft_activity.csv.gz")
        cls.model = DescriptiveAnalytics(cls.carrier, cls.aircraft)

    def test_aircraft_file_has_no_operational_actionability_flags(self):
        self.assertFalse(any("screen_" in col or "underutil" in col or "spare" in col
                             for col in self.aircraft.columns))
        self.assertEqual(len(self.aircraft), 6390)

    def test_coverage_is_a_chart_sample_not_an_availability_flag(self):
        selected, excluded = self.model.sample("AA", CoverageCriteria())
        self.assertEqual(len(selected) + excluded, len(self.aircraft.loc[self.aircraft.carrier == "AA"]))
        self.assertTrue((selected.completed_flights >= 300).all())
        self.assertTrue((selected.observed_span_days >= 300).all())
        self.assertTrue((selected.observed_active_days >= 120).all())
        self.assertFalse(any("priority" in x or "spare" in x for x in selected.columns))

    def test_validate_rejects_double_counting(self):
        damaged = self.carrier.copy()
        damaged.loc[0, "cancelled_flights"] += 1
        with self.assertRaisesRegex(ValueError, "Scheduled flights"):
            DescriptiveAnalytics(damaged, self.aircraft)

    def test_block_minutes_reconcile_and_valid_leg_denominator(self):
        summary = self.model.carrier_summary()
        self.assertEqual(int(summary.valid_domestic_legs.sum()), int(self.aircraft.completed_flights.sum()))
        self.assertTrue(summary.valid_duration_leg_coverage.between(0, 1).all())
        self.assertTrue(np.isclose(summary.recorded_block_minutes.sum(), self.aircraft.block_minutes.sum()))
        self.assertTrue((summary.valid_domestic_legs <= summary.operated_flights - summary.diverted_flights).all())

    def test_model_scores_match_baseline_and_sensitivity_is_not_rank_stable(self):
        data = DashboardDataService(ROOT).load()
        ranks = data["dea_rankings"].set_index("carrier")
        spec = data["dea_sensitivity"].pivot(index="carrier", columns="specification", values="efficiency")
        np.testing.assert_allclose(ranks.efficiency.sort_index(), spec.baseline.sort_index(), atol=1e-7)
        self.assertGreater(spec.loc["G4", "network_as_output"] - spec.loc["G4", "baseline"], 0.40)
        self.assertEqual(int((ranks.efficiency >= 1 - 1e-6).sum()), 2)

    def test_bad_snapshot_rejected_without_looking_at_any_actionability_flags(self):
        with TemporaryDirectory() as temporary:
            target = Path(temporary) / "results" / "ltm_2026"
            shutil.copytree(SNAPSHOT, target)
            manifest = json.loads((target / "provenance.json").read_text())
            manifest["scheduled_rows"] += 7
            (target / "provenance.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "totals disagree"):
                DashboardDataService(Path(temporary)).load()


if __name__ == "__main__":
    unittest.main()
