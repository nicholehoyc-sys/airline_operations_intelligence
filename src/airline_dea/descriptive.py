"""Descriptive BTS flight-record measures; no capacity/availability inference.

A carrier/tail combination is an observation, not an airline-owned aircraft.
Completed legs require a non-diverted domestic record, valid tail, and valid
positive actual elapsed time in the data preparation pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CoverageCriteria:
    """Chart-quality screen only; NOT an underutilization or availability flag."""
    # Minimum thresholds for coverage criteria
    # hides aiecrafts that only appeared briefly in the data
    min_completed_legs: int = 300
    min_observed_span_days: int = 300
    min_active_days: int = 120

    def __post_init__(self) -> None:
        if min(self.min_completed_legs, self.min_observed_span_days, self.min_active_days) < 1:
            raise ValueError("Coverage thresholds must be positive")


class DescriptiveAnalytics:
    """Reconcile measured carrier and tail records and create descriptive KPIs."""

    def __init__(self, carrier: pd.DataFrame, aircraft: pd.DataFrame):
        self.carrier = carrier.copy()
        self.aircraft = aircraft.copy()
        self._validate()

    def _validate(self) -> None: # Validate the carrier and aircraft dataframes for required fields and consistency
        required_carrier = {"carrier", "scheduled_flights", "operated_flights", "cancelled_flights",
                            "diverted_flights", "eligible_arrivals", "on_time_arrivals",
                            "observed_aircraft", "recorded_block_minutes", "on_time_rate",
                            "distinct_destinations"}
        required_aircraft = {"carrier", "tail_num", "completed_flights", "observed_active_days",
                             "observed_span_days", "block_minutes", "block_hours_per_observed_active_day",
                             "legs_per_observed_active_day", "observed_active_day_ratio"}
        for name, frame, required in (("carrier", self.carrier, required_carrier),
                                      ("aircraft", self.aircraft, required_aircraft)):
            missing = required - set(frame.columns)
            if missing:
                raise ValueError(f"{name} missing fields: {sorted(missing)}")
        if self.carrier.carrier.duplicated().any() or self.aircraft.duplicated(["carrier", "tail_num"]).any():
            raise ValueError("Duplicate carrier or carrier-tail observations")
        c = self.carrier.set_index("carrier")
        a = self.aircraft
        if not set(a.carrier).issubset(set(c.index)):
            raise ValueError("Aircraft observations refer to missing carriers")
        if not (c.scheduled_flights == c.operated_flights + c.cancelled_flights).all():
            raise ValueError("Scheduled flights do not reconcile to non-cancelled plus cancelled")
        if not (c.on_time_arrivals <= c.eligible_arrivals).all():
            raise ValueError("On-time count exceeds eligible arrivals")
        if not (c.eligible_arrivals <= c.operated_flights - c.diverted_flights).all():
            raise ValueError("Eligible arrivals exceed non-diverted flights")
        if not (a.observed_active_days <= a.observed_span_days).all():
            raise ValueError("Aircraft active days exceed observed span")
        if not a.observed_active_day_ratio.between(0, 1).all():
            raise ValueError("Aircraft active-day ratio outside [0,1]")
        group = a.groupby("carrier").agg(tails=("tail_num", "size"),
                                         legs=("completed_flights", "sum"),
                                         block_minutes=("block_minutes", "sum"))
        for code, row in group.iterrows():
            if int(row.tails) > int(c.loc[code, "observed_aircraft"]):
                raise ValueError(f"{code}: more aircraft activity rows than observed tails")
            if row.legs > c.loc[code, "operated_flights"] - c.loc[code, "diverted_flights"]:
                raise ValueError(f"{code}: completed valid-duration legs exceed non-diverted flights")
            if not np.isclose(row.block_minutes, c.loc[code, "recorded_block_minutes"], atol=1e-5):
                raise ValueError(f"{code}: aircraft and carrier recorded block minutes disagree")

    def sample(self, carrier: str, criteria: CoverageCriteria | None = None) -> tuple[pd.DataFrame, int]:
        """Return tails with adequate annual observations for a comparable histogram.

        A coverage screen does not establish comparability of aircraft type/mission;
        the caller must display the coverage exclusions and domestic-only caveat.
        """
        # Filter aircraft rows for the specified carrier and apply coverage criteria
        criteria = criteria or CoverageCriteria()
        rows = self.aircraft.loc[self.aircraft.carrier == carrier].copy()
        included = rows.loc[(rows.completed_flights >= criteria.min_completed_legs)
                            & (rows.observed_span_days >= criteria.min_observed_span_days)
                            & (rows.observed_active_days >= criteria.min_active_days)].copy()
        return included, len(rows) - len(included)
        # return the number of excluded aircraft rows
    def carrier_summary(self) -> pd.DataFrame:
        """Carrier-level diagnostic ratios, not actual fleet utilization percentages."""
        c = self.carrier.copy()
        groups = self.aircraft.groupby("carrier").agg(
            valid_domestic_legs=("completed_flights", "sum"),
            sum_observed_active_tail_days=("observed_active_days", "sum"),
            median_tail_block_hours_per_active_day=("block_hours_per_observed_active_day", "median"),
            median_tail_active_day_ratio=("observed_active_day_ratio", "median"),
        )
        c = c.merge(groups, left_on="carrier", right_index=True, how="left", validate="one_to_one")
        c["flights_per_observed_aircraft"] = c.operated_flights / c.observed_aircraft.replace(0, np.nan)
        c["observed_domestic_block_hours_per_active_tail_day"] = (
            c.recorded_block_minutes / (60 * c.sum_observed_active_tail_days.replace(0, np.nan)))
        c["valid_duration_leg_coverage"] = c.valid_domestic_legs / (
            c.operated_flights - c.diverted_flights).replace(0, np.nan)
        return c
