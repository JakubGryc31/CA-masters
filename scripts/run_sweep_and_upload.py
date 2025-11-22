# scripts/run_sweep_and_upload.py
import os, sys, time, subprocess
from pathlib import Path

def run_sweep(pass_through_args):
    cmd = [sys.executable, "scripts/run_thesis_sweep.py"] + pass_through_args
    print("[runner] Starting sweep:", " ".join(cmd))
    res = subprocess.run(cmd)
    if res.returncode != 0:
        print("[runner] Sweep failed with code", res.returncode, file=sys.stderr)
        sys.exit(res.returncode)
    print("[runner] Sweep finished OK.")

def upload_artifacts(outdir: str):
    # env vars MUST be set in the Container Apps Job
    AZ_BLOB_URL = os.getenv("AZ_BLOB_URL")
    AZ_BLOB_SAS = os.getenv("AZ_BLOB_SAS")
    AZ_BLOB_CONTAINER = os.getenv("AZ_BLOB_CONTAINER", "thesis-artifacts")

    if not (AZ_BLOB_URL and AZ_BLOB_SAS):
        print("[runner] Skipping upload: AZ_BLOB_URL or AZ_BLOB_SAS not set.")
        return

    try:
        from azure.storage.blob import BlobServiceClient
    except Exception as e:
        print("[runner] azure-storage-blob not available:", e, file=sys.stderr)
        sys.exit(1)

    root = Path(outdir)
    if not root.exists():
        print(f"[runner] Output dir not found: {root}", file=sys.stderr)
        sys.exit(1)

    ts = time.strftime("%Y%m%d-%H%M")
    print(f"[runner] Uploading {root} to {AZ_BLOB_URL}/{AZ_BLOB_CONTAINER}/{ts}/")
    svc = BlobServiceClient(account_url=AZ_BLOB_URL, credential=AZ_BLOB_SAS)
    cc = svc.get_container_client(AZ_BLOB_CONTAINER)
    try:
        cc.create_container()
    except Exception:
        pass

    # upload all files under outdir -> <timestamp>/...
    count = 0
    for p in root.rglob("*"):
        if p.is_file():
            blob_path = f"{ts}/{p.relative_to(root)}".replace("\\", "/")
            with open(p, "rb") as f:
                cc.upload_blob(name=blob_path, data=f, overwrite=True)
            count += 1

    # write/update latest.txt pointer
    cc.upload_blob(name="latest.txt", data=f"{ts}".encode("utf-8"), overwrite=True)
    print(f"[runner] Uploaded {count} files. Updated latest.txt to {ts}.")

def main():
    # find --outdir in args (default matches your scripts)
    args = sys.argv[1:]
    outdir = "outputs/thesis_artifacts"
    if "--outdir" in args:
        i = args.index("--outdir")
        if i + 1 < len(args):
            outdir = args[i + 1]
    run_sweep(args)
    upload_artifacts(outdir)

if __name__ == "__main__":
    main()
