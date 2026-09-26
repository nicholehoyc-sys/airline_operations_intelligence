# Validation report — simplified LTM July 2026 release

## Checks performed on original and processed data

The **twelve original BTS ZIP archives supplied by the project author**, August 2025–July 2026, were compared byte-for-byte by SHA-256 against all twelve corresponding `results/ltm_2026/provenance.json` entries. **12/12 original source hashes match.** The source manifest records one CSV file, a BTS source URL and an individual source-row count for every reporting month. The archived months together span exactly the declared LTM reporting window.

The shipped descriptive carrier and aircraft-level files were reconciled as follows:

| Reconciliation | Result |
|---|---:|
| Scheduled flight records | 7,043,858 |
| Non-cancelled records (diversions included) | 6,915,477 |
| Diverted, non-cancelled records | 19,966 |
| Non-diverted records | 6,895,511 |
| Completed, valid-duration domestic legs with observed tail | 6,895,510 |
| Aircraft-level leg coverage of non-diverted records | 99.999985% |
| Total recorded domestic block minutes, **both** carrier and summed aircraft levels | 995,896,284 |
| Distinct reporting-carrier codes | 14 |
| Eligible DEA peer carriers | 12 |
| Observed carrier–tail combinations | 6,390 |
| Reporting months | 12 |

**Do not interchange these denominators:** the 6,915,477 non-cancelled records include diversions, while the aircraft activity series requires a completed non-diverted domestic leg, a valid tail and an eligible recorded elapsed time. The one-record gap between non-diverted flights and valid-duration aircraft legs in this particular snapshot does not imply that the datasets can be treated as definitionally identical in other periods. Their recorded block-minute totals reconcile exactly because both use the same valid-duration source filter.

### Coverage and distribution

The dashboard defaults to *descriptive chart coverage only*: ≥300 qualifying domestic legs, ≥300 days between first/last observed qualifying legs, and ≥120 distinct observed qualifying days. **4,954 / 6,390** carrier–tail observations meet these display criteria; **1,436** are excluded from the default distribution but can be included via the UI. Among the default chart sample, the median observed domestic block hours per active day is **9.364 hours** and the median within-observed-span active-day ratio is **0.907**. These are medians of flight-record proxies **not** actual total fleet utilization percentages, availability measurements, or a list of idle assets. Observation-coverage thresholds do not select outliers.

### DEA numerical and interpretive checks

The input-oriented CCR optimizer was **rerun from the supplied carrier metrics**. All twelve carrier scores under each of four specifications (`baseline`, `volume_only`, `network_as_output`, `block_hours_exposure`) reproduced the shipped results with maximum absolute score difference **0.0** at floating-point precision. The stored baseline rows also match their corresponding rows in the sensitivity file. Existing tests cover known DEA solutions, rescaling invariance and original-unit non-radial slack reporting.

In the baseline, **MQ and WN** have radial scores of **1.000** with no reported stage-two slack; this means only that they are modeled frontier observations for this peer set, **not** that they have identical operating models or are universally optimal airlines. G4 has a score of approximately **0.552** with destinations as a minimized input, compared with approximately **0.999** when destinations are treated as an output. Such a change is substantive production-model dependence, **not** a measured improvement in airline operations. The dashboard foregrounds the model definition and shows all four scores per carrier before users interpret frontier membership.

### Automated and interface tests

The streamlined automated suite includes the original small synthetic twelve-month BTS loader tests; known-solution DEA tests; real-snapshot flight-count and elapsed-minute reconciliation; full-model sensitivity checks; data-provenance rejection checks; no-spare-capacity-flag assertions; and a three-tab dashboard execution smoke test using a Streamlit rendering stub plus actual Plotly figure creation.

**Independent checks (Sep 2026):** all four DEA specifications were re-solved with a separate, unscaled textbook envelopment LP. The maximum absolute score difference from the shipped results was < 1e-14, and ranks, reference peers and slacks matched exactly. The Streamlit app was launched (Streamlit 1.64, Plotly 6) and all three tabs rendered without exceptions. A test now asserts that the pipeline's output schema (every CSV column and provenance key) is identical to the shipped snapshot.

   **End-to-end regeneration (25 Sep 2026):** all 12 raw BTS archives were downloaded with `src/acquire_bts.py` and the full 7,043,858-record pipeline was rerun with `src/run_ltm.py` (Windows, Python 3.10). `src/compare_results.py` confirmed 12/12 archive SHA-256 hashes and row counts match, and every output table matches the shipped `results/ltm_2026/` snapshot.
