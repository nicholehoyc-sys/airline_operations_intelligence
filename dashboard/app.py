"""Three-page Streamlit explorer: DEA assumptions, observed fleet activity, strategy KPIs.

Run from the project root: streamlit run dashboard/app.py
No spare-capacity, maintenance, or future flight availability claims are made.
"""
# frontend for the airline operations intelligence dashboard
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import plotly.express as px
import streamlit as st

from airline_dea.dashboard_service import DashboardDataService
from airline_dea.descriptive import CoverageCriteria
from airline_dea.carriers import CARRIER_NAMES, label

st.set_page_config(page_title="Airline Operations Intelligence", layout="wide")


@st.cache_data(show_spinner=False)
def load_data() -> dict:
    return DashboardDataService(ROOT).load()


def table(frame: pd.DataFrame, columns: list[str]) -> None:
    st.dataframe(frame[columns], hide_index=True, use_container_width=True)


def production_description(spec: str) -> str:
    return {
        "baseline":
            "Core benchmark — fleet + network size vs. flights + on-time operations",

        "volume_only":
            "Flight volume — fleet + network size vs. flights operated",

        "network_as_output":
            "Network reach — fleet size vs. flights + destinations served",

        "block_hours_exposure":
            "Flying activity — fleet + network size vs. domestic flying hours",
    }[spec]

st.title("Airline Operations Intelligence")
st.caption("Benchmarking U.S. airline operating efficiency and fleet activity "
           " using domestic flight data from August 2025 to July 2026")
st.info("This dashboard compares how carriers deploy their observed aircraft and networks "
    "to generate flight activity and on-time operations. Results describe domestic "
    "operations in the BTS dataset and should not be interpreted as total fleet "
    "utilization, profitability, or overall airline quality.")

try:
    data = load_data()
except (ValueError, FileNotFoundError, KeyError, OSError) as exc:
    st.error(f"A complete, internally consistent LTM dataset is required: {exc}")
    st.stop()

manifest = data["manifest"]
carrier = data["carrier_metrics"]
monthly = data["carrier_monthly"]
ranking = data["dea_rankings"]
sensitivity = data["dea_sensitivity"]
analytics = data["descriptive"]
aircraft = data["aircraft_activity"]
summary = analytics.carrier_summary()
for frame in (carrier, ranking, sensitivity, summary):
    frame.insert(1, "carrier_name", frame["carrier"].map(CARRIER_NAMES).fillna(""))

stats = st.columns(4)
stats[0].metric("Scheduled flight", f"{manifest['scheduled_rows']:,}")
stats[1].metric("Flights operated", f"{manifest['operated_rows']:,}")
stats[2].metric("Reporting / DEA-eligible carriers", f"{manifest['carrier_count']} / {manifest['dea_eligible_carriers']}")
stats[3].metric("Observed carrier–tail combinations", f"{len(aircraft):,}")

benchmark, fleet, insights = st.tabs(["Efficiency benchmark", "Fleet activity", "Carrier comparisons"])

with benchmark:

    st.header(
        "How efficiently do carriers convert operating resources into flight activity?" )

    st.write(
        "DEA benchmarks each carrier against the strongest-performing combinations "
        "of carriers in the dataset. A higher score indicates stronger relative "
        "performance under the selected operating assumptions.")

    st.info(
        "A score of 1.0 means the carrier sits on the modeled efficiency frontier. "
        "The score is a relative operating benchmark — not an overall ranking of "
        "airline quality, profitability, or management performance."    )

    # Allow users to test how different definitions of airline output
    # affect the relative efficiency results.
    specs = [
        "baseline",
        "volume_only",
        "network_as_output",
        "block_hours_exposure",]

    spec = st.selectbox(
        "Choose benchmarking approach",
        specs,
        format_func=production_description, )

    selected = (
        sensitivity.loc[sensitivity.specification.eq(spec)]
        .sort_values("efficiency", ascending=False) )

    st.plotly_chart(
        px.bar(
            selected,
            x="carrier",
            y="efficiency",
            hover_data=[
                "carrier_name",
                "input_variables",
                "output_variables",    ],
            range_y=[0, 1.05],
            labels={
                "carrier": "Carrier",
                "efficiency": "Relative efficiency score",},
            title="Relative operating efficiency by carrier", ),
        use_container_width=True,
    )

    st.caption(
        "Higher scores indicate stronger performance relative to the peer group "
        "under the selected assumptions. Changing what the model treats as an "
        "input or output can materially change carrier scores."   )

    # Show the underlying model variables for users who want more detail.
    table(
        selected,
        [
            "carrier",
            "carrier_name",
            "efficiency",
            "input_variables",
            "output_variables",
        ],   )

    # Keep technical DEA assumptions available without placing them
    # in front of users who only want the business interpretation.
    with st.expander("How to interpret this DEA benchmark"):
        st.markdown(
            """
            **Model:** Input-oriented CCR Data Envelopment Analysis.

            The model compares how effectively carriers convert selected
            operating resources into observed outputs.

            **Important limitations**

            - Carriers operate different business models, including regional,
              low-cost and network-carrier structures.
            - Aircraft size, seat capacity and route distance are not directly
              controlled in the baseline model.
            - Destination count can represent either operating complexity or
              valuable network reach, depending on the model specification.
            - On-time arrivals are related to overall flight volume.
            - Results therefore depend on the selected inputs, outputs and peer
              population.

            For these reasons, DEA scores should be interpreted as
            **model-dependent relative operating benchmarks**, rather than as
            absolute measures of airline efficiency.
            """
        )
    st.subheader("Sensitivity: How much do modeling assumptions change the result?")
    st.write(
    "DEA results depend on what the model treats as a resource versus an output. "
    "Comparing alternative specifications shows which carrier conclusions are "
    "robust and which are highly assumption-dependent.")
    pivot = sensitivity.pivot(index="carrier", columns="specification", values="efficiency").reset_index()
    pivot.insert(1, "carrier_name", pivot["carrier"].map(CARRIER_NAMES).fillna(""))
    pivot["model_score_range"] = pivot[specs].max(axis=1) - pivot[specs].min(axis=1)
    table(pivot.sort_values("model_score_range", ascending=False), ["carrier", "carrier_name", *specs, "model_score_range"])
    st.caption("A larger range means the carrier's relative position is more sensitive to how operating efficiency is defined.")
    # Let the user inspect one carrier's baseline DEA result in business-friendly terms.
chosen = st.selectbox(
    "Select a carrier to inspect",
    ranking.carrier.tolist(),
    format_func=label,
)

r = ranking.loc[ranking.carrier.eq(chosen)].iloc[0]

st.subheader("Carrier benchmark summary")

col1, col2, col3 = st.columns(3)

col1.metric(
    "Baseline efficiency score",
    f"{float(r.efficiency):.3f}",
)

# Translate the technical DEA frontier classification into simpler language.
frontier_label = {
    "strongly_efficient": "On frontier",
    "radially_efficient_with_slack": "On frontier, with additional gaps",
    "below_frontier": "Below frontier",
}.get(str(r.frontier_status), str(r.frontier_status))

col2.metric(
    "Relative position",
    frontier_label,
)

col3.metric(
    "Benchmark peers",
    str(r.reference_peers),
)

st.caption(
    "The efficiency score and benchmark peers shown here come from the "
    "baseline DEA model. Benchmark peers are mathematical reference points "
    "within the model, not airlines that the selected carrier should directly copy."
)

# Keep the more technical DEA outputs available for users who want to inspect them.
with st.expander("View detailed DEA results"):
    st.markdown(
        """
        **How to read these results**

        - **Input gaps** show additional reductions in modeled inputs identified
          after the proportional DEA adjustment.
        - **Output gaps** show additional increases in modeled outputs identified
          by the model.
        - These are mathematical benchmarking results, not direct operating
          recommendations.
        """
    )

    st.write("**Input gaps:**", str(r.input_slacks))
    st.write("**Output gaps:**", str(r.output_slacks))
    st.write("**Benchmark peers:**", str(r.reference_peers))

# Keep data-eligibility details separate from the main benchmark interpretation.
with st.expander("Carrier coverage and DEA eligibility"):
    st.caption(
        "The DEA analysis uses only carriers that meet the required reporting "
        "and data-coverage criteria. This table shows which carriers are included "
        "and why others may be excluded."
    )

    table(
        carrier,
        [
            "carrier",
            "carrier_name",
            "active_months",
            "operated_flights",
            "observed_aircraft",
            "distinct_destinations",
            "on_time_rate",
            "dea_eligible",
            "dea_exclusion_reason",
        ],
    )

with fleet:
    st.header("How intensively are carriers using their observed domestic aircraft?")
    st.write(
    "Explore how frequently aircraft appear in domestic operations and how many "
    "flying hours they record when active.")
    st.info(
    "These metrics describe aircraft observed in BTS domestic flight records. "
    "They are not measures of total aircraft availability because international "
    "flying, maintenance and other unobserved activity may be missing.")
    code = st.selectbox("Select reporting carrier", sorted(aircraft.carrier.unique()), format_func=label)
    subset = aircraft.loc[aircraft.carrier.eq(code)]
    row = summary.loc[summary.carrier.eq(code)].iloc[0]
    total = st.columns(4)
    total[0].metric("Aircrafts observed", f"{len(subset):,}")
    total[1].metric("Domestic flights analyzed", f"{int(row.valid_domestic_legs):,}")
    total[2].metric("Median flying hours / active day", f"{row.median_tail_block_hours_per_active_day:.2f}")
    total[3].metric("Median share of active days", f"{row.median_tail_active_day_ratio:.1%}")
    st.caption("Medians are across observed tail combinations, not a percentage of aircraft capacity. "
               "Active-day ratio divides observed active domestic dates by days between first and last "
               "observed valid-duration domestic legs; it is not an aircraft's actual availability rate.")

    c = CoverageCriteria()
    filtered, excluded = analytics.sample(code, c)
    show_all = st.checkbox( "Show aircraft with limited observation history", value=False)
    plotted = subset if show_all else filtered

# Explain the chart sample in plain language.
st.caption(
    f"Showing {len(plotted):,} of {len(subset):,} observed aircraft. "
    f"{excluded:,} aircraft are excluded by default because they have limited "
    "domestic flight history in the dataset. This filter improves comparability "
    "and does not classify aircraft as underutilized."
)

if plotted.empty:

    st.info(
        "No aircraft have sufficient observation history to be included "
        "in the default charts for this carrier.")
else:  # Distribution of flying intensity across observed aircraft.
    fig_hours = px.histogram( plotted, x="block_hours_per_observed_active_day",
        nbins=35,
        labels={
            "block_hours_per_observed_active_day":
                "Domestic flying hours per active day"},
        title="How intensively are observed aircraft used when active?", )
    st.plotly_chart( fig_hours, use_container_width=True, )
    st.caption(   "Shows the distribution of recorded domestic flying hours on days "
        "when each aircraft appears in the BTS dataset.")
    # Compare how frequently each aircraft appears with how much it flies
    # on the days when it is active.
    fig_activity = px.scatter( plotted,
        x="observed_active_day_ratio",
        y="block_hours_per_observed_active_day",
        hover_data=[ "tail_num", "completed_flights","observed_active_days",],
        labels={
            "observed_active_day_ratio":
                "Share of observed days with domestic flights",
            "block_hours_per_observed_active_day":
                "Domestic flying hours per active day",
            "tail_num":
                "Aircraft tail number",
            "completed_flights":
                "Domestic flights observed",
            "observed_active_days":
                "Days with observed domestic flights",},
        title="Aircraft activity profile",)

    st.plotly_chart(
        fig_activity,
        use_container_width=True,)

    st.caption(
        "Aircraft toward the upper-right appear more frequently in domestic "
        "operations and record more flying hours when active. Lower activity "
        "does not necessarily imply spare capacity because other operations "
        "may not be captured in this dataset.")

    # Detailed aircraft-level metrics for users who want to inspect
    # the underlying observations.
    with st.expander("View aircraft-level activity data"):
        table(plotted.sort_values("completed_flights", ascending=False, ),
            [  "tail_num",
                "completed_flights",
                "observed_active_days",
                "observed_span_days",
                "block_hours_per_observed_active_day",
                "legs_per_observed_active_day",
                "observed_active_day_ratio",
                "observed_domestic_block_hours_per_calendar_day",],)
# Build a monthly timeline for the selected carrier.
monthly_carrier = (
    monthly.loc[monthly.carrier.eq(code)]
    .sort_values(["year", "month"])
    .copy())

monthly_carrier["period"] = pd.to_datetime(
    dict(
        year=monthly_carrier.year,
        month=monthly_carrier.month,
        day=1,))

# Convert recorded block minutes into hours for easier interpretation.
monthly_carrier["recorded_block_hours"] = (
    monthly_carrier["recorded_block_minutes"] / 60)

fig_monthly = px.line( monthly_carrier,
    x="period",
    y="recorded_block_hours",
    markers=True,
    labels={
        "period": "Month",
        "recorded_block_hours": "Recorded domestic flying hours",},
    title="Monthly domestic flying activity",)

st.plotly_chart(
    fig_monthly,
    use_container_width=True,)

st.caption(
    "Monthly changes may reflect seasonality, network deployment, maintenance, "
    "international assignments, storage, re-registration, or data coverage. "
    "These observations are descriptive and are not used to classify aircraft "
    "as available for redeployment.")
with insights:

    st.header("Compare airline operating models")

    st.write(
        "Compare carriers across operating scale, network breadth, aircraft activity "
        "and service reliability to understand how different airline models are positioned."
    )

    # Business-friendly labels shown on the dashboard.
    # The underlying column names remain unchanged.
    fields = {
        "Flights operated":
            "operated_flights",

        "Destinations served":
            "distinct_destinations",

        "Flights per observed aircraft":
            "flights_per_observed_aircraft",

        "Flying hours per active aircraft-day":
            "observed_domestic_block_hours_per_active_tail_day",

        "Median aircraft flying hours per active day":
            "median_tail_block_hours_per_active_day",

        "On-time arrival rate":
            "on_time_rate",

        "Cancellation rate":
            "cancellation_rate",
    }

    left, right = st.columns(2)

    xname = left.selectbox(
        "Compare on horizontal axis",
        list(fields),
        index=1,
    )

    yname = right.selectbox(
        "Compare on vertical axis",
        list(fields),
        index=2,
    )

    fig = px.scatter(
        summary,
        x=fields[xname],
        y=fields[yname],
        text="carrier",
        hover_data=[
            "carrier_name",
            "active_months",
        ],
        labels={
            fields[xname]: xname,
            fields[yname]: yname,
        },
        title="How carrier operating models compare",
    )

    fig.update_traces(
        textposition="top center"
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
    )

    st.markdown(
        """
        **How to read this chart**

        - **High flights per aircraft + narrower network:** more concentrated,
          high-frequency operations
        - **Broader network + lower flight frequency:** greater network reach
          with a different deployment model
        - **Higher flying hours + fewer flights:** may indicate longer average missions
        - **Similar scale but different on-time performance:** may point to differences
          in network structure or operational execution

        These patterns describe differences in operating models. They do not by
        themselves show that one strategy is better than another.
        """
    )

    st.caption(
        "The comparison is descriptive. Differences may reflect business model, "
        "aircraft mix, route structure and international operations that are not "
        "fully captured in this domestic dataset."
    )

    # Keep the detailed carrier-level data available without putting it
    # in the main dashboard view.
    with st.expander("View carrier-level operating data"):

        table(
            summary.sort_values(
                "operated_flights",
                ascending=False,
            ),
            [
                "carrier",
                "carrier_name",
                "active_months",
                "operated_flights",
                "observed_aircraft",
                "distinct_destinations",
                "flights_per_observed_aircraft",
                "valid_domestic_legs",
                "valid_duration_leg_coverage",
                "observed_domestic_block_hours_per_active_tail_day",
                "on_time_rate",
                "cancellation_rate",
            ],
        )

        st.caption(
            "Aircraft counts refer to tail numbers observed in the BTS domestic "
            "flight records, not verified total airline fleet size."
        )


# Keep technical data definitions separate from the main dashboard.
with st.expander("Data source and methodology"):

    st.markdown(
        f"""
        **Source:** {manifest["source"]}

        **Analysis period:** {manifest["start"]} to {manifest["end"]}

        **Monthly source files:** {len(manifest["archives"])}

        **Scheduled flight records:** {manifest["scheduled_rows"]:,}

        **Non-cancelled flight records:** {manifest["operated_rows"]:,}
        """
    )

    st.markdown(
        """
        **Key definitions**

        - **Flights operated:** scheduled flights that were not cancelled.
          This population can include diverted flights.
        - **Domestic flights with usable operating-time data:** non-diverted
          flights with a valid aircraft tail number and usable elapsed-time data.
        - **On-time arrival:** an eligible flight arriving less than 15 minutes
          after its scheduled arrival time.
        - **Observed aircraft:** aircraft tail numbers appearing in the BTS
          domestic flight records; this is not a verified total fleet inventory.
        - **Flying hours per active aircraft-day:** recorded domestic flying hours
          divided by the number of aircraft-days with observed domestic activity.
          It is not a true fleet-capacity utilization rate.
        """
    )

    st.caption(
        "Original BTS archive names, source URLs, record counts and SHA-256 hashes "
        "are stored in `results/ltm_2026/provenance.json`. "
        "Detailed model assumptions are documented in `docs/METHODOLOGY.md`."
    )