# Methods, denominators and interpretation

## Reporting population

The analysis population is the **national U.S. domestic Reporting Carrier On-Time Performance** flight records for August 2025–July 2026. The unit for DEA is the **reporting operating-carrier code**, not an airline holding company. The observed tail number is not a fleet-inventory record; separate codes and code changes may represent distinct operational reporting populations. There are 14 reporting carriers in the snapshot; 12 meet the pre-specified eligibility criteria for DEA (12 active reporting months, at least 10,000 non-cancelled flights, positive model inputs/output). Two carriers with shorter reporting windows remain in descriptive tables but are omitted from the DEA peer set.

## Exact KPI populations

| Measure | Formula / interpretation |
|---|---|
| Scheduled records | All source records; includes cancellations. |
| Non-cancelled flights | Records with `Cancelled == 0`; **includes diverted flights**. |
| Completed, valid-duration domestic legs | Non-cancelled, non-diverted records with an observed tail number and `0 < ActualElapsedTime <= 1440` minutes. These are aircraft-level observations, a smaller population than all non-cancelled records. |
| Observed carrier–tail pairs | Number of unique nonblank tail numbers associated with non-cancelled domestic records per reporting carrier; **not** an airline's owned, leased or available fleet. |
| Eligible arrivals | Non-cancelled, non-diverted flights with recorded `ArrDelay`. |
| On-time arrival rate | Eligible arrivals with `ArrDelay < 15` minutes divided by eligible arrivals. Cancellations/diversions/missing-delay records are **not counted as late** in this specific rate. |
| Recorded domestic block minutes | Sum of valid `ActualElapsedTime` on non-cancelled, non-diverted flights. Gate-to-gate elapsed time is not the same as air time, available block hours, or verified asset capacity. |
| Observed active-day ratio | Distinct dates with valid-duration domestic activity divided by inclusive days from first to last *observed qualifying domestic flight*. Days without a recorded domestic flight may involve international operations, maintenance, relocation, storage, or omitted source coverage. |
| Block hours per observed active day | A tail's recorded domestic block minutes / 60 / qualifying observed active domestic days. Does not measure the fraction of hours the aircraft was available. |
| Block hours per full calendar day | A tail's recorded domestic block minutes / 60 / 365. This is *observed domestic flight exposure* per day, not an available-capacity utilization fraction. |
| Flights per observed aircraft | Carrier-level non-cancelled flight records / observed carrier-tail count. **Not** a measure of annual flights per verified airline fleet aircraft. |
| Carrier aggregate domestic block hours per observed active tail-day | Sum of recorded carrier domestic block minutes / 60 / sum of qualifying observed tail-active dates. A weighted descriptive mean, **not** the median of tail averages nor a true capacity utilization rate. |

The `recorded_block_minutes` carrier and aircraft totals reconcile exactly in the supplied snapshot. A missing/invalid duration or missing tail can reduce the aircraft-level valid-duration sample, without making the non-cancelled flight count incorrect. All activity distributions default to a *chart-coverage screen*: at least 300 qualifying domestic legs, at least 300 inclusive first-to-last observed span days, and at least 120 qualifying active domestic dates. These thresholds are a transparent **presentation choice**, not a calibrated statistical outlier rule. The dashboard shows the number of excluded thin-coverage observations and permits viewing the full population. It makes no individual-aircraft actionability claims.

## CCR Data Envelopment Analysis

For each eligible carrier \(o\), the input-oriented, constant-returns-to-scale CCR model solves

\[
\min_{\theta,\lambda}\theta\quad\text{subject to}\quad
\sum_j\lambda_j x_{ij}\le\theta x_{io},\qquad
\sum_j\lambda_j y_{rj}\ge y_{ro},\qquad
\lambda_j\ge0,\quad 0\le\theta\le1.
\]

A second linear program fixes the radial score at its stage-one optimum and maximizes normalized input/output slacks. The program performs its own strictly positive column normalization; exported slacks are converted **back to original measurement units**. A radial score of 1 with positive non-radial slack is distinguished from zero-slack frontier membership.

**Baseline inputs:** observed carrier–tail count and number of distinct domestic destinations served on non-cancelled flights. **Baseline outputs:** non-cancelled domestic flights and eligible on-time arrival **counts**, not on-time percentage. The on-time count is a subset of flight volume, so two outputs are not independent measurements of output. Destinations as a minimized *input* is one debatable network-cost assumption, not a normative claim that airlines should reduce their route networks.

**Sensitivity specifications:** `volume_only` uses flight count as sole output; `network_as_output` treats destinations as a service output and uses aircraft as the only input; `block_hours_exposure` replaces flight-count outputs with recorded domestic block minutes. The block-minute model is not seat capacity, available seat miles, profit, or verified aircraft capacity. All model variants are shown separately; score ranges across them are *specification differences, not sampling uncertainty or historical change*.

DEA scores measure relative position in a small (12-carrier), heterogeneous peer population. Regional feeders, dense short-haul operators, and airlines with substantial longer-stage or international flying are **not operationally interchangeable**. Two frontier carriers can represent very different operating models. Neither reference-peer weights nor baseline input-slack quantities should be translated into a literal instruction to remove aircraft, terminate destinations or redeploy a fleet.

## What this project deliberately does not do

No aircraft is flagged as underutilized or available for maintenance substitution. International/ferry flights, crew schedules, maintenance releases, verified equipment type and total fleet inventory are not present. This project does not optimize rotations, forecast fleet demand, estimate financial performance, or infer causality from cross-carrier correlations.
