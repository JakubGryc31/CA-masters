# dashboard/streamlit_app.py
import os
import io
import time
from dataclasses import dataclass

import pandas as pd
import plotly.express as px
import streamlit as st

# Optional: load .env locally (comment out if you don't want this behaviour)
try:
    from dotenv import load_dotenv  # pip install python-dotenv
    load_dotenv()
except Exception:
    pass

# ---------- Config / Auth ----------
USE_MI = os.getenv("USE_MI", "0") == "1"  # set to "1" if running in Azure with Managed Identity

AZ_BLOB_URL = os.getenv("AZ_BLOB_URL", "https://castoragemasters.blob.core.windows.net")
AZ_BLOB_CONTAINER = os.getenv("AZ_BLOB_CONTAINER", "output-simulation")
AZ_BLOB_SAS = os.getenv("AZ_BLOB_SAS", None)  # token WITHOUT leading '?'

LATEST_BLOB = os.getenv("LATEST_BLOB", "latest.txt")
GROUPED_NAME = os.getenv("GROUPED_NAME", "metrics_summary_grouped.csv")
RAW_NAME = os.getenv("RAW_NAME", "metrics_summary_raw.csv")

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

# ---------- UI ----------
st.set_page_config(page_title="UAV Control — Sweep Dashboard", layout="wide")
st.title("UAV Control — Experiment Sweep Dashboard")

with st.sidebar:
    st.header("Data source")
    st.caption("Pulls from Azure Blob Storage")
    st.code(
        f"URL: {AZ_BLOB_URL}\nContainer: {AZ_BLOB_CONTAINER}\nlatest.txt: {LATEST_BLOB}",
        language="text",
    )
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

# Basic hygiene
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
for name, sel in [
    ("controller", sel_controller),
    ("grid", sel_grid),
    ("turbulence", sel_turb),
    ("failure", sel_fail),
]:
    if sel:
        q = q[q[name].isin(sel)]

# Sample size
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
with k[0]:
    kpi(q, "overshoot_mean", "Overshoot (↓)")
with k[1]:
    kpi(q, "time_to_recover_mean", "Time to recover (↓)")
with k[2]:
    kpi(q, "crash_mean", "Crash rate (↓)", fmt=lambda v: f"{100*v:.1f}%")
with k[3]:
    kpi(q, "control_effort_mean", "Control effort (↓)")

st.divider()

# ---------- Per-metric charts with error bars ----------
def bar_with_err(df, y_col, y_label):
    if y_col not in df.columns:
        st.info(f"Column '{y_col}' not found.")
        return
    err_col = y_col.replace("_mean", "_std")
    error_y = df[err_col] if err_col in df.columns else None
    fig = px.bar(
        df, x="controller", y=y_col, color="controller",
        error_y=error_y, barmode="group",
        title=y_label
    )
    if y_col == "crash_mean":
        fig.update_yaxes(tickformat=".0%", range=[0, 1])
    st.plotly_chart(fig, use_container_width=True)

c1, c2 = st.columns(2)
with c1: bar_with_err(q, "overshoot_mean", "Overshoot (lower is better)")
with c2: bar_with_err(q, "time_to_recover_mean", "Time to recover (lower is better)")

c3, c4 = st.columns(2)
# format crash as percentage by temporarily scaling
if "crash_mean" in q.columns:
    q_pct = q.copy()
    q_pct["crash_mean"] = q_pct["crash_mean"].clip(0, 1)
    with c3:
        bar_with_err(q_pct, "crash_mean", "Crash rate (lower is better)")
else:
    with c3:
        st.info("Column 'crash_mean' not found.")

with c4: bar_with_err(q, "control_effort_mean", "Control effort (lower is better)")

st.divider()

# Overshoot by grid (mean ± std), if available
if {"grid", "controller", "overshoot_mean"}.issubset(q.columns):
    st.subheader("Overshoot by grid")
    err = "overshoot_std" if "overshoot_std" in q.columns else None
    fig = px.bar(q, x="grid", y="overshoot_mean", color="controller", barmode="group",
                 error_y=q[err] if err else None)
    fig.update_layout(yaxis_title="Overshoot")
    st.plotly_chart(fig, use_container_width=True)

# Recovery time vs turbulence (line)
if {"controller", "turbulence", "time_to_recover_mean"}.issubset(q.columns):
    st.subheader("Recovery time vs. turbulence")
    # try numeric sort if turbulence is numeric-like
    try:
        q2 = q.assign(_turb=pd.to_numeric(q["turbulence"]))
    except Exception:
        q2 = q.assign(_turb=q["turbulence"])
    fig = px.line(q2.sort_values("_turb"), x="turbulence", y="time_to_recover_mean",
                  color="controller", markers=True)
    fig.update_layout(yaxis_title="Time to recover")
    st.plotly_chart(fig, use_container_width=True)

# ---------- Downloads ----------
st.subheader("Download current data")
d1, d2 = st.columns(2)
with d1:
    st.download_button(
        "Download grouped CSV (filtered view)",
        data=q.to_csv(index=False).encode("utf-8"),
        file_name=f"grouped_{ptr.ts}_filtered.csv",
        mime="text/csv",
        use_container_width=True,
    )
with d2:
    st.download_button(
        "Download raw CSV (full run)",
        data=df_raw.to_csv(index=False).encode("utf-8"),
        file_name=f"raw_{ptr.ts}.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.caption(f"Refreshed: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
