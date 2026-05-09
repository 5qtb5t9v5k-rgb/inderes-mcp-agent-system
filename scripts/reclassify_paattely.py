"""Retroactively re-classify saved paattely.json files using the new parser.

Background: case_002 in evals/golden.yaml caught that the päättely
parser was returning `{prose: ...}` even when LEAD wrote 4 well-formed
paragraphs (one per slot per the prompt spec). The fix in
synthesis.py:_extract_paattely now lifts 4-paragraph prose into
`{disagree, resolution, uncertain, skipped}` when applicable.

This script applies the same lift to historical paattely.json files
so the SQLite index reflects the new classification without losing
the original content. The original `prose` body is preserved in a
`prose_legacy` field for forensic transparency — we never destroy
saved data.

Usage::

    python scripts/reclassify_paattely.py            # dry-run, prints summary
    python scripts/reclassify_paattely.py --apply    # writes the changes

After --apply, rebuild the SQLite index to pick up the new kinds:

    python scripts/build_runs_index.py

Idempotent: re-running on already-converted files is a no-op (the
heuristic looks for `prose` key, which is gone after conversion).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


_PARAGRAPHS_RE = re.compile(r"\n\s*\n")


def reclassify_one(path: Path, *, apply: bool) -> str:
    """Return one of: 'converted', 'kept_prose', 'no_prose_field', 'error'."""
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "error"
    parsed = blob.get("parsed") or {}
    if not isinstance(parsed, dict) or "prose" not in parsed:
        return "no_prose_field"
    body = parsed["prose"]
    paragraphs = [p.strip() for p in _PARAGRAPHS_RE.split(body) if p.strip()]
    if len(paragraphs) != 4:
        return "kept_prose"

    new_parsed = {
        "disagree":   paragraphs[0],
        "resolution": paragraphs[1],
        "uncertain":  paragraphs[2],
        "skipped":    paragraphs[3],
        # Preserve original prose for forensic transparency.
        "prose_legacy": body,
    }
    blob["parsed"] = new_parsed
    if apply:
        path.write_text(
            json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return "converted"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--runs-dir", type=Path,
        default=Path.home() / ".inderes_agent" / "runs",
    )
    parser.add_argument("--apply", action="store_true",
                        help="Actually write changes (default: dry-run)")
    args = parser.parse_args()

    if not args.runs_dir.is_dir():
        print(f"runs dir not found: {args.runs_dir}", file=sys.stderr)
        return 1

    counts = {"converted": 0, "kept_prose": 0, "no_prose_field": 0, "error": 0}
    for run_dir in sorted(args.runs_dir.iterdir()):
        pj = run_dir / "paattely.json"
        if not pj.exists():
            continue
        outcome = reclassify_one(pj, apply=args.apply)
        counts[outcome] += 1

    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"[{mode}] {counts['converted']} converted to structured, "
          f"{counts['kept_prose']} kept as prose (< 4 paragraphs), "
          f"{counts['no_prose_field']} skipped (already structured / no prose), "
          f"{counts['error']} errored")
    if not args.apply and counts["converted"]:
        print("\nRe-run with --apply to write the changes, then rebuild the "
              "index with `python scripts/build_runs_index.py`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
