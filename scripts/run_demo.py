import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from pathlib import Path
import pandas as pd
from src.experiments.sim import run
from src.experiments.scenarios import turbulence_schedule_factory
from src.analysis.metrics import metrics_from_log
from src.analysis.plots import plot_timeseries

OUT = Path('outputs'); OUT.mkdir(exist_ok=True)

baseline = dict(kp=0.8, ki=0.05, kd=0.12)
ga_candidate = dict(kp=0.15, ki=0.01, kd=0.006)

sched = turbulence_schedule_factory(low=0.0, mid=0.35, late=0.1, t1=50, t2=100)

for name, gains in [('baseline', baseline), ('ga', ga_candidate)]:
    log = run(T=140, seed=7, a_ref=0.0, pitch_up_at=35, pitch_up_delta=0.3,
              failure_window=(70,90), turb_sched=sched, **gains)
    metrics, df = metrics_from_log(log)
    df.to_csv(OUT/f'timeseries_{name}.csv', index=False)
    plot_timeseries(df, str(OUT/f'{name}'))

rows = []
for name in ['baseline','ga']:
    df = pd.read_csv(OUT/f'timeseries_{name}.csv')
    metrics, _ = metrics_from_log(df.to_dict(orient='list'))
    metrics['config'] = name
    rows.append(metrics)
pd.DataFrame(rows).to_csv(OUT/'metrics_summary.csv', index=False)
print("Demo complete.")
