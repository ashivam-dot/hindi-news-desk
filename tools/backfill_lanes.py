"""Give the published rows from before 2026-10-22 a lane and an audience (plan.backfill_lanes), once.

    uv run python tools/backfill_lanes.py           # count the lanes, write nothing
    uv run python tools/backfill_lanes.py --write   # rewrite state/published.json

It only reads and rewrites the local ledger file (a checkout of the state branch): nothing is fetched, pushed or sent
to YouTube, and a row that already has a lane or an audience keeps it. learn.refresh labels old rows the same way on
every read, so the ranking does not wait for this.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desk import ledger, plan  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    rows = ledger.published()
    done = plan.backfill_lanes(rows)
    print(f"{len(done)} rows, {sum(1 for r in rows if not r.get('lane'))} without a lane: "
          + ", ".join(f"{k} {n}" for k, n in Counter(r["lane"] for r in done).most_common()))
    if "--write" in argv:
        print(f"wrote {ledger.save('published', done)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
