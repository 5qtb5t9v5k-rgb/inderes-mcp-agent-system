"""Reproduce a Tila C valuation run from CLI.

Mimics the UI's valuation-toggle flow: classify → append VALUATION →
dispatch → synthesize. Lets us verify the LEAD synthesis structure
(does it actually emit ## 🔢 Oma arvonmääritys?) without the Streamlit
UI in the loop.

Usage::
    python scripts/repro_valuation.py "arvonmääritys huhtamäki"

Writes the run to ~/.inderes_agent/runs/<ts>/ as usual; prints the
synthesis text to stdout so you can grep for `## 🔢 Oma arvonmääritys`.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import time

from inderes_agent.observability.run_log import new_run_dir, write_run
from inderes_agent.orchestration.router import (
    Domain,
    classify_query,
    query_has_valuation_intent,
)
from inderes_agent.orchestration.synthesis import synthesize
from inderes_agent.orchestration.workflows import run_workflow


async def main(query: str) -> None:
    run_dir = new_run_dir()
    print(f"run_dir: {run_dir}")
    t_start = time.time()

    classification = await classify_query(query)
    print(f"router: domains={[d.value for d in classification.domains]} "
          f"companies={classification.companies}")

    # Mirror ui/app.py:1078 — append VALUATION when intent gate fires.
    if (
        classification.companies
        and query_has_valuation_intent(query)
    ):
        if Domain.VALUATION not in classification.domains:
            classification.domains.append(Domain.VALUATION)
        if Domain.QUANT not in classification.domains:
            classification.domains.append(Domain.QUANT)
        print(f"appended VALUATION → domains={[d.value for d in classification.domains]}")

    workflow_result = await run_workflow(query, classification, run_dir=run_dir)

    answer, lead_model, trace = await synthesize(query, workflow_result)

    write_run(
        run_dir=run_dir,
        query=query,
        workflow=workflow_result,
        answer=answer,
        lead_model=lead_model,
        duration_s=time.time() - t_start,
        synth_trace=trace,
    )

    print()
    print("=" * 72)
    print("SYNTHESIS:")
    print("=" * 72)
    print(answer)
    print("=" * 72)
    print(f"\n# Sections containing '## ':")
    for line in answer.splitlines():
        if line.startswith("## "):
            print(f"  {line}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python scripts/repro_valuation.py '<query>'", file=sys.stderr)
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
