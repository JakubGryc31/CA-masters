# scripts/run_sweep_and_upload.py
"""
1) runs scripts/run_thesis_sweep.py with passthrough args
2) QC (min seeds / derived metrics)
3) uploads OUTDIR to Azure Blob + updates latest.txt

Env (SAS mode, default):
  AZ_BLOB_URL, AZ_BLOB_CONTAINER, AZ_BLOB_SAS
MI mode:
  USE_MI=1 (and grant identity Storage Blob Data Reader)

Optional:
  MIN_SEEDS_PER_GROUP (default 15)
"""
from __future__ import annotations
import os, sys, time, subprocess
from pathlib import Path
from typing import List, Tuple

def log(msg: str): print(f"[runner] {msg}", flush=True)

def parse_outdir(args: List[str], default="outputs/thesis_artifacts") -> str:
    return args[args.index("--outdir")+1] if "--outdir" in args else default

def run(cmd: List[str]) -> int:
    log("Exec: " + " ".join(cmd))
    return subprocess.run(cmd).returncode

def run_sweep(pass_through: List[str]) -> None:
    rc = run([sys.executable, "scripts/run_thesis_sweep.py"] + pass_through)
    log(f"Sweep finished with code {rc}")
    if rc != 0: sys.exit(rc)

def run_qc(outdir: str, min_seeds: int) -> None:
    raw_csv = str(Path(outdir) / "metrics_summary_raw.csv")
    if not Path(raw_csv).exists():
        log(f"QC: raw CSV not found at {raw_csv}"); sys.exit(2)
    rc = run([sys.executable, "scripts/qc_after_sweep.py",
              "--raw", raw_csv, "--outdir", outdir, "--min_seeds", str(min_seeds)])
    if rc != 0:
        log(f"QC failed (code {rc}); not uploading."); sys.exit(rc)
    log("QC passed.")

def get_blob_client():
    from azure.storage.blob import BlobServiceClient
    url = os.getenv("AZ_BLOB_URL"); container = os.getenv("AZ_BLOB_CONTAINER")
    use_mi = os.getenv("USE_MI","0") == "1"; sas = os.getenv("AZ_BLOB_SAS")
    if not url or not container:
        log("Upload configuration error: AZ_BLOB_URL or AZ_BLOB_CONTAINER not set."); sys.exit(4)
    if use_mi:
        from azure.identity import DefaultAzureCredential
        svc = BlobServiceClient(account_url=url, credential=DefaultAzureCredential())
        log("Auth mode: Managed Identity")
    else:
        if not sas: log("AZ_BLOB_SAS not set (and USE_MI=0)."); sys.exit(4)
        svc = BlobServiceClient(account_url=url, credential=sas)
        log("Auth mode: SAS token")
    cc = svc.get_container_client(container)
    try: cc.create_container()
    except Exception: pass
    ts = time.strftime("%Y%m%d-%H%M")
    return cc, ts

def upload_artifacts(outdir: str) -> Tuple[int, str]:
    from azure.core.exceptions import HttpResponseError
    root = Path(outdir)
    if not root.exists(): log(f"Upload: output dir not found: {root}"); sys.exit(4)
    cc, ts = get_blob_client(); uploaded = 0
    for p in root.rglob("*"):
        if p.is_file():
            blob_name = f"{ts}/{p.relative_to(root)}".replace("\\","/")
            with open(p, "rb") as f:
                try:
                    cc.upload_blob(name=blob_name, data=f, overwrite=True); uploaded += 1
                except HttpResponseError as e:
                    log(f"Upload error for {blob_name}: {e}"); raise
    cc.upload_blob(name="latest.txt", data=ts.encode("utf-8"), overwrite=True)
    return uploaded, ts

def main():
    args = sys.argv[1:]; outdir = parse_outdir(args)
    log(f"Args: {args}"); log(f"Resolved outdir: {outdir}")
    for k in ("AZ_BLOB_URL","AZ_BLOB_CONTAINER","AZ_BLOB_SAS","USE_MI"):
        log(f"ENV {k}: {'set' if os.getenv(k) else 'MISSING'}")

    run_sweep(args)
    run_qc(outdir=outdir, min_seeds=int(os.getenv("MIN_SEEDS_PER_GROUP","15")))
    uploaded, ts = upload_artifacts(outdir)
    log(f"Uploaded {uploaded} files. Updated latest.txt -> {ts}."); log("All done.")

if __name__ == "__main__":
    main()
