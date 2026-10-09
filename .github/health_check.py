"""Open (or update) an alert issue when the desk is silent, its last run failed, or it has been holding for hours.

python3 .github/health_check.py state/health.json  (a missing file means no run has been recorded yet: no alert)
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SILENT_H = 4
TITLE = "Desk needs attention"


def problem(path: Path, now: datetime) -> str | None:
    if not path.exists():
        # A new desk has no run yet (the run workflow alerts on its own failures).
        print("no desk run recorded yet (state/health.json is missing)")
        return None
    health = json.loads(path.read_text(encoding="utf-8"))
    age = (now - datetime.fromisoformat(health["at"])).total_seconds() / 3600
    if age > SILENT_H:
        return f"No desk run recorded for {age:.1f} hours (last at {health['at']})."
    if not health.get("ok"):
        return f"Last run failed: {health.get('error')}"
    if health.get("held"):
        return f"The desk is holding: {health['held']}"
    return None


def main() -> None:
    found_problem = problem(Path(sys.argv[1]), datetime.now(timezone.utc))
    print(found_problem or "healthy")
    if not found_problem:
        return
    found = subprocess.run(["gh", "issue", "list", "--state", "open", "--label", "alert", "--search", TITLE,
                            "--json", "number", "--jq", ".[0].number"], capture_output=True, text=True).stdout.strip()
    if found:
        subprocess.run(["gh", "issue", "comment", found, "--body", found_problem], check=True)
    else:
        subprocess.run(["gh", "issue", "create", "--label", "alert", "--title", TITLE, "--body", found_problem],
                       check=True)


if __name__ == "__main__":
    main()
