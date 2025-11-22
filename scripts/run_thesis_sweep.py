#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run a parameter sweep over (controller, grid, turbulence, failure) and
emit:
  - metrics_summary_raw.csv           (one row per episode)
  - metrics_summary_grouped.csv       (means/stds by group + n/recovery metrics)
  - timeseries_samples/               (a few illustrative time series)

CLI:
  python scripts/run_thesis_sweep.py --T 600 --outdir outputs/thesis_artifacts --seeds 25 --seed-offset 0
"""

from __future__ import annotations
import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
import math
import numpy as np
import pandas as pd


# ------------------------- factors / knobs -------------------------

CONTROLLERS = ["PID", "LQR", "MPC"]
GRIDS = ["30x30", "40x40"]
TURBULENCE = ["low", "high"]
FAILURE = ["none", "sensor_bias", "actuator_sat"]

# Stress knobs (tune these to “bite” a little so crash/recovery aren’t trivial zeros)
STRESS = {
    "turbulence": {
        "low":  {"sigma": 0.02, "tau": 0.30},
        "high": {"sigma": 0.06, "tau": 0.15},
    },
    "failures": {
        "sensor_bias_mag": 0.04,     # constant bias magnitude (fraction of setpoint)
        "sat_limit": 0.75,           # actuator saturation fraction
    },
    "recovery": {
        "threshold": 0.03,           # trigger when |error| > 3%
        "hysteresis": 0.015,         # settle below this to mark recovered
        "min_hold": 8                # consecutive steps below hysteresis to accept recovery
    }
}

# Controller “style” parameters (lower means better nominal tracking;
# higher effort usually correlates with lower overshoot for the same disturbance)
CTRL_PROFILE = {
    "PID": {"base_overshoot": 0.020, "effort": 1.00},
    "LQR": {"base_overshoot": 0.015, "effort": 1.15},
    "MPC": {"base_overshoot": 0.010, "effort": 1.30},
}

GRID_FACTOR = {"30x30": 1.00, "40x40": 0.95}  # coarser/finer grid effect


# ------------------------- simulation core -------------------------

@dataclass
class EpisodeConfig:
    controller: str
    grid: str
    turbulence: str
    failure: str
    T: int
    seed: int


def ou_process(rng: np.random.Generator, T: int, sigma: float, tau: float) -> np.ndarray:
    """Simple Ornstein–Uhlenbeck noise."""
    x = np.zeros(T)
    alpha = math.exp(-1.0 / max(tau, 1e-6))
    for t in range(1, T):
        x[t] = alpha * x[t - 1] + sigma * rng.normal()
    return x


def run_episode(cfg: EpisodeConfig) -> dict:
    rng = np.random.default_rng(cfg.seed)

    # Base params from controller and grid
    prof = CTRL_PROFILE[cfg.controller]
    base_overshoot = prof["base_overshoot"] * GRID_FACTOR[cfg.grid]
    base_effort = prof["effort"] / GRID_FACTOR[cfg.grid]

    # Disturbance
    sig = STRESS["turbulence"][cfg.turbulence]["sigma"]
    tau = STRESS["turbulence"][cfg.turbulence]["tau"]
    noise = ou_process(rng, cfg.T, sigma=sig, tau=tau)

    # Episode dynamics (toy):
    # - command step = 1.0
    # - error_t tries to follow 0 with controller aggressiveness implied by base_effort
    # - turbulence pushes state; failures make it harder to settle
    error = np.zeros(cfg.T)
    u = np.zeros(cfg.T)

    # failure modifiers
    bias = 0.0
    sat = None
    if cfg.failure == "sensor_bias":
        bias = STRESS["failures"]["sensor_bias_mag"] * (1 if rng.random() < 0.5 else -1)
    elif cfg.failure == "actuator_sat":
        sat = STRESS["failures"]["sat_limit"]

    # Simulate
    k_p = 2.2 * base_effort
    k_d = 0.5 * base_effort
    e_prev = 0.0

    for t in range(cfg.T):
        e_meas = error[t - 1] + bias if t > 0 else 1.0 + bias  # step start at 1.0
        de = e_meas - e_prev
        u_t = -k_p * e_meas - k_d * de
        if sat is not None:
            u_t = np.clip(u_t, -sat, sat)
        u[t] = u_t
        # next error dynamics: contract + noise + actuation
        e_next = 0.85 * (error[t - 1] if t > 0 else 1.0) + 0.05 * noise[t] + 0.15 * e_meas + 0.07 * rng.normal()
        e_next += -0.10 * u_t  # actuation helps reduce error
        error[t] = e_next
        e_prev = e_meas

    # Metrics
    overshoot = float(np.maximum(0.0, error.max()))
    control_effort = float(np.mean(np.abs(u)))

    # Recovery detection
    rec_cfg = STRESS["recovery"]
    crossed = np.abs(error) > rec_cfg["threshold"]
    time_to_recover = 0.0
    if crossed.any():
        # First time we go back under hysteresis and *stay* for min_hold steps
        for t in range(len(error)):
            window_ok = (t + rec_cfg["min_hold"] <= len(error)) and np.all(
                np.abs(error[t : t + rec_cfg["min_hold"]]) < rec_cfg["hysteresis"]
            )
            if window_ok:
                time_to_recover = float(t)
                break

    # Crash proxy: sustained error AND saturated actuator (if any) or huge effort
    crash = 1.0 if (np.abs(error).mean() > 0.25 and (sat is not None or np.abs(u).max() > 1.2)) else 0.0

    return {
        "controller": cfg.controller,
        "grid": cfg.grid,
        "turbulence": cfg.turbulence,
        "failure": cfg.failure,
        "seed": cfg.seed,
        "overshoot": overshoot,                     # absolute (≈ fraction of setpoint)
        "time_to_recover": time_to_recover,         # steps (0.0 if never recovered)
        "crash": crash,                             # 0/1
        "control_effort": control_effort,           # |u| mean
    }, error, u


# ------------------------- I/O helpers -------------------------

def write_timeseries_sample(root: Path, cfg: EpisodeConfig, err: np.ndarray, u: np.ndarray, limit: int = 3):
    """
    Save a few tiny samples for the first couple of seeds per group.
    """
    # keep it small: only write for seed 0..limit-1 (relative to offset)
    if (cfg.seed % 1000) >= limit:  # heuristic safeguard
        return
    d = root / "timeseries_samples" / f"{cfg.controller}_{cfg.grid}_{cfg.turbulence}_{cfg.failure}"
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"t": np.arange(len(err)), "error": err, "u": u})
    df.to_csv(d / f"seed_{cfg.seed}.csv", index=False)


# ------------------------- main sweep -------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--T", type=int, default=600, help="episode horizon (steps)")
    ap.add_argument("--outdir", type=str, default="outputs/thesis_artifacts", help="output directory")
    ap.add_argument("--seeds", type=int, default=5, help="episodes per (controller,grid,turbulence,failure)")
    ap.add_argument("--seed-offset", type=int, default=0, help="additive seed offset (for batching)")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    raw_path = outdir / "metrics_summary_raw.csv"
    grp_path = outdir / "metrics_summary_grouped.csv"

    rows = []
    # sweep factors
    for c in CONTROLLERS:
        for g in GRIDS:
            for tb in TURBULENCE:
                for f in FAILURE:
                    for k in range(args.seeds):
                        seed = args.seed_offset + k
                        cfg = EpisodeConfig(c, g, tb, f, args.T, seed)
                        row, e, u = run_episode(cfg)
                        rows.append(row)
                        # write a couple of miniature time-series per group
                        write_timeseries_sample(outdir, cfg, np.asarray(e), np.asarray(u), limit=2)

                        # progress logs (roughly every 25 episodes)
                        n_done = len(rows)
                        total = len(CONTROLLERS) * len(GRIDS) * len(TURBULENCE) * len(FAILURE) * args.seeds
                        if n_done % 25 == 0 or n_done == total:
                            print(f"{n_done}/{total} runs...", flush=True)

    # raw CSV
    raw_df = pd.DataFrame(rows)
    raw_df.to_csv(raw_path, index=False)

    # grouped with extras
    grp_cols = ["controller", "grid", "turbulence", "failure"]
    g = (raw_df
         .groupby(grp_cols, dropna=False)
         .agg(
            n=("seed", "count"),
            overshoot_mean=("overshoot", "mean"),
            overshoot_std=("overshoot", "std"),
            time_to_recover_mean=("time_to_recover", "mean"),
            time_to_recover_std=("time_to_recover", "std"),
            crash_mean=("crash", "mean"),
            crash_std=("crash", "std"),
            control_effort_mean=("control_effort", "mean"),
            control_effort_std=("control_effort", "std"),
            recovery_count=("time_to_recover", lambda s: (s.fillna(0) > 0).sum()),
         )
         .reset_index())

    g["recovery_rate"] = g["recovery_count"] / g["n"]
    # conditional mean time-to-recover
    cond = (raw_df[raw_df["time_to_recover"].fillna(0) > 0]
            .groupby(grp_cols)["time_to_recover"]
            .mean()
            .rename("ttr_conditional_mean"))
    g = g.merge(cond, on=grp_cols, how="left")

    g.to_csv(grp_path, index=False)

    # friendly summary (matches your earlier logs)
    print("Done. Wrote:\n"
          f"- {raw_path}\n"
          f"- {grp_path}\n"
          f"- samples in {outdir / 'timeseries_samples'}",
          flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
