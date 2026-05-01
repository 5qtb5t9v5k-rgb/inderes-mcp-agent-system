"""Entry point: `python -m inderes_agent` (REPL) or `python -m inderes_agent "question"` (one-shot).

Startup sequence:
  1. Load .env, configure logging + tracing
  2. Eagerly run OAuth (or use cached token) so the browser opens BEFORE async work begins —
     this avoids 4 parallel agent builds racing on the same OAuth flow
  3. Dispatch to one-shot or REPL mode
"""

from __future__ import annotations

import asyncio
import sys

from dotenv import load_dotenv

from .cli import render
from .cli.repl import ConversationState, handle_query, repl
from .llm.gemini_client import QuotaExhaustedError
from .logging import configure_logging
from .mcp.inderes_client import prefetch_token
from .observability.tracing import setup_tracing


async def _one_shot(question: str) -> int:
    state = ConversationState()
    try:
        await handle_query(question, state)
        # Always emit a compact trace in one-shot mode so the user sees per-subagent
        # outcome — invaluable for debugging while the system is new.
        if state.last_workflow is not None:
            render.render_trace_compact(state.last_workflow, state.last_lead_model)
        return 0
    except QuotaExhaustedError as exc:
        render.render_error(str(exc))
        return 2
    except Exception as exc:
        render.render_error(f"{type(exc).__name__}: {exc}")
        return 1


def main() -> int:
    load_dotenv()
    configure_logging()
    setup_tracing()

    # Trigger OAuth eagerly so the browser opens here, not 4× concurrently inside async work.
    try:
        prefetch_token()
    except Exception as exc:
        render.render_error(f"Inderes OAuth failed: {exc}")
        return 3

    args = sys.argv[1:]
    if args:
        question = " ".join(args)
        return asyncio.run(_one_shot(question))
    asyncio.run(repl())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
