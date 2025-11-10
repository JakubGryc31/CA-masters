
import sys, time
def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stdout)
