"""Reproducible national BTS on-time analysis; runs only on complete, verified archives.

The output concerns *observed domestic operations*, NOT airline fleet inventory or
available spare aircraft. Separate-period CCR frontiers are not year-over-year scores.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from datetime import date
import calendar
from collections import defaultdict
from typing import Iterable
import hashlib
import json
import zipfile

import numpy as np
import pandas as pd

from .dea_model import DEAModel

BTS_BASE = "https://transtats.bts.gov/PREZIP" #from official monthly files
FILENAME = "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
SOURCE_NAME = "Reporting Carrier On-Time Performance (1987-present)"
FIELDS = {
    "flight_date": ("FlightDate",),
    "carrier": ("Reporting_Airline", "UniqueCarrier"),
    "tail_num": ("Tail_Number", "TailNum"),
    "origin": ("Origin",),
    "dest": ("Dest",),
    "cancelled": ("Cancelled",),
    "diverted": ("Diverted",),
    "arr_delay": ("ArrDelay",),
    "actual_elapsed": ("ActualElapsedTime",),
    "air_time": ("AirTime",),
} #maps internal field names to BTS CSV column names
REQUIRED_FIELDS = tuple(FIELDS)


@dataclass(frozen=True) #setup code and fix reporting period
class ReportingPeriod:
    name: str
    start: date
    end: date

    def months(self) -> list[tuple[int, int]]: #returns a pair of integers with (year, month) tuples 
        cursor = date(self.start.year, self.start.month, 1) #move one month at a time
        last = date(self.end.year, self.end.month, 1)
        months = []
        while cursor <= last: #loop through every month in the reporting period
            months.append((cursor.year, cursor.month))
            cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1) #move year and month forward by one month
        if len(months) != 12 or self.start.day != 1 or self.end != (pd.Timestamp(last) + pd.offsets.MonthEnd(0)).date():
            raise ValueError(f"{self.name} requires precisely twelve complete calendar months")
        return months


LTM_2026 = ReportingPeriod("ltm_2026", date(2025, 8, 1), date(2026, 7, 31))
NATIONAL_2013 = ReportingPeriod("national_2013", date(2013, 1, 1), date(2013, 12, 31)) #check code works for any year


class BTSArchiveInventory:
    """Give users direct official links and require every expected local archive.""" #Checks that all required BTS monthly ZIP files are available locally before the analysis runs

    def __init__(self, source_dir: Path, period: ReportingPeriod):
        self.source_dir = Path(source_dir)
        self.period = period

    def entries(self) -> list[dict]:
        return [
            {
                "year": year,
                "month": month,
                "filename": FILENAME.format(year=year, month=month),
                "url": f"{BTS_BASE}/{FILENAME.format(year=year, month=month)}",
            }
            for year, month in self.period.months()
        ]

    def verify(self) -> list[tuple[int, int, Path]]:
        missing = [e for e in self.entries() if not (self.source_dir / e["filename"]).is_file()]
        if missing:
            raise FileNotFoundError(
                f"{self.period.name}: missing {len(missing)} of 12 original BTS archives in {self.source_dir}. "
                "No partial-period results will be generated. Missing files:\n" +
                "\n".join(f"  {e['filename']}  {e['url']}" for e in missing)
            )
        paths = []
        for e in self.entries():
            path = self.source_dir / e["filename"]
            if not zipfile.is_zipfile(path):
                raise ValueError(f"Invalid BTS ZIP: {path}")
            with zipfile.ZipFile(path) as zf:
                if zf.testzip() is not None:
                    raise ValueError(f"Corrupt member in {path}")
            paths.append((e["year"], e["month"], path))
        return paths


class BTSMonthlyReader:
    """Read *one* PREZIP CSV in chunks without retaining all 12 months in RAM."""

    def __init__(self, chunksize: int = 150_000):
        self.chunksize = chunksize

    @staticmethod
    def _csv_name(zf: zipfile.ZipFile) -> str:
        csvs = [name for name in zf.namelist() if name.lower().endswith(".csv") and
                not name.startswith("__MACOSX/")]
        if len(csvs) != 1:
            raise ValueError(f"Expected exactly one CSV in {zf.filename}, found {csvs}")
        return csvs[0]

    @staticmethod
    def _field_map(header: Iterable[str], path: Path) -> dict:
        lookup = {h.strip().lower().lstrip("\ufeff"): h for h in header}
        columns = {}
        for target, alternatives in FIELDS.items():
            match = next((lookup[a.lower()] for a in alternatives if a.lower() in lookup), None)
            if match is None:
                raise ValueError(f"{path.name}: missing {target} field, expected {alternatives}")
            columns[match] = target
        return columns

    @staticmethod
    def _dates(s: pd.Series) -> pd.Series:
        t = s.astype("string").str.strip()
        compact = t.str.fullmatch(r"\d{8}").fillna(False)
        dates = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
        dates.loc[compact] = pd.to_datetime(t.loc[compact], format="%Y%m%d", errors="coerce")
        dates.loc[~compact] = pd.to_datetime(t.loc[~compact], errors="coerce", format="mixed")
        return dates

    def iter_month(self, path: Path, year: int, month: int) -> Iterable[pd.DataFrame]: #opens a Zip and reads the CSV in chunks for the specified year and month
        with zipfile.ZipFile(path) as zf:
            member = self._csv_name(zf)
            with zf.open(member) as stream:
                columns = self._field_map(pd.read_csv(stream, nrows=0).columns, path)
            # Read identifying fields as strings to preserve codes and YYYYMMDD.
            text_fields = {original: "string" for original, canonical in columns.items()
                           if canonical in {"flight_date", "carrier", "tail_num", "origin", "dest"}}
            with zf.open(member) as stream:
                for raw in pd.read_csv(
                    stream, usecols=list(columns), dtype=text_fields,
                    chunksize=self.chunksize, low_memory=False,
                ):
                    df = raw.rename(columns=columns)
                    df["flight_date"] = self._dates(df["flight_date"]) #convert the flight_date column to datetime objects 
                    bad_date = df["flight_date"].isna() | (df["flight_date"].dt.year != year) | (df["flight_date"].dt.month != month) #identify rows with invalid or out-of-period dates
                    if bad_date.any():
                        raise ValueError(f"{path.name}: {int(bad_date.sum())} rows have invalid/out-of-period FlightDate")
                    for col in ("carrier", "tail_num", "origin", "dest"):
                        df[col] = df[col].astype("string").str.strip().str.upper()
                    if df[["carrier", "origin", "dest"]].isna().any().any():
                        raise ValueError(f"{path.name}: carrier/origin/destination missing") #check for blank or missing values
                    for col in ("cancelled", "diverted"):
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                        if not df[col].isin((0, 1)).all():
                            raise ValueError(f"{path.name}: invalid {col} values")
                        df[col] = df[col].astype(bool)
                    for col in ("arr_delay", "actual_elapsed", "air_time"):
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                    yield df


def _digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


class PeriodAnalyzer:
    """Carrier and aircraft-day metrics without inferring true airline-owned fleet size."""

    def __init__(self, period: ReportingPeriod, reader: BTSMonthlyReader | None = None):
        self.period = period
        self.reader = reader or BTSMonthlyReader()

    def process(self, inventory: BTSArchiveInventory, output_dir: Path, *, minimum_operated: int = 10000,
                require_complete_days: bool = True) -> dict:
        # Input preflight completes before creating any output files.
        archives = inventory.verify()
        output_dir = Path(output_dir)
        monthly_parts = []
        aircraft_days = []
        monthly_day_coverage = {}
        distinct_tails: dict[str, set[str]] = defaultdict(set)
        distinct_destinations: dict[str, set[str]] = defaultdict(set)
        manifest = {"period": self.period.name, "start": str(self.period.start), "end": str(self.period.end),
                    "source": SOURCE_NAME, "geography": "US domestic reporting-carrier records, nationwide",
                    "completeness": "all 12 archives required", "archives": [],
            "on_time_definition": "arr_delay < 15 minutes; excluded cancelled/diverted and missing delay from rate denominator"}

        for year, month, path in archives:
            month_frames = []
            month_days = []
            observed_days = set()
            rows = 0
            for data in self.reader.iter_month(path, year, month):
                rows += len(data)
                observed_days.update(data["flight_date"].dt.day.unique().tolist())
                active = ~data["cancelled"] # flights that were not cancelled
                arrived = active & (~data["diverted"]) & data["arr_delay"].notna() # flights that arrived on time (not cancelled, not diverted, and have arrival delay recorded)
                on_time = arrived & data["arr_delay"].lt(15) # flights that arrived on time (arrival delay less than 15 minutes)
                valid_elapsed = (active & (~data["diverted"]) & data["actual_elapsed"].gt(0) &
                                 data["actual_elapsed"].le(24 * 60)) # flights with valid actual elapsed time (gate-to-gate time between 0 and 24 hours)
                valid_tail = data["tail_num"].notna() & data["tail_num"].ne("")

                counts = data[["carrier"]].copy() # create a copy of the carrier column for counting purposes -- count by carrier
                counts["scheduled_flights"] = 1
                counts["operated_flights"] = active.astype("int8")
                counts["cancelled_flights"] = data["cancelled"].astype("int8")
                counts["diverted_flights"] = (active & data["diverted"]).astype("int8")
                counts["eligible_arrivals"] = arrived.astype("int8")
                counts["on_time_arrivals"] = on_time.astype("int8")
                counts["missing_arrival_delay"] = (active & (~data["diverted"]) &
                                                    data["arr_delay"].isna()).astype("int8")
                counts["missing_tail_operated"] = (active & (~valid_tail)).astype("int8")
                counts["recorded_block_minutes"] = data["actual_elapsed"].where(valid_elapsed, 0).astype(float)
                month_frames.append(counts.groupby("carrier", sort=False).sum())

                # Tracks unique aircraft and destinations
                # Build carrier-level sets of unique observed aircraft and destinations. Prevent the same tail number or destination from being counted more than once when it appears across multiple flights or monthly BTS files
                for carrier, sub in data.loc[active & valid_tail, ["carrier", "tail_num"]].groupby("carrier"):
                    distinct_tails[str(carrier)].update(sub["tail_num"].dropna().astype(str).unique())
                for carrier, sub in data.loc[active, ["carrier", "dest"]].groupby("carrier"):
                    distinct_destinations[str(carrier)].update(sub["dest"].dropna().astype(str).unique())

                flight_days = data.loc[valid_elapsed & valid_tail,
                                       ["carrier", "tail_num", "flight_date", "actual_elapsed"]]
                if not flight_days.empty:
                    flight_days["completed_flights"] = 1
                    g = flight_days.groupby(["carrier", "tail_num", "flight_date"], sort=False).agg(
                        completed_flights=("completed_flights", "sum"),
                        block_minutes=("actual_elapsed", "sum"), # Build record on the block minutes for each carrier, tail number, and flight date per day
                    ).reset_index()
                    month_days.append(g) # Append the grouped flight days for the current month
            if rows == 0:
                raise ValueError(f"{path.name}: no data rows")
            expected_days = set(range(1, calendar.monthrange(year, month)[1] + 1))
            if require_complete_days and observed_days != expected_days:
                raise ValueError(f"{path.name}: missing calendar days {sorted(expected_days - observed_days)}")
            monthly_day_coverage[f"{year}-{month:02d}"] = len(observed_days)
            stats = pd.concat(month_frames).groupby(level=0).sum()
            stats["year"] = year
            stats["month"] = month
            monthly_parts.append(stats.reset_index())
            if month_days:
                aircraft_days.append(pd.concat(month_days).groupby(
                    ["carrier", "tail_num", "flight_date"], as_index=False
                )[["completed_flights", "block_minutes"]].sum())
            manifest["archives"].append({"filename": path.name, "url": f"{BTS_BASE}/{path.name}",
                                          "sha256": _digest(path), "rows": rows})

        monthly = pd.concat(monthly_parts, ignore_index=True)
        carrier = monthly.groupby("carrier", as_index=False)[[
            "scheduled_flights", "operated_flights", "cancelled_flights", "diverted_flights",
            "eligible_arrivals", "on_time_arrivals", "missing_arrival_delay",
            "missing_tail_operated", "recorded_block_minutes",
        ]].sum()
        # define carrier-level metrics based on the aggregated monthly data
        carrier["observed_aircraft"] = carrier["carrier"].map(lambda c: len(distinct_tails[str(c)]))
        carrier["observed_tail_reporting_coverage"] = 1 - carrier["missing_tail_operated"] / carrier["operated_flights"].replace(0, np.nan)
        carrier["distinct_destinations"] = carrier["carrier"].map(lambda c: len(distinct_destinations[str(c)]))
        carrier["on_time_rate"] = carrier["on_time_arrivals"] / carrier["eligible_arrivals"].replace(0, np.nan)
        carrier["cancellation_rate"] = carrier["cancelled_flights"] / carrier["scheduled_flights"]
        carrier["arrival_delay_coverage"] = carrier["eligible_arrivals"] / (
            carrier["operated_flights"] - carrier["diverted_flights"]
        ).replace(0, np.nan)
        active_months = monthly.loc[monthly["operated_flights"].gt(0)].groupby("carrier").size()
        carrier["active_months"] = carrier["carrier"].map(active_months).fillna(0).astype(int)
        eligible = (carrier["observed_aircraft"].gt(0) & carrier["distinct_destinations"].gt(0)
                    & carrier["operated_flights"].ge(minimum_operated)
                    & carrier["active_months"].eq(12) & carrier["on_time_arrivals"].gt(0))
        carrier["dea_eligible"] = eligible
        carrier["dea_exclusion_reason"] = np.select(
            [carrier["active_months"].ne(12),
             carrier["operated_flights"].lt(minimum_operated),
             carrier["observed_aircraft"].le(0) | carrier["distinct_destinations"].le(0) |
             carrier["on_time_arrivals"].le(0)],
            ["fewer than 12 active reporting months", "below minimum flight-volume threshold",
             "missing or non-positive DEA variable"], default="")
        ranking = self._fit_dea(carrier.loc[eligible].copy())
        sensitivity = self._dea_sensitivity(carrier.loc[eligible].copy())

        if not aircraft_days:
            raise ValueError(f"{self.period.name}: no valid aircraft/day records")
        days = pd.concat(aircraft_days, ignore_index=True).groupby(
            ["carrier", "tail_num", "flight_date"], as_index=False
        )[["completed_flights", "block_minutes"]].sum()
        # Aircraft-level span depends on first/last observed flight; a gap may be
        # international service, maintenance, coverage changes, etc. Not confirmed idle time.
        aircraft = days.groupby(["carrier", "tail_num"], as_index=False).agg(
            completed_flights=("completed_flights", "sum"),
            observed_active_days=("flight_date", "nunique"),
            first_observed=("flight_date", "min"),
            last_observed=("flight_date", "max"),
            block_minutes=("block_minutes", "sum"),
        )
        aircraft["observed_span_days"] = (aircraft["last_observed"] - aircraft["first_observed"]).dt.days + 1
        period_days = (self.period.end - self.period.start).days + 1
        aircraft["observed_active_day_ratio"] = aircraft["observed_active_days"] / aircraft["observed_span_days"]
        aircraft["observed_active_day_ratio_full_period"] = aircraft["observed_active_days"] / period_days
        aircraft["observed_domestic_block_hours_per_calendar_day"] = aircraft["block_minutes"] / (60 * period_days)
        aircraft["observed_domestic_legs_per_calendar_day"] = aircraft["completed_flights"] / period_days
        aircraft["block_hours_per_observed_active_day"] = aircraft["block_minutes"] / 60 / aircraft["observed_active_days"]
        aircraft["legs_per_observed_active_day"] = aircraft["completed_flights"] / aircraft["observed_active_days"]
        aircraft["mean_observed_domestic_leg_minutes"] = aircraft["block_minutes"] / aircraft["completed_flights"]
        # Descriptive metrics only. Never infer idle capacity or classify tails
        # as underutilized from incomplete domestic flight movements.

        # Write only after all sources validate, processing and DEA succeed to prevent half-written outputs
        output_dir.mkdir(parents=True, exist_ok=True)
        monthly.to_csv(output_dir / "carrier_monthly.csv", index=False)
        carrier.to_csv(output_dir / "carrier_metrics.csv", index=False)
        aircraft.to_csv(output_dir / "aircraft_activity.csv.gz", index=False, compression="gzip")
        ranking.to_csv(output_dir / "dea_rankings.csv", index=False)
        sensitivity.to_csv(output_dir / "dea_sensitivity.csv", index=False)
        manifest["scheduled_rows"] = int(carrier["scheduled_flights"].sum())
        manifest["operated_rows"] = int(carrier["operated_flights"].sum())
        manifest["calendar_days_per_month"] = monthly_day_coverage
        manifest["carrier_count"] = int(len(carrier))
        manifest["observed_carrier_tail_pairs"] = int(len(aircraft))
        manifest["dea_eligible_carriers"] = int(eligible.sum())
        manifest["method_note"] = ("Domestic flight records; observed tails are not inventory; "
                                   "no spare capacity, redeployment or maintenance recommendations.")
        manifest["model_interpretation"] = ("DEA model-dependent observed frequency and network tradeoffs; "
                                            "not overall operational efficiency or feasible peer prescriptions.")
        manifest["dea_sensitivity_models"] = sorted(sensitivity["specification"].unique().tolist())
        manifest["analysis_scope"] = ("Descriptive domestic aircraft activity and model-dependent CCR DEA; "
                                      "no aircraft actionability classification")
        (output_dir / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
        return manifest

    @staticmethod
    def _fit_dea(carrier: pd.DataFrame) -> pd.DataFrame:
        """
        Run the baseline CCR DEA model and return carrier-level efficiency
        scores, slacks, reference peers, rankings, and frontier classifications.
        """

        # DEA is a relative benchmark. Stop if the carrier population is
        # unexpectedly small, which may indicate missing or incorrectly filtered data.
        if len(carrier) < 3:
            raise ValueError("DEA requires at least three eligible carriers")

        # Use carrier codes as row labels so DEA outputs can be matched back
        # to the correct airline.
        indexed = carrier.set_index("carrier")

        # Baseline DEA specification
        # Inputs represent observed fleet/network resources, while outputs
        # represent flight activity and service reliability.
        input_names = [
            "observed_aircraft",
            "distinct_destinations",
        ]

        output_names = [
            "operated_flights",
            "on_time_arrivals",
        ]

        # Pass original values to DEAModel. The model performs numerical
        # scaling internally and converts slacks back to original units.
        x = indexed[input_names].astype(float)
        y = indexed[output_names].astype(float)

        # Solve the CCR DEA model for all eligible carriers.
        model = DEAModel(x, y)
        result = model.fit()

        # Start from the original carrier metrics and append DEA results.
        ranking = carrier.copy()

        # Match each carrier with its DEA efficiency score.
        ranking["efficiency"] = ranking["carrier"].map(
            result.efficiency
        )

        # Small optimization residuals can occur because of floating-point
        # arithmetic. Only treat relative slacks above this tolerance as meaningful.
        SLACK_TOLERANCE = 1e-5

        def has_meaningful_slack(carrier_code: str) -> bool:
            """Check whether a carrier has meaningful input or output slack."""

            input_relative_slack = (
                result.input_slacks.loc[carrier_code]
                / indexed.loc[carrier_code, input_names]
            )

            # clip(lower=1) prevents division by zero for an output value of zero.
            output_relative_slack = (
                result.output_slacks.loc[carrier_code]
                / indexed.loc[carrier_code, output_names].clip(lower=1)
            )

            return bool(
                (input_relative_slack > SLACK_TOLERANCE).any()
                or (output_relative_slack > SLACK_TOLERANCE).any()
            )

        ranking["has_nonradial_slack"] = ranking["carrier"].map(
            has_meaningful_slack
        )

        # Format slacks as compact strings for CSV/dashboard display.
        ranking["input_slacks"] = ranking["carrier"].map(
            lambda c: "; ".join(
                f"{name}:{value:.2f}"
                for name, value in result.input_slacks.loc[c].items()
            )
        )

        ranking["output_slacks"] = ranking["carrier"].map(
            lambda c: "; ".join(
                f"{name}:{value:.2f}"
                for name, value in result.output_slacks.loc[c].items()
            )
        )

        # DEA reference peers are mathematical frontier benchmarks.
        # They should not be interpreted as airlines that another carrier
        # should directly imitate.
        peer_map = (
            result.peer_summary()
            .set_index("carrier")["peers"]
        )

        ranking["reference_peers"] = ranking["carrier"].map(peer_map)

        # Sort highest-efficiency carriers first.
        ranking = (
            ranking
            .sort_values(
                ["efficiency", "carrier"],
                ascending=[False, True]
            )
            .reset_index(drop=True)
        )

        # Round before ranking so tiny solver precision differences do not
        # create artificial differences between effectively equal scores.
        ranking["rank"] = (
            ranking["efficiency"]
            .round(6)
            .rank(method="min", ascending=False)
            .astype(int)
        )

        # Distinguish carriers that are fully efficient from carriers that
        # reach the radial frontier but retain non-radial input/output slack.
        on_frontier = ranking["efficiency"].ge(1 - 1e-6)

        ranking["frontier_status"] = np.select(
            [
                on_frontier & ~ranking["has_nonradial_slack"],
                on_frontier & ranking["has_nonradial_slack"],
            ],
            [
                "strongly_efficient",
                "radially_efficient_with_slack",
            ],
            default="below_frontier",
        )
        return ranking

    @staticmethod
    def _dea_sensitivity(eligible: pd.DataFrame) -> pd.DataFrame:
        """Expose model dependence; never treat alternative scores as direct rankings.

        Baseline: aircraft + destinations as inputs, flights + on-time counts as outputs.
        Volume: same inputs, flights only. Network-as-service: aircraft as input,
        operated flights + distinct destinations as outputs. These embody different
        production assumptions and are NOT averaged or treated as temporal trends.
        """
        specs = {
            "block_hours_exposure": (["observed_aircraft", "distinct_destinations"], ["recorded_block_minutes"]), #replace hours flown with flights counts to be fairer to long-haul carriers
            "baseline": (["observed_aircraft", "distinct_destinations"], ["operated_flights", "on_time_arrivals"]),
            "volume_only": (["observed_aircraft", "distinct_destinations"], ["operated_flights"]),
            "network_as_output": (["observed_aircraft"], ["operated_flights", "distinct_destinations"]),
        }
        indexed = eligible.set_index("carrier")
        result = []
        for name, (inputs, outputs) in specs.items():
            scores = DEAModel(indexed[inputs].astype(float), indexed[outputs].astype(float)).fit()
            for carrier, score in scores.efficiency.items():
                result.append({"carrier": carrier, "specification": name, "efficiency": score,
                               "input_variables": ",".join(inputs), "output_variables": ",".join(outputs)})
        return pd.DataFrame(result)
