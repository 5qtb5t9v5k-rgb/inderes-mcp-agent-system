"""Index forensic-run JSONs into a SQLite database for fast eval queries.

Walks ``~/.inderes_agent/runs/<run_id>/`` and parses:
  - query.txt
  - routing.json
  - meta.json (incl. stage_timings)
  - conflicts.json
  - paattely.json
  - synthesis.txt (size only — text is left on disk)
  - subagent-*.json (tool calls extracted)
  - console.log (error sniff)

The result is a SQLite database at ``~/.inderes_agent/evals/runs_index.sqlite``
with two tables:

  runs        — one row per run, all the indexed metadata + flags
  tool_calls  — one row per MCP tool call across all runs

Why SQLite (not Postgres / Supabase) for Tier 0:
  - Zero infra. The DB is a single file; rebuild whenever you want.
  - 183 runs × ~5 tool calls each = ~1000 rows. Trivial to query.
  - When we move to Tier 2 (Supabase), the same schema applies — this
    script just needs a Postgres backend swap.

The indexer is idempotent: running it again rebuilds from scratch. We
never modify the source JSONs, so re-running on a moving runs/ dir is
always safe.

Usage::

    python scripts/build_runs_index.py            # rebuild, default paths
    python scripts/build_runs_index.py --runs-dir /alt/path/runs

Then query directly with ``sqlite3 ~/.inderes_agent/evals/runs_index.sqlite``
or programmatically. Sample queries are in ``evals/sample_queries.sql``.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_RUNS = """
CREATE TABLE IF NOT EXISTS runs (
    run_id              TEXT PRIMARY KEY,
    ts                  TEXT NOT NULL,
    query               TEXT,
    query_norm          TEXT,
    has_query           INTEGER,
    is_trivial_query    INTEGER,
    domains             TEXT,
    domains_count       INTEGER,
    companies           TEXT,
    companies_count     INTEGER,
    is_comparison       INTEGER,
    routing_reasoning   TEXT,
    lead_model          TEXT,
    conflict_model      TEXT,
    duration_s          REAL,
    fanout_s            REAL,
    conflict_s          REAL,
    lead_s              REAL,
    subagent_count      INTEGER,
    subagent_errors     INTEGER,
    fallback_events     INTEGER,
    has_synthesis       INTEGER,
    synthesis_chars     INTEGER,
    agreements_count    INTEGER,
    conflicts_count     INTEGER,
    isolated_count      INTEGER,
    conflict_skipped    TEXT,
    paattely_kind       TEXT,
    has_valuation       INTEGER,
    has_warning_phrase  INTEGER,
    console_has_error   INTEGER
);
"""

SCHEMA_TOOL_CALLS = """
CREATE TABLE IF NOT EXISTS tool_calls (
    run_id          TEXT NOT NULL,
    agent_index     INTEGER,
    agent_domain    TEXT,
    call_id         TEXT,
    tool_name       TEXT,
    arguments_json  TEXT,
    item_count      INTEGER,
    has_error       INTEGER,
    error_text      TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_runs_ts ON runs(ts);",
    "CREATE INDEX IF NOT EXISTS idx_runs_domains ON runs(domains);",
    "CREATE INDEX IF NOT EXISTS idx_runs_lead_model ON runs(lead_model);",
    "CREATE INDEX IF NOT EXISTS idx_tool_calls_run ON tool_calls(run_id);",
    "CREATE INDEX IF NOT EXISTS idx_tool_calls_tool ON tool_calls(tool_name);",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Run-id format: 20260509-094219-578 → 2026-05-09T09:42:19.578Z
_RUN_ID_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})-(\d{3})$")

# Treat these as "trivial" queries — they pollute eval data.
TRIVIAL_QUERY_RE = re.compile(r"^\s*(test|testi|asd+|hello|hi|moi|x+)\s*$", re.I)

# Phrases that LEAD outputs as edge-case warnings — used to flag whether
# the synthesis surfaced a warning the user should see.
WARNING_PHRASES = [
    "älä käytä yksittäisenä",
    "äärimmäisen optimistinen",
    "ristiriidassa",
    "ole varovainen",
    "tuhoutuva",
    "negatiivinen turvamarginaali",
]


def _ts_from_run_id(run_id: str) -> str:
    """Convert run_id like '20260509-094219-578' to ISO-8601 UTC string."""
    m = _RUN_ID_RE.match(run_id)
    if not m:
        return run_id  # fall back to raw — sortable enough
    y, mo, d, h, mi, s, ms = m.groups()
    return f"{y}-{mo}-{d}T{h}:{mi}:{s}.{ms}Z"


def _safe_load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Per-run extraction
# ---------------------------------------------------------------------------


def index_run(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    """Parse one run directory. Returns (run_row, tool_call_rows) or None."""
    run_id = run_dir.name
    if not _RUN_ID_RE.match(run_id):
        return None

    query = _safe_read_text(run_dir / "query.txt").strip()
    routing = _safe_load_json(run_dir / "routing.json") or {}
    meta = _safe_load_json(run_dir / "meta.json") or {}
    conflicts = _safe_load_json(run_dir / "conflicts.json") or {}
    paattely = _safe_load_json(run_dir / "paattely.json") or {}
    synthesis = _safe_read_text(run_dir / "synthesis.txt")
    console = _safe_read_text(run_dir / "console.log")

    domains = routing.get("domains") or []
    companies = routing.get("companies") or []
    stage = (meta.get("stage_timings") or {})

    # Conflict-detector summary
    parsed_conflicts = (conflicts.get("parsed") or {}) if isinstance(conflicts, dict) else {}
    agreements_count = len(parsed_conflicts.get("agreements") or [])
    conflicts_count = len(parsed_conflicts.get("conflicts") or [])
    isolated_count = len(parsed_conflicts.get("isolated_claims") or [])

    # Paattely shape
    parsed_paattely = (paattely.get("parsed") or {}) if isinstance(paattely, dict) else {}
    if not parsed_paattely:
        paattely_kind = "empty" if paattely.get("error") is None else "error"
    elif "prose" in parsed_paattely:
        paattely_kind = "prose"
    elif any(k in parsed_paattely for k in ("disagree", "resolution", "uncertain", "skipped")):
        paattely_kind = "structured"
    else:
        paattely_kind = "empty"

    # Synthesis warnings
    syn_lower = synthesis.lower()
    has_warning_phrase = any(p in syn_lower for p in WARNING_PHRASES)

    # Console error sniff (any line with ERROR / Traceback)
    console_has_error = bool(re.search(r"ERROR|Traceback|HeadlessAuthError", console))

    run_row = {
        "run_id": run_id,
        "ts": _ts_from_run_id(run_id),
        "query": query or None,
        "query_norm": query.strip().lower() if query else None,
        "has_query": int(bool(query)),
        "is_trivial_query": int(bool(TRIVIAL_QUERY_RE.match(query or ""))),
        "domains": json.dumps(domains, ensure_ascii=False),
        "domains_count": len(domains),
        "companies": json.dumps(companies, ensure_ascii=False),
        "companies_count": len(companies),
        "is_comparison": int(bool(routing.get("is_comparison"))),
        "routing_reasoning": routing.get("reasoning"),
        "lead_model": meta.get("lead_model"),
        "conflict_model": meta.get("conflict_detector_model"),
        "duration_s": meta.get("duration_seconds"),
        "fanout_s": stage.get("fanout_seconds"),
        "conflict_s": stage.get("conflict_detector_seconds"),
        "lead_s": stage.get("lead_seconds"),
        "subagent_count": meta.get("subagent_count"),
        "subagent_errors": meta.get("subagent_errors", 0),
        "fallback_events": meta.get("fallback_events", 0),
        "has_synthesis": int(bool(synthesis.strip())),
        "synthesis_chars": len(synthesis),
        "agreements_count": agreements_count,
        "conflicts_count": conflicts_count,
        "isolated_count": isolated_count,
        "conflict_skipped": conflicts.get("skipped_reason") if isinstance(conflicts, dict) else None,
        "paattely_kind": paattely_kind,
        "has_valuation": int("valuation" in domains),
        "has_warning_phrase": int(has_warning_phrase),
        "console_has_error": int(console_has_error),
    }

    # Tool-call rows from all subagent-*.json files.
    tool_rows: list[dict[str, Any]] = []
    for sa_file in sorted(run_dir.glob("subagent-*.json")):
        sa = _safe_load_json(sa_file)
        if not sa:
            continue
        agent_index = sa.get("index")
        agent_domain = sa.get("domain")
        for call in sa.get("tool_calls") or []:
            tool_rows.append({
                "run_id": run_id,
                "agent_index": agent_index,
                "agent_domain": agent_domain,
                "call_id": call.get("call_id"),
                "tool_name": call.get("name"),
                "arguments_json": json.dumps(
                    call.get("arguments"), ensure_ascii=False, default=str
                ),
                "item_count": call.get("item_count"),
                "has_error": int(call.get("error") is not None),
                "error_text": str(call.get("error")) if call.get("error") else None,
            })

    return run_row, tool_rows


# ---------------------------------------------------------------------------
# DB writer
# ---------------------------------------------------------------------------


def build_index(runs_dir: Path, db_path: Path) -> tuple[int, int]:
    """Walk runs_dir and build the SQLite index. Returns (run_count, tool_call_count)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()  # rebuild from scratch — idempotent

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_RUNS + SCHEMA_TOOL_CALLS)
        for ddl in INDEXES:
            conn.execute(ddl)

        run_count = 0
        tool_count = 0
        for run_dir in sorted(runs_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            indexed = index_run(run_dir)
            if not indexed:
                continue
            run_row, tool_rows = indexed
            cols = ", ".join(run_row.keys())
            placeholders = ", ".join("?" for _ in run_row)
            conn.execute(
                f"INSERT INTO runs ({cols}) VALUES ({placeholders})",
                tuple(run_row.values()),
            )
            for tc in tool_rows:
                cols = ", ".join(tc.keys())
                placeholders = ", ".join("?" for _ in tc)
                conn.execute(
                    f"INSERT INTO tool_calls ({cols}) VALUES ({placeholders})",
                    tuple(tc.values()),
                )
            run_count += 1
            tool_count += len(tool_rows)

        conn.commit()
        return run_count, tool_count
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    default_runs = Path.home() / ".inderes_agent" / "runs"
    default_db = Path.home() / ".inderes_agent" / "evals" / "runs_index.sqlite"
    parser.add_argument("--runs-dir", type=Path, default=default_runs)
    parser.add_argument("--db", type=Path, default=default_db)
    args = parser.parse_args()

    if not args.runs_dir.is_dir():
        print(f"runs dir not found: {args.runs_dir}", file=sys.stderr)
        return 1

    n_runs, n_tools = build_index(args.runs_dir, args.db)
    print(f"indexed {n_runs} runs, {n_tools} tool calls → {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
