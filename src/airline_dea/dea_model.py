"""Validated input-oriented CCR DEA with a lexicographic radial/slack solution.

The stage-one objective is min theta subject to X.T @ lam <= theta*x0,
Y.T @ lam >= y0, and lam >= 0. Stage two fixes theta at its
optimal stage-one value and maximizes normalized slacks.
Neither score nor slack establishes causal managerial performance.
"""
# DEA to answer if I can build a combination of other airlines that 
# produces at least as much as airline X, using a smaller share of X's inputs?
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import linprog


@dataclass(frozen=True)
class DEAResult:
    efficiency: pd.Series
    lambdas: pd.DataFrame
    input_slacks: pd.DataFrame
    output_slacks: pd.DataFrame

    def peer_summary(self, tol: float = 1e-6) -> pd.DataFrame:
        rows = []
        for dmu, efficiency in self.efficiency.items():
            peers = self.lambdas.loc[dmu]
            visible = peers[peers > tol].sort_values(ascending=False)
            rows.append({"carrier": dmu, "efficiency": efficiency,
                         "peers": ", ".join(f"{p} ({w:.3f})" for p, w in visible.items())})
        return pd.DataFrame(rows)
    # format the peer summary for readability like "WN (0.142), MQ (0.111)"

class DEAModel:
    """Solve CCR with nonnegative inputs, strictly positive inputs per DMU.

    Inputs and outputs must share an ordered, unique DMU index. For meaningful
    output weights, each DMU needs at least one strictly positive output.
    """

    def __init__(self, inputs: pd.DataFrame, outputs: pd.DataFrame, *, tolerance: float = 1e-7):
        if inputs.empty or outputs.empty or inputs.shape[1] == 0 or outputs.shape[1] == 0:
            raise ValueError("DEA requires at least one DMU, input and output")
        if not inputs.index.equals(outputs.index) or not inputs.index.is_unique:
            raise ValueError("Inputs/outputs must share a unique ordered DMU index")
        if inputs.columns.has_duplicates or outputs.columns.has_duplicates:
            raise ValueError("Duplicate DEA variable names")
        x, y = inputs.to_numpy(dtype=float), outputs.to_numpy(dtype=float)
        if not (np.isfinite(x).all() and np.isfinite(y).all()):
            raise ValueError("DEA inputs/outputs must be finite, without missing values")
        if (x <= 0).any() or (y < 0).any() or (y.sum(axis=1) <= 0).any():
            raise ValueError("DEA requires positive inputs and nonnegative, nonempty outputs")
        if (y.sum(axis=0) <= 0).any():
            raise ValueError("Every DEA output needs at least one positive observation")
        if not (0 < tolerance < 1e-3):
            raise ValueError("tolerance must be between zero and 1e-3")
        self.inputs, self.outputs = inputs.copy(), outputs.copy()
        self.dmus = inputs.index.tolist()
        # Positive rescaling by observed column maxima is unit invariant for CCR.
        # It also makes stage-two slack priorities comparable across units.
        self._xscale, self._yscale = x.max(axis=0), y.max(axis=0)
        self._X, self._Y = x / self._xscale, y / self._yscale
        self.tol = tolerance
    #checks the validity of the DEA model inputs and outputs before fitting

    def fit(self) -> DEAResult:
        scores = pd.Series(index=self.dmus, dtype=float, name="efficiency")
        peer_weights = pd.DataFrame(0., index=self.dmus, columns=self.dmus)
        input_slacks = pd.DataFrame(0., index=self.dmus, columns=self.inputs.columns)
        output_slacks = pd.DataFrame(0., index=self.dmus, columns=self.outputs.columns)
        for j, name in enumerate(self.dmus):
            score = self._radial_score(j)
            lam, si, so = self._slacks(j, score)
            scores.loc[name] = score
            peer_weights.loc[name] = lam
            # Return in the original measurement units, not scaled LP units.
            input_slacks.loc[name] = si * self._xscale
            output_slacks.loc[name] = so * self._yscale
        return DEAResult(scores, peer_weights, input_slacks, output_slacks)
    # loop over each carrier and solve 2 LPs: one for the radial score and one for the slacks

    # How much could this carrier proportionally reduce ALL inputs 
    # while still producing at least its current outputs

    def _radial_score(self, j: int) -> float: # j is the index of the carrier being evaluated
        n = len(self.dmus)
        x0, y0 = self._X[j], self._Y[j] # Get the current carrier's inputs and outputs
        c = np.r_[1., np.zeros(n)]
        a_in = np.column_stack([-x0, self._X.T])
        a_out = np.column_stack([np.zeros((self._Y.shape[1], 1)), -self._Y.T])
        res = linprog(c, A_ub=np.vstack([a_in, a_out]),
                      b_ub=np.r_[np.zeros(len(x0)), -y0],
                      bounds=[(0., 1.)] + [(0., None)] * n, method="highs")
        if not res.success:
            raise RuntimeError(f"DEA radial LP failed for {self.dmus[j]}: {res.message}")
        score = float(res.x[0])
        if score < -self.tol or score > 1 + self.tol:
            raise RuntimeError(f"DEA score outside [0,1] for {self.dmus[j]}: {score}")
        return min(1., max(0., score))

    #After making that proportional reduction, is there still 
    # any specific input excess or output shortfall left
    def _slacks(self, j: int, score: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        n, m, s = len(self.dmus), self._X.shape[1], self._Y.shape[1]
        c = np.r_[np.zeros(n), -np.ones(m + s)]
        a_in = np.column_stack([self._X.T, np.eye(m), np.zeros((m, s))])
        a_out = np.column_stack([self._Y.T, np.zeros((s, m)), -np.eye(s)])
        rhs = np.r_[score * self._X[j], self._Y[j]]
        res = linprog(c, A_eq=np.vstack([a_in, a_out]), b_eq=rhs,
                      bounds=[(0., None)] * (n + m + s), method="highs")
        if not res.success:
            # A strict stage-two failure must not be silently misreported as zero slack.
            raise RuntimeError(f"DEA slack LP failed for {self.dmus[j]}: {res.message}")
        lam, si, so = res.x[:n], res.x[n:n+m], res.x[n+m:]
        if not np.allclose(a_in @ res.x, rhs[:m], atol=self.tol, rtol=self.tol) or \
           not np.allclose(a_out @ res.x, rhs[m:], atol=self.tol, rtol=self.tol):
            raise RuntimeError(f"DEA slack LP residual above tolerance for {self.dmus[j]}")
        return lam, np.maximum(si, 0.), np.maximum(so, 0.)
