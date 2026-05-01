"""One-shot query example: `python examples/single_question.py`"""

from __future__ import annotations

import asyncio

from dotenv import load_dotenv

from inderes_agent.cli.repl import ConversationState, handle_query
from inderes_agent.logging import configure_logging


async def main() -> None:
    load_dotenv()
    configure_logging()
    state = ConversationState()
    await handle_query("What is Konecranes' current P/E?", state)


if __name__ == "__main__":
    asyncio.run(main())
