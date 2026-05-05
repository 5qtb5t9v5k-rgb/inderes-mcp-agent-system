# Purpose

This is a learning project. It exists to develop, in practice, a working
understanding of how agentic systems are actually built — not how they
look in posts and demos.

The other documents in this repository describe **what** the project is
and **how** it's built. This one describes **why**.

---

## What "in practice" means here

The substrate is Inderes Premium MCP, used through the author's own
subscription. The Nordic-equity research domain is a real one with real
data, real edge cases, and real consequences if a question is answered
sloppily. Building against it produces lessons that transfer; a synthetic
toy agent against fabricated data does not.

The project is intentionally **iterative**. Each iteration exposes a
class of problems the previous one didn't, and the solutions become
artifacts — code, prompts, documentation — that capture the move
forward. The artifacts are as much the point as the running system.

## Trajectory

The project started from a clearly-agentic foundation — one LLM, a few
tools, a tool-calling loop — and is moving toward clearly multi-agent
systems that work reliably in production:

- **v0.1** — single-agent foundation, one Gemini call against 16 MCP
  tools, REPL surface, basic forensic logging
- **v0.2** *(current)* — five-agent fan-out (LEAD + QUANT + RESEARCH +
  SENTIMENT + PORTFOLIO), Trading Desk UI, durable cloud-deployable
  OAuth (gist mirror + external cron), public-safe error handling,
  reliable cross-platform keepalive, empirically-measured IdP
  constraints, layered architecture model documented as a generic
  primer
- **future** — see [`BACKLOG.md`](BACKLOG.md) and
  [`MULTI_AGENT_ARCHITECTURE.md`](MULTI_AGENT_ARCHITECTURE.md) for the
  trajectory toward measurable quality (golden datasets, user feedback),
  reflection-and-retry loops, proactive workflows (watchlist briefings,
  insight ledger), and the move from purely reactive to event-driven
  agentic patterns

The trajectory is not linear. Earlier failed attempts (Claude Agent SDK
"do everything", Cursor agent mode) are part of the record; the current
direction emerged from those failing first. See `LESSONS.md` →
*"Aikomuksesta toimivaan"* for the longer narrative.

## What "production-tested" means here

**Not** "deployed as SaaS to thousands of users". This is, **for now**,
a single-user personal tool — where the road leads is open, but the
current scope is the author's own desk.

**Production-tested** here means the system:

- runs continuously in the cloud, not just on the author's laptop
- survives real-world failure modes — container restarts, IdP idle
  timeouts, scheduler unreliability, transient API errors, capacity
  spikes — tested empirically and documented
- handles its own errors public-safely: no leaked tracebacks, no
  exposed local paths, no internal IDs surfacing to whoever happens
  to be looking
- is reproducible: every query writes a forensic record sufficient to
  replay it after the fact
- has bounded, predictable cost: single-digit cents per query, no
  surprise blowups

A system that demos beautifully but folds at deployment teaches little
about *production* agentic systems. A system that runs for months
despite unreliable infrastructure teaches a great deal.

## What's actually transferable

The deliverable of this project is not the Inderes-research tool itself
— it's the body of practical knowledge accumulated while building it:

- [`LESSONS.md`](LESSONS.md) — reflective build journal: what AI / UI /
  infrastructure each contribute, with concrete examples and the things
  that would be done differently the second time around
- [`MULTI_AGENT_ARCHITECTURE.md`](MULTI_AGENT_ARCHITECTURE.md) — generic
  layered model (Surface / Brain / Action / Data / Harness + Evals &
  Governance planes + Memory tiers) for thinking about any non-trivial
  multi-agent system, with this project as the worked example
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — file-by-file walkthrough of
  one specific concrete implementation, for anyone wanting to see what
  the abstractions look like in actual code
- The **codebase itself** — patterns for OAuth-protected MCP
  integration, multi-vendor LLM fallback, JSON-schema sanitization,
  persistent cloud session keepalive via gist + external cron,
  public-safe Streamlit error UI, fan-out via `asyncio.gather` +
  semaphore, forensic per-run logging

These should scale to any other multi-agent project: different domain,
different tools, different model, different surface. The patterns are
load-bearing; the Inderes specifics are not.

## What this project is NOT

These exclusions are deliberate and worth stating explicitly:

- **Not a commercial product (currently).** Single user, personal
  Premium subscription, open source under permissive terms, no
  monetization in place, no scale path actively planned. Where the
  road leads from here is genuinely open — this section reflects
  current scope and intent, not a permanent constraint. If the
  project grows past single-user use someday, this document will be
  the first thing to update.
- **Not investment advice.** The system surfaces Inderes' own
  recommendations, target prices, insider activity, and analyst views;
  it does not generate buy/sell calls of its own opinion. The user
  decides; the agent shows the data.
- **Not affiliated with Inderes Oyj.** Independent project that uses
  the publicly available Premium MCP through the author's own
  subscription. All Inderes analyst content surfaced by this system
  is © Inderes Oyj.
- **Not a benchmark.** The forensic logging exists for debugging and
  learning, not for publication metrics or model comparisons.
- **Not a substitute for human judgment.** The system at its best is
  a research desk that compresses hours of source-hopping into
  seconds. The decisions still belong to the person reading.

## Reading order

For someone (you, six months from now; a collaborator; a curious
reader) coming to this project for the first time:

1. [`README.md`](README.md) — what it does, how to run it
2. **`PURPOSE.md`** *(this file)* — why it exists
3. [`ARCHITECTURE.md`](ARCHITECTURE.md) — concrete current
   implementation, file by file
4. [`MULTI_AGENT_ARCHITECTURE.md`](MULTI_AGENT_ARCHITECTURE.md) —
   generic layered model with this project as worked example
5. [`LESSONS.md`](LESSONS.md) — reflective build journal
6. [`BACKLOG.md`](BACKLOG.md) — what's next, classified by where
   it sits on the architecture

Reading those six gives a complete picture of: what the system is,
why it exists, how it's built, what's been learned, and where it's
heading.

---

*Document version: 2026-05-05 · v1*
