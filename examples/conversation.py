"""Multi-turn conversation example."""

from __future__ import annotations

import asyncio

from dotenv import load_dotenv

from inderes_agent.cli.repl import ConversationState, handle_query
from inderes_agent.logging import configure_logging


async def main() -> None:
    load_dotenv()
    configure_logging()

    state = ConversationState()
    for q in [
        "Anna pikakatsaus Konecranesista.",
        "Entä insider-aktiivisuus?",
        "Latest earnings call highlights?",
    ]:
        print(f"\n> {q}")
        await handle_query(q, state)


if __name__ == "__main__":
    asyncio.run(main())
