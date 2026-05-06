# AI briefing prompt

A prompt for any AI coding assistant (GitHub Copilot, Cursor agent,
Claude Code, Claude.ai with URL fetch, etc.) to read this repository
in a structured way and produce a briefing useful for someone applying
its patterns to a multi-agent project of their own.

## How to use

1. Copy the markdown block below.
2. Paste into your AI assistant of choice.
3. *(Optional, recommended)* prepend one line describing **your own
   idea X** — the multi-agent project you have in mind in a different
   domain. The briefing's section F is "applying these patterns to
   your own idea X" and is more useful when the AI knows what your X
   is. Example:
   > *"Idea X I'm thinking about: a multi-agent system for
   > pull-request review across a private GitHub org, where each
   > agent specializes in a code concern (security, perf, style,
   > test coverage) and a lead synthesizes a unified review. Read
   > the prompt below and respond per its structure."*
4. The AI will fetch this repo, read the listed files in order, skim
   the listed code paths, and produce a briefing with sections A-G.

The briefing is **not a summary of this project**. It's a
working document the reader can use while building their own X.

---

## The prompt

````markdown
TASK
====

Build a holistic mental model of this multi-agent system from the
repository, sufficient to apply its patterns to a multi-agent project
of your own. Do **not** produce a flat summary — produce a briefing
that surfaces the load-bearing ideas, tradeoffs, and unresolved hard
problems you will run into yourself.

CONTEXT
=======

This is a **proof of concept**, not production code. Treat the *thought
models* as load-bearing: the layered architecture, the failure-mode
classifications, the build-order arguments (evals before AI features),
the harness-as-its-own-layer reframing — those are the transferable
artifacts. The specific code is one concrete instantiation; some of it
is intentional, some is incidental, and the docs are deliberate about
distinguishing the two.

When reading: assume **you have an idea X for a similar system in a
different domain**. Your job is not to summarize this project, it's
to extract what about it survives the move to your X.

REPOSITORY
==========

https://github.com/5qtb5t9v5k-rgb/inderes-mcp-agent-system

READING ORDER (with specific extraction targets per file)
=========================================================

1. **README.md** — extract: what the system does at the surface,
   how it runs locally vs deployed, the documentation map (use it
   as your nav).

2. **PURPOSE.md** — extract: *why* the project exists (it's an
   intentional learning vehicle, not a product), the trajectory
   from single-agent to multi-agent, what counts as
   "production-tested" here, and what is deliberately excluded.

3. **ARCHITECTURE.md** — extract: file-by-file mapping of the
   current implementation, the key design decisions section, and
   "what this is and isn't".

4. **MULTI_AGENT_ARCHITECTURE.md** — *most transferable doc.*
   Extract: the generic layered model (Surface / Brain / Action /
   Data / Harness + Evals & Governance planes + Memory tiers),
   how this project maps to it, the per-layer "critical pitfalls"
   sections, and the use-case risk classification.

5. **LESSONS.md** — extract: the AI / UI / Infrastructure
   ~30/20/50 split, the concrete worked examples (parked Pro
   toggle, OAuth as biggest time sink, gist mirror + cron, etc.),
   and the "things I'd do differently" section.

6. **BACKLOG.md** — extract: what's prioritized and why. Pay
   attention to the new sections "Tool-result-rehellisyys" and
   "Evals-rakentaminen — ennen muiden featureiden lisäämistä".
   Note the explicit build-order argument: evals foundation
   before AI-capability features.

7. **evals/known-failure-cases.md** — extract: Case 001
   (hallucination from training memory) and Case 002 (cherry-pick
   without region filter). These are concrete documented model
   failures with tool-result comparison data. Note especially that
   they are **two different failure modes** producing the same
   surface bug, and what that implies about prompt-engineering
   ceilings.

8. **CHANGELOG.md** — extract: trajectory v0.1 → v0.2, with focus
   on the proportion of UI vs prompt vs infrastructure changes.

CODE TO SKIM (shape, not line-by-line)
======================================

- `src/inderes_agent/orchestration/{router.py, workflows.py,
  synthesis.py}` — three-stage Brain: classify → fan out → synthesize.
- `src/inderes_agent/agents/prompts/*.md` — Harness layer made
  concrete: per-agent system prompts including anti-capabilities.
  Some are in Finnish.
- `src/inderes_agent/llm/gemini_client.py` — multi-vendor LLM
  fallback wrapper (primary 503 → fallback model).
- `src/inderes_agent/mcp/{oauth.py, inderes_client.py}` — OAuth
  PKCE flow + tool wrapping with JSON-Schema sanitization +
  rotation-race recovery.
- `scripts/refresh_inderes_tokens.py` +
  `.github/workflows/refresh-inderes-tokens.yml` — cron heartbeat
  infrastructure for keeping cloud SSO sessions warm. Note this
  is **triggered by an external scheduler (cron-job.org)** because
  GitHub Actions free-tier scheduling proved unreliable.
- `ui/app.py` — Streamlit "Trading Desk" surface with
  public-safe error handling, recovery counter, and embedded
  demo video on auth-expired card.
- `scripts/relogin.sh` — one-shot recovery flow for the
  predictable ~10h Inderes Keycloak SSO Session Max.

OUTPUT — write a briefing with exactly these sections
=====================================================

**A. What this system does today** — concrete capabilities only,
no aspirations. Surfaces, what queries work, where it runs.

**B. Core architecture in one screenful** — the five layers, one
paragraph each, mapped to actual files in the repo. Mention what
sits on top of what.

**C. The load-bearing patterns** — ranked by how broadly they apply.
What about this project survives a move to a different domain
(different MCP, different LLM, different surface)? Be specific
(name the pattern, not generic "good logging").

**D. Current known limitations** — taken honestly from the docs
plus what you noticed reading the code. Include the empirically
measured Inderes Keycloak SSO Session Max = 10h hard cap and the
GitHub Actions free-tier scheduler unreliability.

**E. Unresolved hard problems** — specifically the AI capability
gaps documented in `evals/known-failure-cases.md`. Explain why
prompt-engineering alone has hit a ceiling against these and
what the project's BACKLOG identifies as the structural fixes
(reflection + retry, tool-result entity validation,
result-completeness check, stronger synthesis model). These are
the same hard problems any non-trivial multi-agent project will
run into; treat them as a preview of your own future debugging.

**F. Applying these patterns to your own idea X** — given the
project's stated thought models (layered architecture, harness as
its own layer, evals-before-AI-features sequencing,
risk-tiered use-case classification), how would you apply them to
a multi-agent project in your own domain? Concretely: what would
your Surface/Brain/Action/Data/Harness layers be, where would
your governance plane activate, what's your equivalent of "Inderes
Premium MCP" as a constrained data source, and what early
failures should you anticipate building against. This is the
section that justifies reading the repo at all — go as deep here
as the material warrants.

**G. Things I'm uncertain about after this read** — gaps,
contradictions, places where docs and code disagree, things the
docs are intentionally vague about. Be honest; this section is
the most useful for both you (the reader applying patterns) and
the project owner (who can clarify the next iteration).

CONSTRAINTS
===========

- **Some files are in Finnish** (BACKLOG.md, parts of
  prompts/*.md, parts of LESSONS.md). Translate as needed but
  quote meaningfully when it matters.

LENGTH
======

Comprehensive. The briefing should cover sections A-G completely,
with section F getting whatever depth the material warrants —
that's the section that justifies the whole exercise. Don't
artificially compress; length follows depth, not the other way
around.
````

---

## Notes for the project owner

If this prompt is updated, also consider whether:

- **The reading order in PURPOSE.md** is still aligned (suggested
  reading order shows up in two places; they should match)
- **Newly added top-level docs** should be inserted into the prompt's
  reading order
- **`evals/known-failure-cases.md` has new cases** beyond Case 001
  and Case 002 — if so, mention them by ID in the prompt so the AI
  knows to extract them all

The prompt is intentionally **opinionated about output structure**
(sections A-G, in that order) so that briefings produced by different
AI assistants stay roughly comparable. If you change the structure,
expect to lose comparability across runs.

---

*Document version: 2026-05-06 · v1*
