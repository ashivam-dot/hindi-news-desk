"""Starts the desk's `run` workflow every EVERY minutes, because GitHub drops most of its scheduled runs (29-30 Oct:
gaps of 45 min to 4.5 h against a 15 min cron), then starts the next keeper before this job's time runs out.

    python scripts/keeper.py <owner/repo>
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

REPO = sys.argv[1]
EVERY = 15 * 60
LIFETIME = 5.5 * 3600  # a GitHub job may run 6 h
started = time.time()


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args, "-R", REPO], capture_output=True, text=True, timeout=60).stdout


def busy_or_recent() -> bool:
    """A live `run` is queued or running, or one started in the last 12 minutes (the cron did its job)."""
    runs = json.loads(gh("run", "list", "-w", "run", "-L", "5", "--json", "status,createdAt,event") or "[]")
    now = datetime.now(timezone.utc)
    for r in runs:
        if r["status"] in ("queued", "in_progress", "waiting", "pending"):
            return True
        age = (now - datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))).total_seconds()
        if age < 12 * 60:
            return True
    return False


while time.time() - started < LIFETIME:
    try:
        if not busy_or_recent():
            gh("workflow", "run", "run", "-f", "dry=false")
            print(datetime.now(timezone.utc).isoformat(timespec="seconds"), "started run", flush=True)
    except Exception as exc:  # noqa: BLE001 - try again next round
        print("keeper:", exc, flush=True)
    time.sleep(EVERY)
gh("workflow", "run", "keeper")
print("handed over to the next keeper", flush=True)
