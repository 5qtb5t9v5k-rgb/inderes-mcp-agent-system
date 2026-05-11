# Research prompt — Agentic AI expansions for personal investment research

**Date:** 2026-05-11
**Use:** paste into a deep-research session (Claude / Gemini Deep Research / ChatGPT o-series / your favourite). The prompt is self-contained.

---

## Concrete case (the system this research informs)

`inderes-mcp-agent-system` — a personal LLM-agent for Finnish + international stock research. Stack:

- **Microsoft Agent Framework (MAF)** for agent lifecycle + AFC tool-loop
- **Gemini** models (Flash Lite primary, Flash fallback, Pro for "deep mode")
- **Two MCP servers** as data sources:
  - `inderes-mcp` (private OAuth, owns Finnish equity analysis: ROE history, analyst targets, transcripts, forum sentiment, model portfolio)
  - `yahoo-finance-mcp` (own MIT-public sidecar built 2026-05-11, owns international coverage + Q-fresh price/BVPS via yfinance)
- **5 subagents** (QUANT, RESEARCH, SENTIMENT, VALUATION, PORTFOLIO) + a LEAD synthesizer + a planner + a conflict-detector + fabrication guard
- **Streamlit Cloud** front-end, single-user, daily query cap
- Per-agent tool partitioning (each subagent sees only its domain's tools, mirroring Bloomberg Terminal's role-based screens)

Empirically observed today (15-query test session):
- LLM **discovered Yahoo tools from descriptions alone** — `get_holders(MSFT)` and `get_history(NVDA)` fired without any prompt nudge
- **Cross-source consensus emerged organically** on one query — LLM planned + executed "Inderes target vs Yahoo consensus side-by-side" as a natural reasoning step
- **Cross-source retry GAP** is real — when Inderes search returned empty for ASML / Smart Eye, research+sentiment agents fab-guarded instead of trying Yahoo

## The research question

**What is the full taxonomy of "agentic expansions" available to a single-user, multi-source, MCP-based research agent — and how would one prioritise them against measurable user experience improvements?**

In other words: we have a working multi-agent baseline. What does the *next 12 months* of expansion look like if the goal is "full agent experience" (= the agent feels like a real research analyst working alongside the user, not just a chat tool)?

## Avenues to investigate

### A. Reasoning + reflection patterns

1. **Reflexion / self-critique loops** — anomaly detection + retry-with-context. How do labs deploy this without exploding cost? Where does the cost/quality curve plateau?
2. **Devil's advocate / Bull-Bear debate** — adversarial pairing. State of the art: is single-pass critique enough or do multi-turn debates produce materially better synthesis? What's the empirical evidence (DeepMind debate papers, Anthropic's debate-of-experts work)?
3. **Tree of Thoughts / Graph of Thoughts** — branching reasoning. Practical for a personal-use research agent or overkill? When do users actually benefit from exploring multiple reasoning paths?
4. **Magentic Progress Ledger** (Microsoft) — inner-loop state for multi-agent orchestration. Spec is public. Production-tested? Failure modes?
5. **Confidence calibration** — agents reporting 1-5 confidence per claim. What scoring rubrics actually work? Does the LLM's self-reported confidence correlate with truth (Karpathy's calibration work, recent calibration evals)?

### B. Tool surface expansion

6. **Cross-source retry / fallback patterns** — when source A is empty, agent considers source B before giving up. Prompt-level vs code-level vs trained behaviour. Industry state of the art?
7. **Tool discovery from descriptions** — empirically the LLM picks the right tool when descriptions are concrete. What's the failure boundary? How do successful agentic systems write tool descriptions?
8. **Function composition** — agents chaining tools (e.g. `search_ticker → get_snapshot → get_history → plot`). When does this need explicit prompt scaffolding vs emerging organically?
9. **Web grounding** (Google Search, Bing, Perplexity-style) — production case studies of integrating web search alongside vetted tool sources without diluting provenance.

### C. Human-in-the-loop (HITL)

10. **Pre-flight cost gates** — show user *"this will cost ~$0.04 and take 30 s, proceed?"* before expensive operations. State of the art for cost estimation accuracy.
11. **Mid-flight checkpoints** — agent pauses on critical decisions (e.g. before publishing, before transacting, before committing data changes). What checkpoint UX has been validated?
12. **Approval modes** — never-require / require-all / require-suspicious. Industry-standard approval mode policies (cf. MAF approval_mode, OpenAI Assistants API).

### D. Memory + personalization

13. **Insight ledger / long-term memory** — agent distils 1-3 takeaways per query → loaded into future contexts. What memory architectures are actually working in production (mem0, Letta, MemGPT, Claude Projects)?
14. **User preference learning** — agent picks up "user prefers conservative ROE assumption" or "user always wants comparison vs sector peers". Is this realistic without explicit feedback loops or does it stay a fantasy?
15. **Watchlist + proactive briefings** — user marks "watch Sampo"; agent runs morning brief autonomously. Cron + LLM cost model — what's the threshold where proactive becomes valuable vs annoying?

### E. Multi-agent orchestration

16. **Agent partitioning strategies** — per-domain (our approach) vs per-step vs per-user vs hybrid. Empirical wins documented in MAF / AutoGen / CrewAI / LangGraph literature?
17. **Conflict detection** — between agents reaching contradictory conclusions. We have this as a side-process LLM call. State of the art for inter-agent disagreement resolution?
18. **Auto-orchestrator / meta-router** — LLM decides which agents + which tier dynamically based on query shape. Magentic-One? Bedrock multi-agent collaboration? What's working in production?

### F. Trust + provenance

19. **Per-claim footnote markers + source panels** — `[¹]` markers tracing each claim to its tool call. Anthropic's citations? Perplexity's source UX? Best practices?
20. **Fabrication guards** — structural enforcement against zero-tool-call answers. We have this. What's the broader literature on structural guards (vs prompt guidance)?
21. **Hard limits at orchestration boundary** — max_iter / max_tool_calls / max_cost / max_duration / kill switch. OWASP Agentic Top 10 #T1 (excessive agency). Implementation patterns in production agents?

### G. Output quality + UX

22. **Always-on visualization** — when data is plot-able, render automatically. Token-budget aware approaches: how do production agents (Tableau Pulse, Hex Magic, Julius AI) handle the LLM-context-vs-UI-render split for tabular and time-series data?
23. **Streaming output** — token-by-token rendering with tool-call interruption support. State of the art in chat agent streaming + interrupt UX?
24. **Multi-modal output** — agents emitting Plotly + tables + markdown + audio narration. Where is this actually working vs marketing?

### H. Operational robustness

25. **Quota / rate-limit handling** — distinguishing per-minute (retry) vs per-day (give up) vs per-tokens vs concurrent (throttle). Production patterns from OpenAI / Anthropic / Google SDK consumers.
26. **Stale-fallback caching** — when upstream breaks, serve last known with freshness flag. Industry-standard cache architectures for LLM tool calls?
27. **Health checks + canary probes** — daily scheduled probes of MCP servers + LLM endpoints to detect upstream drift before users hit it.

### I. Evaluation + continuous improvement

28. **Golden test suites for agents** — case_NNN.yaml with expected tools, claims, refusals. How do leading labs operationalize this? (cf. OpenAI's evals, Anthropic's evaluation framework, Stanford HELM)
29. **Autonomous nightly evals + self-repair** — cron runs eval suite, prompts-only auto-fixes for regressions, alerts otherwise. Anyone actually shipping this in production?
30. **Human feedback loops (👍/👎)** — minimal viable feedback UI + how it feeds back into eval set + prompt updates. Production patterns?

## Specific lens — what makes this case unusual

- **Single-user**, not multi-tenant — design tradeoffs simplify (no auth-per-user, no rate-fairness between users, no shared memory contamination)
- **Domain-specific** (Finnish + international equity research) — not general-purpose. Tool surface is bounded, evaluation is tractable, success criteria are concrete (was the answer factually right + did it cite sources + did it admit unknowns)
- **Free-tier-bias** — Inderes MCP + Yahoo MCP + Gemini API + Streamlit Cloud + Fly.io are all free or near-free. Cost discipline is real. Lessons should account for "what would I do if I had $0 vs $50/month vs $500/month budget"
- **MIT-public artefacts where possible** — `yahoo-finance-mcp` is intentionally MIT-open so the broader MCP community can reuse. Architectural decisions should favour reusable building blocks over monolithic vendor lock-in

## Desired output

A structured research write-up that:

1. **Surveys current state** for each avenue A–I (cite specific papers, products, GitHub repos, blog posts, conference talks where possible — actual evidence beats hand-waving)
2. **Ranks the 30 avenues** by expected impact-per-effort for *this specific case* (single-user investment research, MAF + Gemini stack)
3. **Identifies the top 5–8 expansions** worth pursuing in the next 12 months, with effort estimates and prerequisite chains (what unblocks what)
4. **Flags emerging tech to watch** — what's coming in late-2026 / 2027 that would change the prioritisation (new model capabilities, new MCP features, new agent frameworks)
5. **Calls out anti-patterns** — what looks attractive but actually fails in single-user low-budget settings

Keep it analytical, not promotional. Where industry hype outpaces evidence, say so. Where evidence is genuinely strong, say so concretely (papers, benchmarks, production deployments).

## Reading recommendations to seed the research

**Pattern catalogues (start here — they are the canonical maps of the space):**

- **[nibzard/awesome-agentic-patterns](https://github.com/nibzard/awesome-agentic-patterns)** —
  curated catalogue of ~178 patterns across 8 categories (Context &
  Memory, Feedback Loops, Learning & Adaptation, Orchestration &
  Control, Reliability & Eval, Security & Safety, Tool Use &
  Environment, UX & Collaboration). Each entry must be traceable to
  a public source (blog, talk, repo, paper) — no marketing material.
  Companion website at <https://agentic-patterns.com> has a Pattern
  Explorer, Compare Tool, and Decision Explorer. **Direct hits with
  this project (~20 patterns already implemented under different
  names):** Tool Capability Compartmentalization (= our per-agent
  tool partition), Sub-Agent Spawning, Plan-Then-Execute, Opponent
  Processor (= conflict detector), Output Verification Loop (=
  fabrication guard), Schema Validation Retry (= valuation parser),
  Verbose Reasoning Transparency (= `**Ajatus:**` opener), Failover-
  Aware Model Fallback, Filesystem-Based Agent State, Workflow
  Evals with Mocked Tools. **Novel patterns we don't yet have but
  should consider:** Lethal Trifecta Threat Model (Simon Willison),
  Action Caching & Replay Pattern, Tool Search Lazy Loading,
  Subject Hygiene for Task Delegation, Burn the Boats.

- **[Google Cloud — Choose a design pattern for your agentic AI
  system](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system)**
  — cloud-vendor architectural decision framework (~10 macro
  patterns). Strong on decision criteria (task complexity / latency /
  cost budget / human involvement). Identifies Single-Agent,
  Sequential, Parallel, Loop, Iterative Refinement, Review and
  Critique, Coordinator, Hierarchical Task Decomposition, Swarm,
  ReAct, Human-in-the-Loop, Custom Logic. **This project maps to a
  Parallel + Coordinator + Hierarchical + Review/Critique hybrid.**
  Google's guidance "avoid complex multi-agent when simpler
  suffices" worth reflecting on: do we over-architect for our actual
  problem complexity? Probably yes for trivial queries (single-name
  price lookup) — see auto-orchestrator / meta-router idea in §1.

**Foundational papers + writeups:**

- *State of the possible* (presumably the source for our §9 patterns — see existing BACKLOG.md)
- Microsoft Agent Framework docs + Magentic-One paper
- OWASP Agentic AI Top 10 (2026)
- Anthropic's "Building agents" / "Computer use" technical notes
- LangGraph + CrewAI + AutoGen production case studies (where they exist)
- Bloomberg's ASKB announcement (their LLM-agent layer over Terminal data)
- Perplexity, Hex Magic, Julius AI — vertical-AI productivity agents in adjacent domains

**Production case studies / blog posts to surface:**

- Cursor / Replit / Continue.dev — agentic coding patterns (relevant
  even for non-code domains: heavy fan-out + iterative refinement +
  HITL approval)
- Hex Magic / Julius AI — agentic data analysis (closest UX-analogue
  to investment research: structured queries + chart-rendering +
  step-by-step transparency)
- Perplexity Pro / DeepResearch — multi-source synthesis with
  citation discipline (the source-badge model we want to evolve)

---

*Generated 2026-05-11 from the Inderes agent project's BACKLOG.md context. Self-contained as a research prompt — paste into a fresh deep-research session and it will run.*
