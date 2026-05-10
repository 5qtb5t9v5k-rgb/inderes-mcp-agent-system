# Agentic dev session — meta-analysis 2026-05-10

A snapshot of Claude Code's session-summary view, captured mid-sprint
(during the Wk 1 #4 feedback-widget commit `47da707`):

```
610 turns   3,439 tool calls   214h 35m   79.2k tokens
```

Cumulative numbers across the entire ~9-day sprint that took the
Inderes-agent from "Tier 0 evals + Plotly toggle on" to "Wk 1 fully
shipped" (charts, footnotes, hard limits, feedback). This doc unpacks
what those numbers reveal — both about the development pattern and
about the project itself, since this codebase is in the unusual
position of *being built with the same kind of agent fabric it ships*.

## TL;DR

- **610 turns / 9 days ≈ 68 turns per day average.** Heavy interactive
  usage, not autocomplete-style. Real ratio is bursty: the 14-commit
  day on 2026-05-09 was a peak, surrounded by quieter days.
- **3,439 tool calls / 610 turns = 5.6 tool calls per turn.** Confirms
  the working pattern is **search-heavy, not generate-heavy**. Each
  user message triggers ~5–6 file reads / greps / agent dispatches on
  average before code actually changes.
- **214h 35m = wall-clock session age, not active time.** Claude Code
  sessions persist across sleep / walks / context switches. Treating
  this as "time spent" overstates by 5–10×; the active fraction was
  closer to 20–40 hours of focused work.
- **79.2k tokens is the headline anomaly** — 9 days of dev with 600+
  turns and a context budget that never blew up. Aggressive context
  compression (summary handoffs, on-demand tool-schema loading) is
  doing the heavy lifting. Without it, naïve token usage at this
  conversation density would be ~5–10M tokens.

## What the ratios reveal

### Tool-calls-per-turn (5.6) — exploration-dominant

A "type-and-receive-suggestions" pattern would produce ~0.5 tool calls
per turn (mostly Edit + occasional Read). 5.6 is in the **agentic
research band**: each turn averages a Read-Read-Grep-Edit-Bash chain
or a single Agent dispatch that internally fans out further.

This matches the work the project actually demanded:

| Phase | Why high tool-call/turn |
|---|---|
| Footnote bugs | Each "tooltip not showing" report needed Reads across `components.py` (~2.7k lines), `theme.css`, plus a smoke-run trace dive |
| Plotly chart fixes | Multi-company batched-API-response parsing required following data through 4 files before the patch was obvious |
| Router refactor | Replacing keyword matching with semantic intent meant grepping across the whole `orchestration/` tree to find every call site |
| Eval foundation | Tier 0 SQLite indexer touched 183 run dirs — high read volume, low write volume |

### Tokens-per-turn (~130) — compression dominates

79.2k tokens / 610 turns = **130 tokens per turn average**. That's
absurdly low for conversations this rich; full transcripts would be
50–100× larger. The Anthropic-side machinery doing this:

- **Summary handoffs.** When context fills, the harness writes a
  durable summary and starts a new "compacted" context window. We
  hit this at least 2× during the sprint (once visible mid-this-doc).
- **On-demand tool-schema loading.** Most MCP tools are deferred —
  their JSONSchema only enters context when called. A naïve setup
  would burn ~10–30k tokens just on schemas at session start.
- **Selective Read excerpts.** The harness keeps a sliding window of
  recent file reads, not the full history.

The cost shape is: token usage grows roughly **linearly** with
the tool-call count, but **logarithmically** with the turn count.
That's the right shape for a long session — and it's the shape we
should be aiming for in our own product (LEAD synthesis context
should compress old subagent results, not concatenate them all).

### Wall-clock vs active time — 214h ≠ effort

214h35m / 24 ≈ **8.95 days**. Two weekends and 6 weekdays of session
lifetime, not labour. The active fraction is observable in the
commit graph:

- 14 commits on 2026-05-09 (peak day)
- 7 commits on 2026-05-10 (this Wk 1 wrap-up day)
- Smaller bursts on other days

Mapping commits to ~1–3 hours of focused work each, **active hours
are likely 30–50, not 215**. The 215 number is useful only as a
"how long has this collaboration been alive" signal — and that
matters for context discipline (a 9-day-old session has more drift
risk than a fresh one).

## What the stats do NOT capture

The numbers above are inputs and process. They say nothing about
**outputs and quality** — the things that would actually matter on
a project review. Worth naming the gaps:

| What's measured | What's missing |
|---|---|
| 610 turns | How many were productive vs course-corrections vs reverts |
| 3,439 tool calls | Hit rate (right file first time vs grep-grep-grep) |
| 79.2k tokens | Token cost — Sonnet vs Haiku mix not visible here |
| 214h 35m | Active focus time vs session lifetime |
| ✗ | **Bugs introduced** — the eval-driven cycle catches some but not all |
| ✗ | **Reverts** — we did at least one today (elapsed-time counter) |
| ✗ | **Decision quality** — was each refactor the right call? |
| ✗ | **User feedback signal** — the 👍/👎 widget that just shipped is itself the start of fixing this gap |

The right next-level dashboard would pair these stats with: commits,
test count, eval pass-rate trends, and the upcoming feedback.json
aggregation. The session view is necessary but not sufficient.

## The interesting feedback loop

This codebase is recursive in an unusual way: **we're building
agent ergonomics while using agent ergonomics**. The empirical
baselines that drive `RunBudget` defaults (Wk 1 #3, see
`src/inderes_agent/orchestration/limits.py`) came from **183
historical runs** of the inderes-agent itself — and the sprint that
produced those baselines is itself a long Claude Code session whose
own stats are above.

Cross-walking the two:

| Metric | Inderes-agent (per-run, p95) | This dev session (cumulative) |
|---|---|---|
| Tool calls | 14 | 3,439 |
| Wall-clock | 30s | 214h 35m |
| Cost cap | $0.50 | (much larger; not metered here) |

The shapes are radically different — a single agent run is *bursty
and bounded*, a dev session is *spread and unbounded*. But the
**lessons cross-pollinate**:

- The dev session uses **summary handoffs** to stay in budget;
  Inderes-agent's LEAD synthesis should do the same with old
  conversation turns once we ship multi-turn context (it currently
  only sees the latest query + a 400-char prior-summary).
- The dev session uses **on-demand tool-schema loading**;
  Inderes-agent's `mcp_catalog` initialisation could similarly
  defer rarely-used tools.
- The dev session has **no hard kill switch** because the human is
  in the loop; Inderes-agent **must** have one (Wk 1 #3 shipped
  this exact safeguard last week).

## Why this matters for the product

The Inderes-agent is fundamentally a trust product: an agent that's
allowed to call tools that touch real money decisions. Trust is
calibrated against **observable behaviour over time**, not against
single answers. Three artefacts of the dev process directly inform
the product:

1. **Tool-call telemetry as a quality signal.** The session metric
   *"agents that grep more before editing have fewer regressions"*
   should translate to a product metric: *subagents that emit more
   tool calls before answering have higher accuracy*. The Tier 0
   indexer can already test this hypothesis on the 183-run dataset.

2. **Token compression discipline.** The fact that 9 days of dev
   stayed under 80k tokens is proof that compression-first design
   works at scale. The LEAD synthesis prompt should adopt the same
   philosophy: never concatenate raw subagent outputs, always
   summarise first.

3. **The 👍/👎 widget shipped today is the user-facing analogue
   of the session summary view.** It captures the same kind of
   meta-signal — *was this conversation productive?* — but on a
   per-run basis. Feeding feedback.json into the eval indexer
   closes the loop: dev session quality and product session quality
   become symmetrical, queryable concepts.

## Action items surfaced

None of these are blocking, but worth capturing while the framing is
fresh:

- **§4 Tech debt:** add a session-meta dashboard to the eval indexer
  that joins `feedback.json` × `meta.json` × tool-call counts. Mirror
  of the Claude Code summary view, but per-run. Half-day's work after
  Tier 2 Supabase lands (Wk 3).
- **§1 AI capabilities:** consider an *active-time* metric in the
  run log — wall-clock minus idle (no events for >30s = idle). The
  difference between "the agent took 30s" and "the agent was waiting
  90s on Pro tier" is a calibration signal.
- **§6 Evals:** correlate tool-call-count with judge-pass-rate on
  the 183-run dataset. Hypothesis: more tool calls → higher
  factual grounding → higher pass rate, up to the 12-call cap.
  If the curve plateaus, our cap is well-calibrated; if it climbs
  through the cap, we're capping useful exploration.

---

*Captured automatically via screenshot during a Claude Code session
in `claude-code-pre-release-test`. Stats are point-in-time; the
session has continued since.*
