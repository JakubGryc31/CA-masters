# scripts/run_sweep_and_upload.py
import os, sys, time, subprocess
from pathlib import Path

def log(msg): print(f"[runner] {msg}", flush=True)

def run_sweep(pass_through_args):
    cmd = [sys.executable, "scripts/run_thesis_sweep.py"] + pass_through_args
    log("Starting sweep: " + " ".join(cmd))
    res = subprocess.run(cmd)
    log(f"Sweep finished with code {res.returncode}")
    if res.returncode != 0:
        sys.exit(res.returncode)

def upload_artifacts(outdir: str):
    AZ_BLOB_URL = os.getenv("AZ_BLOB_URL")
    AZ_BLOB_SAS = os.getenv("AZ_BLOB_SAS")
    AZ_BLOB_CONTAINER = os.getenv("AZ_BLOB_CONTAINER", "thesis-artifacts")

    if not AZ_BLOB_URL or not AZ_BLOB_SAS:
        log("Skipping upload: AZ_BLOB_URL or AZ_BLOB_SAS not set.")
        return

    try:
        from azure.storage.blob import BlobServiceClient
    except Exception as e:
        log(f"azure-storage-blob not available: {e}")
        sys.exit(1)

    root = Path(outdir)
    if not root.exists():
        log(f"Output dir not found: {root}")
        sys.exit(1)

    ts = time.strftime("%Y%m%d-%H%M")
    log(f"Uploading from {root} to {AZ_BLOB_URL}/{AZ_BLOB_CONTAINER}/{ts}/")
    svc = BlobServiceClient(account_url=AZ_BLOB_URL, credential=AZ_BLOB_SAS)
    cc = svc.get_container_client(AZ_BLOB_CONTAINER)
    try:
        cc.create_container()
    except Exception:
        pass

    count = 0
    for p in root.rglob("*"):
        if p.is_file():
            blob_path = f"{ts}/{p.relative_to(root)}".replace("\\", "/")
            with open(p, "rb") as f:
                cc.upload_blob(name=blob_path, data=f, overwrite=True)
            count += 1

    cc.upload_blob(name="latest.txt", data=f"{ts}".encode("utf-8"), overwrite=True)
    log(f"Uploaded {count} files. Updated latest.txt to {ts}.")

def main():
    args = sys.argv[1:]
    outdir = "outputs/thesis_artifacts"
    if "--outdir" in args:
        i = args.index("--outdir")
        if i + 1 < len(args):
            outdir = args[i + 1]
    log(f"Args: {args}")
    log(f"Resolved outdir: {outdir}")
    # print a redacted view of env presence (not values)
    for k in ("AZ_BLOB_URL","AZ_BLOB_CONTAINER","AZ_BLOB_SAS"):
        v = os.getenv(k)
        log(f"ENV {k}: {'set' if v else 'MISSING'}")
    run_sweep(args)
    upload_artifacts(outdir)

if __name__ == "__main__":
    main()
