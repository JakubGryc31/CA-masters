# scripts/qc_after_sweep.py
import argparse, json, sys
from pathlib import Path
import pandas as pd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, help="Path to metrics_summary_raw.csv")
    ap.add_argument("--outdir", required=True, help="Output directory (same as sweep)")
    ap.add_argument("--min_seeds", type=int, default=15, help="Min episodes per group")
    args = ap.parse_args()

    raw = pd.read_csv(args.raw)

    # required columns in raw
    req = ["controller","grid","turbulence","failure","seed",
           "overshoot","time_to_recover","crash","control_effort"]
    missing = [c for c in req if c not in raw.columns]
    if missing:
        print(f"[qc] Missing columns in raw: {missing}", file=sys.stderr)
        sys.exit(2)

    # derive indicators
    raw["has_recovery"] = raw["time_to_recover"].fillna(0) > 0

    grp_cols = ["controller","grid","turbulence","failure"]
    g = (raw
         .groupby(grp_cols, dropna=False)
         .agg(
            n=("seed","count"),
            overshoot_mean=("overshoot","mean"),
            overshoot_std=("overshoot","std"),
            time_to_recover_mean=("time_to_recover","mean"),
            time_to_recover_std=("time_to_recover","std"),
            crash_mean=("crash","mean"),
            crash_std=("crash","std"),
            control_effort_mean=("control_effort","mean"),
            control_effort_std=("control_effort","std"),
            recovery_count=("has_recovery","sum"),
         )
         .reset_index())

    # derived QC metrics
    g["recovery_rate"] = g["recovery_count"] / g["n"]
    # conditional mean TTR (only where recoveries happened)
    cond = (raw[raw["has_recovery"]]
            .groupby(grp_cols)["time_to_recover"]
            .mean()
            .rename("ttr_conditional_mean"))
    g = g.merge(cond, on=grp_cols, how="left")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # save the upgraded grouped CSV (will be read by dashboard)
    grouped_path = outdir / "metrics_summary_grouped.csv"
    g.to_csv(grouped_path, index=False)
    print(f"[qc] wrote upgraded grouped CSV -> {grouped_path}")

    # QC report
    under = g[g["n"] < args.min_seeds].copy()
    report = {
        "total_groups": int(len(g)),
        "min_seeds_required": args.min_seeds,
        "groups_below_threshold": int(len(under)),
        "examples_below": under.head(10).to_dict(orient="records"),
        "ok": len(under) == 0
    }
    (outdir / "qc_report.json").write_text(json.dumps(report, indent=2))
    (outdir / "qc_report.md").write_text(
        f"# QC report\n\n"
        f"- groups: **{len(g)}**\n"
        f"- min_seeds: **{args.min_seeds}**\n"
        f"- groups under threshold: **{len(under)}**\n\n"
        f"First 10 under-threshold groups:\n\n{under.head(10).to_markdown(index=False)}\n"
    )
    print(f"[qc] min_seeds={args.min_seeds}, groups<{args.min_seeds}: {len(under)}")

    # non-zero exit to fail the job if QC not met
    if len(under) > 0:
        print("[qc] FAIL: not enough seeds per group.", file=sys.stderr)
        sys.exit(3)

if __name__ == "__main__":
    main()
