#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run a parameter sweep over (controller, grid, turbulence, failure) and emit:
  - metrics_summary_raw.csv
  - metrics_summary_grouped.csv
  - timeseries_samples/ (few samples)

Example:
  python scripts/run_thesis_sweep.py --T 600 --outdir outputs/thesis_artifacts --seeds 25 --seed-offset 0
"""
from __future__ import annotations
import argparse, math, sys
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd

CONTROLLERS = ["PID", "LQR", "MPC"]
GRIDS = ["30x30", "40x40"]
TURBULENCE = ["low", "high"]
FAILURE = ["none", "sensor_bias", "actuator_sat"]

STRESS = {
    "turbulence": {
    "low":  {"sigma": 0.012, "tau": 0.45},
    "high": {"sigma": 0.035, "tau": 0.22},
},
    "failures": {
        "sensor_bias_mag": 0.025,
        "sat_limit": 0.55,
    },
    "recovery": {
        "threshold": 0.03,
        "hysteresis": 0.015,
        "min_hold": 8
    }
}

CTRL_PROFILE = {
    "PID": {"base_overshoot": 0.030, "effort": 0.95},
    "LQR": {"base_overshoot": 0.018, "effort": 1.10},  
    "MPC": {"base_overshoot": 0.012, "effort": 1.35},  
}
GRID_FACTOR = {"30x30": 1.00, "40x40": 0.95}

@dataclass
class EpisodeConfig:
    controller: str; grid: str; turbulence: str; failure: str; T: int; seed: int

def ou_process(rng: np.random.Generator, T: int, sigma: float, tau: float) -> np.ndarray:
    x = np.zeros(T); alpha = math.exp(-1.0 / max(tau, 1e-6))
    for t in range(1, T): x[t] = alpha * x[t - 1] + sigma * rng.normal()
    return x

def run_episode(cfg: EpisodeConfig) -> tuple[dict, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(cfg.seed)
    prof = CTRL_PROFILE[cfg.controller]
    base_effort = prof["effort"] / GRID_FACTOR[cfg.grid]

    sig = STRESS["turbulence"][cfg.turbulence]["sigma"]
    tau = STRESS["turbulence"][cfg.turbulence]["tau"]
    noise = ou_process(rng, cfg.T, sigma=sig, tau=tau)

    error = np.zeros(cfg.T); u = np.zeros(cfg.T)

    bias = 0.0; sat = None
    if cfg.failure == "sensor_bias":
        bias = STRESS["failures"]["sensor_bias_mag"] * (1 if rng.random() < 0.5 else -1)
    elif cfg.failure == "actuator_sat":
        sat = STRESS["failures"]["sat_limit"]

    deadzone = 0.03
    if abs(u_t) < deadzone:
    u_t = 0.0

    k_p = 1.2 * base_effort; k_d = 0.3 * base_effort
    CONTRACT = 0.70; COUPLE = 0.08; ACTUATE = -0.08
    MAX_ABS_ERR = 2.0; DIVERGE_LIM = 1.4; DIVERGE_HOLD = 45
    diverge_count = 0; e_prev = 0.0

    for t in range(cfg.T):
        e_meas = error[t - 1] + bias if t > 0 else 1.0 + bias
        de = e_meas - e_prev
        u_t = -k_p * e_meas - k_d * de
        if sat is not None: u_t = np.clip(u_t, -sat, sat)
        u[t] = u_t

        e_prev_state = (error[t - 1] if t > 0 else 1.0)
        e_next = CONTRACT * e_prev_state + COUPLE * e_meas + 0.03 * noise[t] + 0.03 * rng.normal()
        e_next += ACTUATE * u_t
        e_next = float(np.clip(e_next, -MAX_ABS_ERR, MAX_ABS_ERR))
        error[t] = e_next; e_prev = e_meas

        if abs(e_next) > DIVERGE_LIM:
            diverge_count += 1
            if diverge_count >= DIVERGE_HOLD:
                error[t+1:] = 0.0; u[t+1:] = 0.0; break
        else:
            diverge_count = 0

    overshoot = float(min(max(0.0, error.max()), 2.0))
    rec_cfg = STRESS["recovery"]; crossed = np.abs(error) > rec_cfg["threshold"]
    time_to_recover = 0.0
    if crossed.any():
        for t in range(len(error)):
            ok = (t + rec_cfg["min_hold"] <= len(error)) and np.all(
                np.abs(error[t:t+rec_cfg["min_hold"]]) < rec_cfg["hysteresis"])
            if ok: time_to_recover = float(t); break

    sat_hits = float((np.abs(u) >= (sat if sat is not None else 10)).mean()) if len(u) else 0.0
    crash = 1.0 if (diverge_count >= DIVERGE_HOLD or np.abs(error).mean() > 0.35 or sat_hits > 0.25) else 0.0

    control_effort = float(min(np.mean(np.abs(u)), 2.0))

    return ({
        "controller": cfg.controller, "grid": cfg.grid, "turbulence": cfg.turbulence, "failure": cfg.failure,
        "seed": cfg.seed, "overshoot": overshoot, "time_to_recover": time_to_recover,
        "crash": crash, "control_effort": control_effort
    }, error, u)

def write_timeseries_sample(root: Path, cfg: EpisodeConfig, err: np.ndarray, u: np.ndarray, limit: int = 2):
    if (cfg.seed % 1000) >= limit: return
    d = root / "timeseries_samples" / f"{cfg.controller}_{cfg.grid}_{cfg.turbulence}_{cfg.failure}"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"t": np.arange(len(err)), "error": err, "u": u}).to_csv(d / f"seed_{cfg.seed}.csv", index=False)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--T", type=int, default=600)
    ap.add_argument("--outdir", type=str, default="outputs/thesis_artifacts")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--seed-offset", type=int, default=0)
    args = ap.parse_args()

    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    raw_path = outdir / "metrics_summary_raw.csv"; grp_path = outdir / "metrics_summary_grouped.csv"

    rows = []
    total = len(CONTROLLERS) * len(GRIDS) * len(TURBULENCE) * len(FAILURE) * args.seeds
    for c in CONTROLLERS:
        for g in GRIDS:
            for tb in TURBULENCE:
                for f in FAILURE:
                    for k in range(args.seeds):
                        seed = args.seed_offset + k
                        cfg = EpisodeConfig(c, g, tb, f, args.T, seed)
                        row, e, uu = run_episode(cfg)
                        rows.append(row)
                        write_timeseries_sample(outdir, cfg, np.asarray(e), np.asarray(uu), limit=2)
                        if len(rows) % 25 == 0 or len(rows) == total:
                            print(f"{len(rows)}/{total} runs...", flush=True)

    raw_df = pd.DataFrame(rows); raw_df.to_csv(raw_path, index=False)

    grp_cols = ["controller","grid","turbulence","failure"]
    g = (raw_df.groupby(grp_cols, dropna=False)
         .agg(n=("seed","count"),
              overshoot_mean=("overshoot","mean"),
              overshoot_std=("overshoot","std"),
              time_to_recover_mean=("time_to_recover","mean"),
              time_to_recover_std=("time_to_recover","std"),
              crash_mean=("crash","mean"),
              crash_std=("crash","std"),
              control_effort_mean=("control_effort","mean"),
              control_effort_std=("control_effort","std"),
              recovery_count=("time_to_recover", lambda s: (s.fillna(0) > 0).sum()))
         .reset_index())
    g["recovery_rate"] = g["recovery_count"] / g["n"]
    cond = (raw_df[raw_df["time_to_recover"].fillna(0) > 0]
            .groupby(grp_cols)["time_to_recover"].mean().rename("ttr_conditional_mean"))
    g = g.merge(cond, on=grp_cols, how="left")
    g.to_csv(grp_path, index=False)

    print("Done. Wrote:\n"
          f"- {raw_path}\n- {grp_path}\n- samples in {outdir / 'timeseries_samples'}", flush=True)

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: sys.exit(130)
