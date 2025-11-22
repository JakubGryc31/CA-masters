import os, sys, json, argparse, itertools
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
from src.experiments.sim import run
from src.experiments.scenarios import turbulence_schedule_factory
from src.analysis.metrics import metrics_from_log
from src.analysis.plots import plot_timeseries

def parse_grid(s: str):
    s = s.lower().replace(' ', '')
    if 'x' not in s:
        raise argparse.ArgumentTypeError("Grid must be like 30x30")
    a, b = s.split('x')
    return int(a), int(b)

def get_controllers(ga_best_path=None):
    ctrls = {
        'PID-baseline': dict(kp=0.8, ki=0.05, kd=0.12),
        'PD':           dict(kp=0.8, ki=0.0,  kd=0.12),
        'P-only':       dict(kp=0.8, ki=0.0,  kd=0.0),
    }
    # GA tuned PID (fallback if file missing)
    if ga_best_path and Path(ga_best_path).exists():
        try:
            best = json.loads(Path(ga_best_path).read_text())
            ctrls['PID-GA'] = dict(kp=float(best['kp']), ki=float(best['ki']), kd=float(best['kd']))
        except Exception:
            ctrls['PID-GA'] = dict(kp=0.15, ki=0.01, kd=0.006)
    else:
        ctrls['PID-GA'] = dict(kp=0.15, ki=0.01, kd=0.006)
    return ctrls

def main():
    ap = argparse.ArgumentParser(description="Run thesis experiment sweep and aggregate results.")
    ap.add_argument("--grids", default="30x30,40x40", help="Comma-separated grids, e.g. 30x30,40x40")
    ap.add_argument("--maneuvers", default="0.2,0.3,0.5", help="Comma-separated pitch-up deltas")
    ap.add_argument("--turbulence", default="low,med,high", help="Levels to sweep")
    ap.add_argument("--failure", default="none,early,late", help="Failure windows")
    ap.add_argument("--seeds", default="0,1,2,3,4", help="Comma-separated integer seeds")
    ap.add_argument("--T", type=int, default=600, help="Simulation horizon (steps)")
    ap.add_argument("--pitch_time", type=int, default=200, help="When to apply pitch-up")
    ap.add_argument("--ga-best", default="", help="Path to GA best PID json, e.g. outputs/best_pid.json")
    ap.add_argument("--outdir", default="outputs/thesis_artifacts", help="Where to write artifacts")
    ap.add_argument("--max-runs", type=int, default=0, help="Stop after N runs (0 = no cap)")
    args = ap.parse_args()

    grids = [parse_grid(g) for g in args.grids.split(",") if g.strip()]
    man_list = [float(x) for x in args.maneuvers.split(",") if x.strip()]
    turb_levels = [x.strip().lower() for x in args.turbulence.split(",") if x.strip()]
    fail_modes = [x.strip().lower() for x in args.failure.split(",") if x.strip()]
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]

    OUT = Path(args.outdir); OUT.mkdir(parents=True, exist_ok=True)
    timeseries_dir = OUT / "timeseries_samples"; timeseries_dir.mkdir(exist_ok=True)

    ctrls = get_controllers(args.ga_best)

    # turbulence schedules by level
    def make_sched(level):
        if level == 'low':
            return turbulence_schedule_factory(low=0.0, mid=0.2, late=0.05, t1=int(0.3*args.T), t2=int(0.6*args.T))
        if level == 'med':
            return turbulence_schedule_factory(low=0.0, mid=0.35, late=0.1, t1=int(0.3*args.T), t2=int(0.6*args.T))
        if level == 'high':
            return turbulence_schedule_factory(low=0.1, mid=0.5,  late=0.2, t1=int(0.3*args.T), t2=int(0.6*args.T))
        raise ValueError(f"Unknown turbulence level: {level}")

    # failure windows relative to T
    def failure_window(mode):
        if mode == 'none':  return None
        if mode == 'early': return (int(0.35*args.T), int(0.35*args.T) + 20)
        if mode == 'late':  return (int(0.65*args.T), int(0.65*args.T) + 40)
        raise ValueError(f"Unknown failure mode: {mode}")

    rows = []
    total = len(grids) * len(man_list) * len(turb_levels) * len(fail_modes) * len(ctrls) * len(seeds)
    done = 0

    for (gh, gw), man, turb, fail, (ctrl_name, ctrl_gains), seed in itertools.product(
        grids, man_list, turb_levels, fail_modes, ctrls.items(), seeds
    ):
        sched = make_sched(turb)
        fw = failure_window(fail)
        log = run(
            T=args.T, seed=seed, a_ref=0.0,
            pitch_up_at=args.pitch_time, pitch_up_delta=man,
            failure_window=fw, turb_sched=sched,
            grid_h=gh, grid_w=gw,
            **ctrl_gains
        )
        metrics, df = metrics_from_log(log)
        row = {
            'grid': f"{gh}x{gw}",
            'maneuver': man,
            'turbulence': turb,
            'failure': fail,
            'controller': ctrl_name,
            'seed': seed,
            **metrics
        }
        rows.append(row)

        # Save one sample timeseries + plots per scenario×controller (first seed encountered)
        sample_name = f"g{gh}x{gw}_man{man}_t{turb}_f{fail}_{ctrl_name}".replace('.', 'p')
        sample_csv = timeseries_dir / f"{sample_name}.csv"
        if not sample_csv.exists():
            df.to_csv(sample_csv, index=False)
            plot_timeseries(df, str(timeseries_dir / sample_name))

        done += 1
        if done % 25 == 0:
            print(f"{done}/{total} runs...")
        if args.max_runs and done >= args.max_runs:
            break

    # Raw results and grouped mean ± std
    df_raw = pd.DataFrame(rows)
    df_raw.to_csv(OUT / "metrics_summary_raw.csv", index=False)

    group_cols = ['grid', 'maneuver', 'turbulence', 'failure', 'controller']
    agg_cols = ['overshoot', 'time_to_recover', 'stability_variance', 'control_effort', 'crash']
    grouped = df_raw.groupby(group_cols)[agg_cols].agg(['mean', 'std']).reset_index()
    grouped.columns = ['_'.join(col).strip('_') if isinstance(col, tuple) else col for col in grouped.columns]
    grouped.to_csv(OUT / "metrics_summary_grouped.csv", index=False)

    print(f"Done. Wrote:\n - {OUT/'metrics_summary_raw.csv'}\n - {OUT/'metrics_summary_grouped.csv'}\n - samples in {timeseries_dir}")

    # --- Optional: upload artifacts to Azure Blob Storage ---
import os, time
from pathlib import Path

az-blob-url = os.getenv("az-blob-url")  # e.g. https://<account>.blob.core.windows.net
az-blob-sas = os.getenv("az-blob-sas")  # SAS token without leading '?'
az-blob-container = os.getenv("az-blob-container", "thesis-artifacts")

if az-blob-url and az-blob-sas:
    try:
        from azure.storage.blob import BlobServiceClient
        ts = time.strftime("%Y%m%d-%H%M")
        root = Path(args.outdir)

        svc = BlobServiceClient(account_url=az-blob-url, credential=az-blob-sas)
        cc = svc.get_container_client(az-blob-container)
        try:
            cc.create_container()
        except Exception:
            pass

        # upload all files under outdir -> <timestamp>/...
        for p in root.rglob("*"):
            if p.is_file():
                blob_path = f"{ts}/{p.relative_to(root)}".replace("\\", "/")
                with open(p, "rb") as f:
                    cc.upload_blob(name=blob_path, data=f, overwrite=True)

        # write or update 'latest.txt' pointer
        cc.upload_blob(name="latest.txt", data=f"{ts}".encode("utf-8"), overwrite=True)
        print(f"Uploaded artifacts to {az-blob-url}/{az-blob-container}/{ts} and updated latest.txt")
    except Exception as ex:
        print("Blob upload skipped or failed:", ex)

if __name__ == "__main__":
    main()
