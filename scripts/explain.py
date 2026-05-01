"""Print a narrative for a past run.

Usage:
  python scripts/explain.py                  # latest run
  python scripts/explain.py 20260501-202125-569
  python scripts/explain.py /full/path/to/run_dir
"""

from __future__ import annotations

import sys
from pathlib import Path

from inderes_agent.observability.narrate import summarize_run
from inderes_agent.observability.run_log import RUNS_ROOT


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else None

    if arg is None:
        if not RUNS_ROOT.exists():
            print("No runs yet.", file=sys.stderr)
            return 1
        candidates = sorted(RUNS_ROOT.iterdir(), reverse=True)
        if not candidates:
            print("No runs yet.", file=sys.stderr)
            return 1
        run_dir = candidates[0]
    else:
        p = Path(arg)
        run_dir = p if p.is_absolute() and p.exists() else RUNS_ROOT / arg
        if not run_dir.exists():
            print(f"No such run: {run_dir}", file=sys.stderr)
            return 1

    print(summarize_run(run_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
