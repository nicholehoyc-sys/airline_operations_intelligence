"""Offline fixtures are deliberately tiny and are never labeled actual BTS results."""
from __future__ import annotations
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from airline_dea.ltm_pipeline import (
    BTSArchiveInventory, BTSMonthlyReader, FILENAME, LTM_2026, NATIONAL_2013,
    PeriodAnalyzer,
)


class BTSYearPipelineTest(unittest.TestCase):
    @staticmethod
    def write_month(folder: Path, year: int, month: int, *, wrong_date=False, bad_cancel=False):
        codes = ("AA", "DL", "UA")
        rows = []
        for i, code in enumerate(codes):
            for j in range(3):
                rows.append({"FlightDate": f"{year}-{month:02d}-{j+1:02d}",
                             "Reporting_Airline": code, "Tail_Number": f"N{i+1:03d}{code}",
                             "Origin": "JFK" if j == 0 else "LAX", "Dest": "SFO" if j != 1 else "JFK",
                             "Cancelled": 1 if (i == 0 and j == 0) else 0,
                             "Diverted": 1 if (i == 1 and j == 0) else 0,
                             "ArrDelay": 15 if (i == 2 and j == 2) else 2,
                             "ActualElapsedTime": 115 + 5 * i, "AirTime": 90 + i})
        data = pd.DataFrame(rows)
        if wrong_date:
            data.loc[0, "FlightDate"] = "2020-01-01"
        if bad_cancel:
            data.loc[0, "Cancelled"] = 3
        name = FILENAME.format(year=year, month=month)
        with zipfile.ZipFile(folder / name, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("reporting_carrier.csv", data.to_csv(index=False))
        return folder / name

    def test_expected_ltm_months_include_2025_and_2026(self):
        months = LTM_2026.months()
        self.assertEqual(len(months), 12)
        self.assertEqual(months[0], (2025, 8))
        self.assertEqual(months[-1], (2026, 7))
        self.assertEqual(NATIONAL_2013.months(), [(2013, m) for m in range(1, 13)])

    def test_absent_month_fails_before_creating_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_month(root, 2026, 7)
            with self.assertRaisesRegex(FileNotFoundError, "missing 11 of 12"):
                PeriodAnalyzer(LTM_2026).process(BTSArchiveInventory(root, LTM_2026), root / "results", minimum_operated=1)
            self.assertFalse((root / "results").exists())

    def test_wrong_year_and_invalid_cancel_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            name = self.write_month(root, 2026, 7, wrong_date=True)
            with self.assertRaisesRegex(ValueError, "out-of-period"):
                list(BTSMonthlyReader(chunksize=2).iter_month(name, 2026, 7))
            name = self.write_month(root, 2026, 7, bad_cancel=True)
            with self.assertRaisesRegex(ValueError, "invalid cancelled"):
                list(BTSMonthlyReader(chunksize=2).iter_month(name, 2026, 7))

    def test_incomplete_calendar_month_rejected_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for year, month in LTM_2026.months():
                self.write_month(root, year, month)
            with self.assertRaisesRegex(ValueError, "missing calendar days"):
                PeriodAnalyzer(LTM_2026).process(
                    BTSArchiveInventory(root, LTM_2026), root / "results", minimum_operated=1
                )
            self.assertFalse((root / "results").exists())

    def test_end_to_end_twelve_month_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for year, month in LTM_2026.months():
                self.write_month(root, year, month)
            output = root / "results"
            provenance = PeriodAnalyzer(LTM_2026, BTSMonthlyReader(chunksize=2)).process(
                BTSArchiveInventory(root, LTM_2026), output, minimum_operated=1, require_complete_days=False
            )
            self.assertEqual(provenance["scheduled_rows"], 108)
            self.assertEqual(provenance["operated_rows"], 96)
            self.assertEqual(len(provenance["archives"]), 12)
            self.assertTrue(all(len(e["sha256"]) == 64 for e in provenance["archives"]))
            carriers = pd.read_csv(output / "carrier_metrics.csv").set_index("carrier")
            self.assertEqual(carriers.loc["AA", "cancelled_flights"], 12)
            self.assertEqual(carriers.loc["AA", "operated_flights"], 24)
            self.assertEqual(carriers.loc["DL", "diverted_flights"], 12)
            self.assertEqual(carriers.loc["DL", "eligible_arrivals"], 24)
            self.assertEqual(carriers.loc["UA", "on_time_arrivals"], 24)
            self.assertEqual(carriers.loc["AA", "observed_aircraft"], 1)
            self.assertEqual(carriers.loc["AA", "distinct_destinations"], 2)
            self.assertEqual(carriers.loc["AA", "active_months"], 12)
            rankings = pd.read_csv(output / "dea_rankings.csv")
            self.assertEqual(set(rankings.carrier), {"AA", "DL", "UA"})
            self.assertTrue(rankings.efficiency.between(0, 1.000001).all())
            aircraft = pd.read_csv(output / "aircraft_activity.csv.gz")
            self.assertEqual(len(aircraft), 3)
            self.assertEqual(int(aircraft.completed_flights.sum()), 84)
            self.assertEqual(json.loads((output / "provenance.json").read_text())["scheduled_rows"], 108)
            # The shipped snapshot must have exactly the schema this code produces.
            shipped = Path(__file__).resolve().parents[1] / "results" / "ltm_2026"
            for name in ("carrier_monthly.csv", "carrier_metrics.csv", "aircraft_activity.csv.gz",
                         "dea_rankings.csv", "dea_sensitivity.csv"):
                self.assertEqual(list(pd.read_csv(output / name).columns),
                                 list(pd.read_csv(shipped / name, nrows=1).columns), name)
            self.assertEqual(set(json.loads((output / "provenance.json").read_text())),
                             set(json.loads((shipped / "provenance.json").read_text())))

    def test_complete_national_2013_fixture_is_processed_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for year, month in NATIONAL_2013.months():
                self.write_month(root, year, month)
            output = root / "2013_result"
            manifest = PeriodAnalyzer(NATIONAL_2013, BTSMonthlyReader(chunksize=3)).process(
                BTSArchiveInventory(root, NATIONAL_2013), output, minimum_operated=1, require_complete_days=False
            )
            self.assertEqual(manifest["period"], "national_2013")
            self.assertEqual(manifest["scheduled_rows"], 108)
            self.assertEqual({str(e["filename"]).split("_")[-2] for e in manifest["archives"]}, {"2013"})
            self.assertEqual(len(pd.read_csv(output / "dea_rankings.csv")), 3)



if __name__ == "__main__":
    unittest.main()
