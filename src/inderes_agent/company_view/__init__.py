"""Company-view mode — sustained-monitoring layer on top of the agent.

Per the design brief at
`docs/design_briefs/company_leaderboard_2026-05-12.md`, this package
holds:

- `leaderboard_data` — current source of leaderboard rows (mock today,
  SQLite-backed nightly-batch tomorrow)
- (future) `buy_grid` — buy-price 5×3 computation per company
- (future) `notebook` — per-ticker markdown notes IO

The agent engine in `src/inderes_agent/{agents,llm,mcp,orchestration}`
remains the drill-down explanation tool; this package provides the
sustained-monitoring surface that calls into it.
"""
