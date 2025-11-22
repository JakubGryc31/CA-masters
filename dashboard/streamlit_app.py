# dashboard/streamlit_app.py
import os
import io
import time
from dataclasses import dataclass

import pandas as pd
import plotly.express as px
import streamlit as st

# Optional: load a local .env during dev
try:
    from dotenv import load_dotenv  # pip install python-dotenv
    load_dotenv()
except Exception:
    pass

# ---------- Config / Auth ----------
USE_MI = os.getenv("USE_MI", "0") == "1"  # set to "1" in Azure if using Managed Identity

AZ_BLOB_URL = os.getenv("AZ_BLOB_URL", "https://<youraccount>.blob.core.windows.net")
AZ_BLOB_CONTAINER = os.getenv("AZ_BLOB_CONTAINER", "output-simulation")
AZ_BLOB_SAS = os.getenv("AZ_BLOB_SAS")  # token WITHOUT leading '?'

LATEST_BLOB = os.getenv("LATEST_BLOB", "latest.txt")
GROUPED_NAME = os.getenv("GROUPED_NAME", "metrics_summary_grouped.csv")
RAW_NAME = os.getenv("RAW_NAME", "metrics_summary_raw.csv")

st.set_page_config(page_title="UAV Control — Experiment Sweep Dashboard", layout="wide")
st.title("UAV Control — Experiment Sweep Dashboard")
st.caption("Means ± std over seeds; filters apply to all charts. Lower is better unless stated otherwise.")

# ---------- Blob helpers ----------
@st.cache_data(ttl=120)
def _get_blob_service():
    if USE_MI:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
        cred = DefaultAzureCredential()
        return BlobServiceClient(account_url=AZ_BLOB_URL, credential=cred)
    else:
        from azure.storage.blob import BlobServiceClient
        if not AZ_BLOB_SAS:
            raise RuntimeError("AZ_BLOB_SAS not set (and USE_MI=0).")
        return BlobServiceClient(account_url=AZ_BLOB_URL, credential=AZ_BLOB_SAS)

@st.cache_data(ttl=60)
def read_text_blob(container: str, name: str) -> str:
    svc = _get_blob_service()
    data = svc.get_container_client(container).download_blob(name).readall()
    return data.decode("utf-8").strip()

@st.cache_data(ttl=60)
def read_csv_blob(container: str, name: str) -> pd.DataFrame:
    svc = _get_blob_service()
    stream = svc.get_container_client(container).download_blob(name).readall()
    return pd.read_csv(io.BytesIO(stream))

@dataclass
class RunPointer:
    ts: str
    grouped_blob: str
    raw_blob: str

def resolve_pointer() -> RunPointer:
    ts = read_text_blob(AZ_BLOB_CONTAINER, LATEST_BLOB)  # e.g., 20251122-1300
    return RunPointer(ts=ts,
                      grouped_blob=f"{ts}/{GROUPED_NAME}",
                      raw_blob=f"{ts}/{RAW_NAME}")

with st.sidebar:
    st.header("Data source")
    st.caption("Pulls from Azure Blob Storage")
    st.code(f"URL: {AZ_BLOB_URL}\nContainer: {AZ_BLOB_CONTAINER}\nlatest.txt: {LATEST_BLOB}", language="text")
    st.caption(f"Auth: {'Managed Identity' if USE_MI else 'SAS token'}")
    st.markdown("---")

status = st.empty()

# Pointer + data load
try:
    ptr = resolve_pointer()
    status.success(f"Loaded latest run: **{ptr.ts}**")
except Exception as e:
    st.error(f"Failed to load latest.txt: {e}")
    st.stop()

try:
    df_grp = read_csv_blob(AZ_BLOB_CONTAINER, ptr.grouped_blob)
    df_raw = read_csv_blob(AZ_BLOB_CONTAINER, ptr.raw_blob)
except Exception as e:
    st.error(f"Failed to read CSVs for run {ptr.ts}: {e}")
    st.stop()

# hygiene
for c in ["controller", "grid", "turbulence", "failure"]:
    if c in df_grp.columns:
        df_grp[c] = df_grp[c].astype(str)

# Filters
flt = st.columns(4)
with flt[0]:
    sel_controller = st.multiselect("Controller(s)", sorted(df_grp["controller"].unique()), default=None)
with flt[1]:
    sel_grid = st.multiselect("Grid", sorted(df_grp["grid"].unique()), default=None)
with flt[2]:
    sel_turb = st.multiselect("Turbulence", sorted(df_grp["turbulence"].unique()), default=None)
with flt[3]:
    sel_fail = st.multiselect("Failure", sorted(df_grp["failure"].unique()), default=None)

q = df_grp.copy()
for name, sel in [("controller", sel_controller), ("grid", sel_grid), ("turbulence", sel_turb), ("failure", sel_fail)]:
    if sel:
        q = q[q[name].isin(sel)]

# Extra % columns for nicer hovers
if "crash_mean" in q:
    q["crash_%"] = (q["crash_mean"].clip(0, 1) * 100).round(1)
if "recovery_rate" in q:
    q["recovery_%"] = (q["recovery_rate"].clip(0, 1) * 100).round(1)

# Totals
st.caption(f"Filtered groups: {len(q):,} rows • Raw rows: {len(df_raw):,} • Run: {ptr.ts}")

# KPI row
def kpi(df, col, label, fmt=None, help_txt=None):
    if col in df.columns and not df.empty:
        v = float(df[col].mean())
        text = f"{v:,.3f}" if fmt is None else fmt(v)
        st.metric(label, text, help=help_txt)
    else:
        st.metric(label, "–", help=help_txt)

k = st.columns(4)
with k[0]: kpi(q, "overshoot_mean", "Overshoot (↓)")
with k[1]: kpi(q, "time_to_recover_mean", "Time to recover (↓)")
with k[2]: kpi(q, "crash_mean", "Crash rate (↓)", fmt=lambda v: f"{100*v:.1f}%")
with k[3]: kpi(q, "control_effort_mean", "Control effort (↓)")

# Recovery KPIs
k2 = st.columns(2)
with k2[0]:
    if "recovery_rate" in q.columns and not q.empty:
        st.metric("Recovery rate (↑)", f"{100*q['recovery_rate'].mean():.1f}%")
    else:
        st.metric("Recovery rate", "–")
with k2[1]:
    if "ttr_conditional_mean" in q.columns and not q.empty:
        mask = q["ttr_conditional_mean"].notna()
        val = q.loc[mask, "ttr_conditional_mean"].mean() if mask.any() else float("nan")
        st.metric("TTR | recovered (↓)", f"{val:.1f}" if mask.any() else "–")
    else:
        st.metric("TTR | recovered", "–")

st.divider()

# Robust summaries for recovery (optional but clarifying)
if {"recovery_rate","ttr_conditional_mean","n"}.issubset(q.columns) and not q.empty:
    rec_n = int((q["recovery_rate"] * q["n"]).sum())  # total recovered episodes across groups
    st.caption(f"Recovered episodes across filtered groups: {rec_n:,}")
    if q["ttr_conditional_mean"].notna().any():
        med_ttr = float(q["ttr_conditional_mean"].median())
        st.caption(f"Median TTR | recovered: {med_ttr:.1f} steps")


# ---------- Per-metric charts with error bars ----------
def bar_with_err(df, y_col, y_label, *, pct=False, clamp=None):
    """
    df: grouped (already filtered)
    y_col: '..._mean'
    pct: show as percent
    clamp: (lo, hi) axis range
    """
    if y_col not in df.columns or df.empty:
        st.info(f"Column '{y_col}' not found or empty.")
        return
    err_col = y_col.replace("_mean", "_std")
    error_y = df[err_col] if err_col in df.columns else None
    hover_cols = [c for c in ["controller","grid","turbulence","failure","n","recovery_%","crash_%","ttr_conditional_mean"]
                  if c in df.columns]
    fig = px.bar(df, x="controller", y=y_col, color="controller", error_y=error_y,
                 barmode="group", hover_data=hover_cols, title=y_label)
    if pct: fig.update_yaxes(tickformat=".0%")
    if clamp: fig.update_yaxes(range=list(clamp))
    fig.update_layout(showlegend=False, margin=dict(l=10,r=10,t=50,b=10))
    st.plotly_chart(fig, use_container_width=True)

c1, c2 = st.columns(2)
with c1:
    bar_with_err(q, "overshoot_mean", "Overshoot (mean ± std, lower is better)", clamp=(0, 2))
with c2:
    ymax = float(q["time_to_recover_mean"].max()) if "time_to_recover_mean" in q and not q.empty else 0.0
    bar_with_err(q, "time_to_recover_mean", "Time to recover (steps, mean ± std, lower is better)",
                 clamp=(0, max(5.0, ymax * 1.1)))

c3, c4 = st.columns(2)
if "crash_mean" in q.columns:
    q_pct = q.copy()
    q_pct["crash_mean"] = q_pct["crash_mean"].clip(0, 1)
    with c3:
        bar_with_err(q_pct, "crash_mean", "Crash rate (fraction, mean ± std, lower is better)",
                     pct=True, clamp=(0, 1))
with c4:
    bar_with_err(q, "control_effort_mean", "Control effort (|u|, mean ± std, lower is better)", clamp=(0, 2))

st.subheader("Overshoot by grid")
if {"grid","controller","overshoot_mean"}.issubset(q.columns):
    fig = px.bar(q, x="grid", y="overshoot_mean", color="controller", barmode="group",
                 error_y=q["overshoot_std"] if "overshoot_std" in q else None,
                 hover_data=[c for c in ["controller","grid","turbulence","failure","n","recovery_%"] if c in q])
    fig.update_layout(yaxis_title="Overshoot", margin=dict(l=10,r=10,t=50,b=10))
    fig.update_yaxes(range=[0, 2])
    st.plotly_chart(fig, use_container_width=True)

# ---------- Pareto trade-off ----------
st.subheader("Trade-off: Overshoot vs. Control Effort (Pareto view)")
if {"overshoot_mean","control_effort_mean","controller"}.issubset(q.columns) and not q.empty:
    qq = q.copy()
    fig = px.scatter(
        qq, x="overshoot_mean", y="control_effort_mean",
        color="controller", symbol="grid",
        facet_col="turbulence" if "turbulence" in qq.columns else None,
        hover_data=[c for c in ["controller","grid","turbulence","failure","n","recovery_%","crash_%","ttr_conditional_mean"] if c in qq.columns],
        title="Controllers closer to the lower-left corner are better (lower overshoot & lower effort)"
    )
    fig.update_xaxes(title="Overshoot", range=[0, 2])
    fig.update_yaxes(title="Control effort (|u|)", range=[0, 2])
    st.plotly_chart(fig, use_container_width=True)

# ---------- How to read these charts ----------
with st.expander("How to read these charts"):
    st.markdown("""
- **Overshoot (↓)** — maximum positive tracking error (fraction of the step). Capped at 2.0 for readability.
- **Time to recover (↓)** — steps until the error remains within a tight band (**hysteresis**) for several consecutive steps.
- **Crash rate (↓)** — fraction of episodes that diverged or violated safety rails (sustained large error or actuator saturation).
- **Control effort (↓)** — average absolute control |u|; lower means less aggressive actuation.
- **Recovery rate / TTR | recovered** — how often recoveries occur and, conditional on recovery, how long it takes.
- Error bars = **±1 std** across seeds (**n** in tooltip). Bars show **means** over current filters.
- Pareto plot: points nearer the **lower-left** are preferable (low overshoot & low effort).
""")

# ---------- Downloads ----------
st.subheader("Download current data")
d1, d2 = st.columns(2)
with d1:
    st.download_button("Download grouped CSV (filtered view)", q.to_csv(index=False).encode("utf-8"),
                       file_name=f"grouped_{ptr.ts}_filtered.csv", mime="text/csv", use_container_width=True)
with d2:
    st.download_button("Download raw CSV (full run)", df_raw.to_csv(index=False).encode("utf-8"),
                       file_name=f"raw_{ptr.ts}.csv", mime="text/csv", use_container_width=True)

st.caption(f"Refreshed: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
