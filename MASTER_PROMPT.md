# MASTER PROMPT — paste into Cursor agent mode

You are an autonomous coding agent. Build the `inderes-research-agent` project specified in `BUILD_SPEC.md` (in this same directory).

## Mission

Build a multi-agent stock research conversation system that:
- Uses **Microsoft Agent Framework** (Python, version 1.0+)
- Uses **Google Gemini** with free-tier-realistic model selection:
  - Primary: `gemini-3.1-flash-lite-preview` (free, occasionally returns `503`)
  - Fallback: `gemini-2.5-flash` (free, more reliable)
  - **DO NOT use `gemini-2.5-pro`** — it's quota-zero on free tier (`429 RESOURCE_EXHAUSTED`). Even if your training data suggests it for synthesis, this build runs free-tier only.
- Connects to **Inderes MCP** at `https://mcp.inderes.com`
- Has 5 specialized agents (lead + 4 subagents: quant, research, sentiment, portfolio)
- Implements **automatic model fallback** (Section 6.8 of spec) — `503` retry then fallback to secondary
- Runs as a CLI tool: `python -m inderes_agent "your question"` or interactive REPL

End state: user can ask natural language questions about Nordic stocks ("How's Konecranes looking?", "Compare Sampo and If P&C") and the multi-agent system orchestrates the right Inderes MCP calls and synthesizes a useful answer — all on free-tier Gemini quotas.

## Process

1. **Read `BUILD_SPEC.md` completely** before any code
2. **Verify framework APIs** by fetching:
   - https://learn.microsoft.com/en-us/agent-framework/python/ (latest API)
   - https://github.com/microsoft/agent-framework (repository)
   - https://learn.microsoft.com/en-us/agent-framework/integrations/mcp (MCP integration specifics)
   The framework was renamed and updated to 1.0 in April 2026 — your training data may be stale. Verify before coding.
3. **Generate the full project** per Section 5 structure
4. **Run** `pip install -e .`, smoke tests, and a single example query
5. **Iterate** on errors until acceptance criteria pass

## Your authority

You may:
- Make implementation choices the spec doesn't cover
- Choose specific MAF orchestration patterns (sequential / concurrent / handoff / group chat / Magentic-One) per orchestration need
- Write the subagent system prompts (`src/inderes_agent/agents/prompts/*.md`)
- Add reasonable error handling and retries
- Use the latest stable versions of packages
- Decide between native Gemini SDK and OpenAI-compatible endpoint based on what's cleanest

You may NOT:
- Change the framework choice (must be Microsoft Agent Framework)
- Change the LLM provider (must be Gemini)
- Change the data source (must be Inderes MCP)
- Add a web frontend (CLI only)
- Have agents that recommend BUY/SELL — they surface signals only

## Constraints

- Python 3.11+
- All API verification against official docs, not training data
- Inderes MCP uses OAuth — first-run browser flow is expected; don't try to work around it
- User must have Inderes Premium subscription (document in README, don't try to fix at code level)

## Output

When done, summarize:
1. Files created (count + tree)
2. Smoke test results
3. Any spec deviations + reasoning
4. What user must do manually (env setup, Inderes Premium, OAuth)

Begin by reading `BUILD_SPEC.md`. Tell me the orchestration pattern decisions you'll make for each example query in Section 8 before generating code.
