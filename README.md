# CA-masters — UAV Control Experiments & Azure Dashboard

**One-line**: Reproducible UAV control experiments (PID/LQR/MPC) with an Azure Container Apps sweep pipeline and a Streamlit dashboard that pulls results directly from Azure Blob Storage.

**Final run (frozen for thesis)**: `20251122-2019`  
**Scope**: 36 groups × 25 seeds = **900 episodes**  
**Headline KPIs (overall)**: Overshoot **0.877**, Time-to-recover **86.631** steps, Crash **0.0%**, Effort **0.103**, Recovery rate **32.0%**, TTR | recovered **267.1** (median ~270.6).

---

## Contents

- [Overview](#overview)
- [Repo structure](#repo-structure)
- [Quick start (local)](#quick-start-local)
- [Generate data locally](#generate-data-locally)
- [Cloud pipeline (Azure Container Apps Job)](#cloud-pipeline-azure-container-apps-job)
- [Dashboard](#dashboard)
- [Reproducibility & “frozen run”](#reproducibility--frozen-run)
- [Diagrams](#diagrams)
- [Results snapshot](#results-snapshot)
- [Cite & License](#cite--license)

---

## Overview

This project simulates a simplified UAV tracking task with three controllers (PID, LQR, MPC) across different grids, turbulence levels, and failure modes.  
A batch sweep writes two CSVs:

- `metrics_summary_raw.csv` — all episodes
- `metrics_summary_grouped.csv` — means/std per (controller, grid, turbulence, failure)

A Streamlit dashboard reads the latest run from Azure Blob Storage and renders KPI bars + a Pareto view (overshoot vs effort).

---

## Repo structure

```
CA-masters/
├─ dashboard/ # Streamlit app
│ └─ streamlit_app.py
├─ scripts/ # Experiment & upload
│ ├─ run_thesis_sweep.py
│ └─ run_sweep_and_upload.py
├─ docs/ # Diagrams & final PDF report assets
│ ├─ architecture.drawio
│ ├─ workflow.drawio
│ └─ UAV Control v6 final — Experiment Sweep Dashboard.pdf
├─ requirements.txt
├─ Dockerfile
├─ .env.sample # copy to .env and fill
├─ .gitignore
├─ LICENSE
└─ CITATION.cff
```

## Quick start (local)

### Create & activate virtual env
python -m venv .venv

### Windows
.venv\Scripts\activate

### macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.sample .env   # set AZ_* if you want dashboard to read from Azure

## Generate data locally 

```
python scripts/run_thesis_sweep.py --T 600 --outdir outputs/thesis_artifacts --seeds 25
```
# Outputs:

- outputs/thesis_artifacts/metrics_summary_raw.csv
- outputs/thesis_artifacts/metrics_summary_grouped.csv
- outputs/thesis_artifacts/timeseries_samples/…

## Cloud pipeline (Azure Container Apps Job)

Idea: Build & push the Docker image to ACR, then run a Container Apps Job that executes the sweep and uploads results to Azure Blob Storage. The job also writes latest.txt with the new run folder name (YYYYMMDD-HHMM/).

### Required configuration (as secrets/variables on the job):

- AZ_BLOB_URL — e.g. https://<account>.blob.core.windows.net
- AZ_BLOB_CONTAINER — e.g. output-simulation
- AZ_BLOB_SAS — SAS token without the leading

### Command / Args in job:

- Command: python
- Args: scripts/run_sweep_and_upload.py --T 600 --outdir outputs/thesis_artifacts

## Dahboard

The Streamlit app loads the pointer in latest.txt, then fetches both grouped & raw CSVs.

Run locally:
```
streamlit run dashboard/streamlit_app.py
```

### Environment variables:

- AZ_BLOB_URL, AZ_BLOB_CONTAINER, and either AZ_BLOB_SAS or USE_MI=1

### Optional:

- TARGET_OVERSHOOT (default 0.10)
- TARGET_EFFORT (default 0.50)
- LATEST_BLOB (default latest.txt), GROUPED_NAME, RAW_NAME

### Features:

- KPI bars (means ± std) with fixed controller order (PID → LQR → MPC)
- Dotted reference lines for overshoot / effort
- TTR axis clamp for readability
- Pareto small-multiples (columns: turbulence; rows appear for failure when multiple are selected)
- PNG and CSV download buttons
- Run badge showing run id, total groups, and total episodes

## Reproducibility (frozen run)

For the thesis we freeze results at:

- Run ID: 20251122-2019
- Folder in storage: 20251122-2019/ containing:
- metrics_summary_grouped.csv
- metrics_summary_raw.csv
- timeseries_samples/

Keep latest.txt pointing to that folder, or record this run id in the thesis text to lock figures to a specific dataset.

## Results snapshot (frozen run)

- 36×25 = 900 episodes (run 20251122-2019)
- Overshoot 0.877
- Time-to-recover 86.631 steps
- Crash 0.0%
- Effort 0.103
- Recovery rate 32.0%
- TTR | recovered 267.1 (median ~270.6)

### Qualitative pattern (consistent across conditions):

- MPC → lowest overshoot, highest effort
- PID → highest overshoot, lowest effort
- LQR → middle on both metrics
- Harder conditions (high turbulence + failures) increase TTR and reduce Pareto efficiency; hierarchy persists.

