# scripts/run_sweep_and_upload.py
"""
Wrapper that:
  1) runs the sweep (scripts/run_thesis_sweep.py) with any passthrough args,
  2) performs QC on the produced CSVs (min seeds per group + derived metrics),
  3) uploads the OUTDIR to Azure Blob and updates latest.txt (timestamp pointer).

Env vars expected (SAS mode – default):
  AZ_BLOB_URL       e.g., https://castoragemasters.blob.core.windows.net
  AZ_BLOB_CONTAINER e.g., output-simulation
  AZ_BLOB_SAS       container/account SAS token, WITHOUT the leading '?'

Optional (Managed Identity mode):
  USE_MI=1          switches to DefaultAzureCredential() instead of SAS.

Exit codes:
  0  success (sweep + QC + upload)
  2  QC detected missing columns
  3  QC failed (min seeds not satisfied)
  4  Upload configuration error (env vars/credential)
"""

from __future__ import annotations
import os
import sys
import time
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional


# -------------------------- small utils --------------------------

def log(msg: str) -> None:
    print(f"[runner] {msg}", flush=True)


def parse_outdir_from_args(args: List[str], default: str = "outputs/thesis_artifacts") -> str:
    outdir = default
    if "--outdir" in args:
        i = args.index("--outdir")
        if i + 1 < len(args):
            outdir = args[i + 1]
    return outdir


def run(cmd: List[str]) -> int:
    log("Exec: " + " ".join(cmd))
    return subprocess.run(cmd).returncode


# -------------------------- steps --------------------------

def run_sweep(pass_through_args: List[str]) -> None:
    """
    Calls the main sweep script with passthrough args.
    """
    cmd = [sys.executable, "scripts/run_thesis_sweep.py"] + pass_through_args
    rc = run(cmd)
    log(f"Sweep finished with code {rc}")
    if rc != 0:
        sys.exit(rc)


def run_qc(outdir: str, min_seeds: int = 15) -> None:
    """
    Runs QC over the raw CSV and writes an upgraded grouped CSV
    with n, recovery_rate, ttr_conditional_mean. Fails the run if
    any group has n < min_seeds.
    """
    raw_csv = str(Path(outdir) / "metrics_summary_raw.csv")
    if not Path(raw_csv).exists():
        log(f"QC: raw CSV not found at {raw_csv}")
        sys.exit(2)

    cmd = [
        sys.executable, "scripts/qc_after_sweep.py",
        "--raw", raw_csv,
        "--outdir", outdir,
        "--min_seeds", str(min_seeds),
    ]
    rc = run(cmd)
    if rc != 0:
        log(f"QC failed (code {rc}); not uploading.")
        sys.exit(rc)
    log("QC passed.")


def get_blob_client():
    """
    Returns (container_client, timestamp_str).
    Supports SAS (default) or Managed Identity if USE_MI=1.
    """
    from azure.storage.blob import BlobServiceClient

    use_mi = os.getenv("USE_MI", "0") == "1"
    url = os.getenv("AZ_BLOB_URL")
    container = os.getenv("AZ_BLOB_CONTAINER")
    sas = os.getenv("AZ_BLOB_SAS")

    if not url or not container:
        log("Upload configuration error: AZ_BLOB_URL or AZ_BLOB_CONTAINER not set.")
        sys.exit(4)

    if use_mi:
        try:
            from azure.identity import DefaultAzureCredential
            cred = DefaultAzureCredential()
            svc = BlobServiceClient(account_url=url, credential=cred)
            log("Auth mode: Managed Identity")
        except Exception as e:
            log(f"Failed to create MI credential: {e}")
            sys.exit(4)
    else:
        if not sas:
            log("AZ_BLOB_SAS not set (and USE_MI=0).")
            sys.exit(4)
        svc = BlobServiceClient(account_url=url, credential=sas)
        log("Auth mode: SAS token")

    cc = svc.get_container_client(container)
    try:
        cc.create_container()
    except Exception:
        pass  # ok if exists

    ts = time.strftime("%Y%m%d-%H%M")
    return cc, ts


def upload_artifacts(outdir: str) -> Tuple[int, str]:
    """
    Uploads ALL files under outdir to <container>/<ts>/..., and updates latest.txt.
    Returns (uploaded_count, ts).
    """
    from azure.core.exceptions import HttpResponseError

    root = Path(outdir)
    if not root.exists():
        log(f"Upload: output dir not found: {root}")
        sys.exit(4)

    cc, ts = get_blob_client()
    uploaded = 0

    for p in root.rglob("*"):
        if p.is_file():
            blob_name = f"{ts}/{p.relative_to(root)}".replace("\\", "/")
            with open(p, "rb") as f:
                try:
                    cc.upload_blob(name=blob_name, data=f, overwrite=True)
                    uploaded += 1
                except HttpResponseError as e:
                    log(f"Upload error for {blob_name}: {e}")
                    raise

    # pointer
    cc.upload_blob(name="latest.txt", data=ts.encode("utf-8"), overwrite=True)
    return uploaded, ts


# -------------------------- main --------------------------

def main() -> None:
    # Pass-through args go straight to run_thesis_sweep.py
    args = sys.argv[1:]
    outdir = parse_outdir_from_args(args, default="outputs/thesis_artifacts")

    log(f"Args: {args}")
    log(f"Resolved outdir: {outdir}")

    # Print redacted env presence
    for k in ("AZ_BLOB_URL", "AZ_BLOB_CONTAINER", "AZ_BLOB_SAS", "USE_MI"):
        v = os.getenv(k)
        log(f"ENV {k}: {'set' if v else 'MISSING'}")

    # 1) run sweep
    run_sweep(args)

    # 2) QC (fail fast if under-sampled)
    run_qc(outdir=outdir, min_seeds=int(os.getenv("MIN_SEEDS_PER_GROUP", "15")))

    # 3) upload
    uploaded, ts = upload_artifacts(outdir)
    log(f"Uploaded {uploaded} files. Updated latest.txt -> {ts}.")
    log("All done.")


if __name__ == "__main__":
    main()
