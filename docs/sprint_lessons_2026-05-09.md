# Sprint lessons — 2026-05-09 / 10

A long session. We started with UI polish, ended with the eval foundation
and 8 production-grade fixes, each of which is now locked behind unit
tests. This doc captures **what we learned**, **why the priorities are
shifting**, and **how the backlog should re-order from a senior-PM lens**.

## TL;DR

- **Eval foundation works.** Tier 0 (SQLite indexer over 183 historical
  runs) + Tier 1 (golden.yaml + Gemini-Pro judge) surfaced 7 concrete
  weaknesses that had been silently corrupting outputs for weeks.
- **Pattern: HARD GATE in agent prompts** beat every flaky-tool-call
  bug we hit. Universal Flash-Lite tendency to "answer from memory"
  required prompt-side enforcement on all 5 subagents.
- **Pattern: code-level pre-pend banners** beat prompt-buried rules
  for LEAD synthesis structure adherence. Tila C completion 1/3 → 5/5.
- **Trust trumps appearance.** Failing visibly ("ei tällä kertaa
  onnistunut") is a UX downgrade short-term but a trust upgrade
  long-term. The user explicitly endorsed this trade.
- **User priorities for next sprint:** *charts (Plotly)* > *retry
  (Reflexion)* > *sources/footnotes* > *evals minttiin*. Reordering
  the backlog accordingly.

## Today's commits (chronological)

| # | Commit | What | Lesson it taught |
|---|---|---|---|
| 1 | `465b22e` | Hero settings expander + FI/EN switcher + roadmap | UX-polish discipline matters; small additions add up |
| 2 | `5be14f9` | Drop duplicate chevron + use st.expander | `<details>` interactivity in Streamlit is fragile; `st.expander` is robust |
| 3 | `37cdd0c` | Tier labels mention model + expandable help; SETTINGS font | Model names in UI = trust; `?` icon is the right help affordance |
| 4 | `349c889` | Plan expander = st.button toggle | When `<details>` clicks fail, `st.button + session_state` always works |
| 5 | `cac33a0` / `4b4bb43` / `b1a91b1` | Slim ASETUKSET typography, fix material-icons leak | Streamlit DOM differs across versions; aggressive `body:has()` selectors > `+ sibling` chains |
| 6 | `9bcf4f0` | **Tier 0 evals** — SQLite indexer, diagnostic SQL, findings | Indexing 183 historical runs surfaced 7 systemic bugs in 1 hour |
| 7 | `8971f66` | **Tier 1 evals** — golden.yaml + Gemini-Pro judge | LLM-as-judge with structured rubric works; baseline locked |
| 8 | `5e5dea7` | Comparison routing floor | Router prompt's own example was the bug source; post-processor as belt-and-braces |
| 9 | `870749a` | Fabrication guard + no-data short-circuit | Trust-killer pattern is universal; needs both prompt + orchestration enforcement |
| 10 | `80c6fd0` | Päättely prose→slots + stronger conflict prompt | Hidden 4-paragraph spec was already perfect data — UI just wasn't reading it |
| 11 | `152c3bf` | Trend classifier severe-decline branch | A 5-line domain rule fixed 3 consecutive UPM failures |
| 12 | `08e7e93` | Valuation HARD GATE + Tila C banner | Code-level pre-pend banner > prompt-buried rules; verified 5/5 |
| 13 | `d36dd72` | Sentiment HARD GATE | Same pattern; one prompt block, applies cleanly |
| 14 | `2039967` | Research + quant + portfolio HARD GATE | Pattern is universal across subagents; apply proactively |

14 commits, 7 distinct lesson categories below.

## Lesson 1 — HARD GATE: prompt-side MCP enforcement

**The bug:** Flash Lite occasionally answers a query from training
memory without calling MCP tools. Outputs look plausible — target
prices, ROE history, forum quotes — but the data is invented. We hit
this on all 5 subagents (valuation, sentiment, research, quant,
portfolio) over the day.

**The fix pattern:**

```markdown
## ⛔ HARD GATE — MCP TOOL CALLS ARE MANDATORY ⛔

Before you emit any [output type], you MUST execute these tool calls:

1. search-companies(query) — resolve id
2. <agent-specific tool>

A response with ZERO MCP tool calls is automatically rejected as
fabrication. Numbers/quotes from training memory are FORBIDDEN.

If a tool returns nothing useful, state that fact — do NOT compensate
by inventing data from memory.
```

Placed at the **top** of each prompt, before the existing structure.

**Why it works:** Flash Lite drifts through long prompts and obeys
recent attention more than buried instructions. A prominent block at
the top with explicit forbidden-action language fires before the model
"decides" to skip tools.

**Backstop:** the orchestration-level fabrication guard
(`workflows.py:_detect_fabrication`) catches anything the HARD GATE
fails to enforce. Two layers, neither alone sufficient.

**Empirical:** valuation pre-fix hit fabrication ~1/3, post-fix 0/5.
Sentiment same. The pattern reliably eliminates the failure class.

## Lesson 2 — Code-level banners > prompt-buried rules

**The bug:** LEAD has a 600-line prompt. Tila C structure (4-section
output for valuation queries) is documented in §260+, but Flash Lite
emitted it only ~2/3 of the time. The other 1/3 it produced Tila B
("valuation skipped") even though the engine succeeded.

**The fix:** at synthesize() time, when `valuation_records` contain
real engine output, pre-pend a high-visibility banner to LEAD's
prompt:

```
⚠️ TILA C — VALUATION ENGINE COMPUTED SUCCESSFULLY ⚠️
You MUST emit the four-section structure: [...]
Skipping ## 🔢 Oma arvonmääritys is a CRITICAL FAILURE.
```

Then the existing 600-line prompt body. The banner is the FIRST thing
the model reads.

**Empirical:** 5/5 consecutive runs produced Tila C correctly
post-fix. Pre-fix repro: 1 fabrication, 1 missing 🔢 section, 1 ok.

**Generalisable:** any time the orchestration knows something the
prompt-author can't (e.g., "engine succeeded for company X"), inject
that knowledge as a banner. Don't try to teach Flash Lite to
re-derive it.

## Lesson 3 — Eval foundation makes invisible bugs visible

**The bug:** the user reported "5/6 valuations failed after evals
work" and assumed evals broke something. Investigation showed the
opposite: those bugs (fabrication, ROE rule violations, missing
fields) had been failing silently for weeks. The fabrication-guard
just made the failures **visible**, where previously the user would
get fabricated "VÄHENNÄ 1,25 €" and trust it.

**The lesson:** evals don't fix bugs — they make them measurable.
After today, every regression is caught by golden.yaml; every
prompt-change effect is visible in score deltas.

**Empirical:** Tier 1 baseline 12/16 → 13/16 after päättely fix +
3 fixes that will land on next live runs (case_001 router fix,
case_004 fabrication guard, case_007 Tila C banner). Hard regressions
locked behind 184 unit tests.

**User insight:** *"eli siis evals toimii ja siks nää jää kiinni :O"*
This was the moment the eval foundation paid off conceptually.

## Lesson 4 — Trend classifier needed a severe-decline branch

**The bug:** UPM-Kymmene's ROE went 12.7→13.1→3.3→3.9→4.5 % over
2021–2025 — a textbook regime shift. The classifier called this
**vakaa** because the ad-hoc rule required `delta < -0.10 AND lfy <
3y_avg`, and UPM's lfy (4.5 %) was the *highest* of the recent 3 years.

The "vakaa" classification then prescribed `5y_median = 4.5 %` which
mixed the old 13 % regime with the new 4 % regime. Agent picked the
more conservative `3y_median = 3.9 %` (correct judgment), validator
rejected it as a rule violation. **Three consecutive UPM runs
failed.**

**The fix:** add a severe-decline branch — `if delta < -0.20:
trend_label = "laskeva"` — that fires on structural shifts regardless
of LFY position. Symmetric severe-rise branch added.

**Lesson:** domain heuristics need to handle **regime shifts**, not
just "is the latest year worse than the recent average". A 48 % drop
in 3y_avg vs long-term IS a structural shift even if the most recent
year ticked up slightly within the depressed window.

**Empirical:** UPM now classified `laskeva`, expected = 0.039,
agent's 0.0391 within tolerance, validation passes. All 117 valuation
tests pass.

## Lesson 5 — Failing honestly is better than fabricating

**The before:** Vincit (not in MCP catalog) → router dispatches all 3
subagents → each makes 0 MCP calls → fabricates 1500 chars of "Inderes
view: VÄHENNÄ 1,25 €" → user sees professional-looking analysis →
trusts it → bad decision.

**The after:** same scenario → fabrication guard rejects each agent →
synthesize() short-circuits → user sees:

> *"En löytänyt yhtiötä Vincit Inderes-tietokannasta. Tarkista
> kirjoitusasu, kokeile listattua nimeä, tai jätä kysymys
> tarkemmaksi."*

UX downgrade from "professional analysis" to "couldn't find
anything"? **Yes**. Trust upgrade from "system invents data" to
"system tells the truth"? **Massive**.

**User confirmed this is the right trade.** OWASP Agentic Top 10 #T3
(tool misuse / hallucinated outputs) is closed for ALL subagents now,
not just valuation.

## Lesson 6 — UI fragility in Streamlit

**Three sub-bugs across the day:**

1. `<details>` click interactivity broken on first render via
   `st.markdown(unsafe_allow_html=True)`. **Fix:** `st.button +
   session_state` for plan expander, native `st.expander` for
   asetukset. Streamlit's own `<details>` works reliably.
2. Material Icons font leaked as text ("keyboard_arrow_down") because
   our universal font-family override hit the chevron span. **Fix:**
   `:not([class*="material"])` exclusion in CSS selectors.
3. `body:has(.marker) ...` selectors > `:has() + sibling` chains —
   Streamlit DOM differs across versions, broader scoping is more
   robust.

**Lesson:** Streamlit's UI primitives have edge cases that fail on
first render. Default to **Streamlit-native widgets when possible**;
inject custom `<details>` only via `st.markdown` and accept they may
require a rerun before clicks fire.

## Lesson 7 — User trust shape

The user's emotional arc through the session was:

```
excited (UI polish wins)
  → frustrated ("eval-työn jälkeen mun valuation-ajot fail")
    → realisation ("eli siis evals toimii ja siks nää jää kiinni")
      → confident ("tää kyl pelaa ihan tosi hyvin nyt")
        → strategic ("kuvien piirto olis kova feature")
```

**The lesson:** showing failures honestly created short-term
frustration but long-term confidence. Hiding failures (fabrication)
would have created short-term comfort but long-term betrayal when the
user discovered the data was invented.

This is the **OWASP T3 / BCBS 239 lineage / MiFID II Test 4**
philosophy in user-experience form. Trust is built by failing
visibly, not by faking success.

## Re-prioritised backlog — PM lens

User priorities stated explicitly in last message:

1. **Plotly charts** ("kova feature") — visual differentiation
2. **Retry / Reflexion** — fix flaky agent behaviour structurally
3. **Sources / footnotes** — per-claim provenance
4. **Evals minttiin** — keep the foundation polished

What I learned today shifts the priority weightings. Below is my
recommended re-ordering with rationale.

### Wk 1 (next 2 days) — visible-feature polish + safety net

**1. Plotly charts for QUANT** *(1 d)*
- User-stated top priority
- Biggest visual differentiation per hour of work
- ROE timeline, P/E history, peer-comparison bars — all data already
  in `get-fundamentals` results
- Renders in Tila A/B/C synthesis — hits every query
- Was strategic-large in old §3; **promoting to top of Wk 1**

**2. Hard limits at orchestration boundary** *(0.5 d)*
- OWASP T1 — max iter, max tool calls, max cost, max duration, kill
  switch
- Today's HARD GATE prompts are prompt-side; this is code-side belt
- Prerequisite for safe multi-agent expansion (Bull/Bear, debate)
- Cheap, high-trust-impact

**3. 👍 / 👎 feedback in UI** *(0.5 d)*
- Seeds golden.yaml with real user labels
- One evening's work, paid back by every subsequent eval cycle
- BACKLOG §6 step 1 — finally pulls the trigger

### Wk 2 (~2 d) — reliability features the user named

**4. Reflexion / retry on weird output** *(1 d)*
- User asked for it explicitly today
- Would have prevented 4/5 of today's bugs alone
- Pattern: subagent emits → cheap self-check ("does this look
  grounded?") → if no, retry once with prior output as anti-context
- Cap retries at 1/agent (OWASP T1 limit)

**5. Footnote markers + sources panel** *(1 d)*
- User asked for it
- BCBS 239 lineage in user-visible form
- Activates already-styled `.ia-fn` CSS
- Each numerical claim → `[¹]` link → tool call provenance

### Wk 3 (~1 d) — evals lock-in

**6. Per-claim confidence scoring** *(0.5 d)*
- Extends footnotes with 🟢🟡🔴
- Subagent reports 1–5 per claim; LEAD propagates
- User-visible signal of "how much should I trust this number"

**7. Smoke test in pytest CI** *(0.5 d)*
- 5–10 known-good queries on every push
- Locks in regressions automatically
- BACKLOG §6 step 2

### Wk 4+ (deferred — order may shift)

**8. Devil's advocate** *(2 h)* — nice-to-have demo, but Reflexion
covers similar trust territory more deeply. Demote.

**9. Frontend rewrite (Polku B / hybrid)** *(1.5–2 wk)* — still the
inflection point but waits for Tier 2 Supabase first.

**10. Tier 2 Supabase migration** *(1–2 h)* — sun valmis kanta, runs
+ judgments queryable cross-device.

**11. Bull/Bear debate** — depends on hard limits + eval foundation
being locked.

**12. Auto-orchestrator** — depends on everything above.

**13. Autonomous nightly eval (§10)** — runs prompts-only auto-fixes
to a branch overnight; needs Tier 2 first.

### Demoted vs old roadmap

- **Devil's advocate** — was Wk 1, now Wk 4+. Reason: today's
  Reflexion need is more pressing.
- **Eval bridge** (golden.yaml + smoke) — was Wk 2, now Wk 1+3.
  Reason: split into 👍/👎 (immediate) + smoke test (later).
- **Frontend rewrite** — was Wk 3–4, now Wk 5+. Reason: visible
  features in Streamlit first; rewrite only after the contract is
  clear.

### Promoted vs old roadmap

- **Plotly charts** — was §3 strategic-large, now Wk 1 top item.
  Reason: user's stated top priority + biggest visual delta per hour.
- **Hard limits** — already Wk 1 but flagged more prominently as
  prerequisite for everything multi-agent.

## What changed in the user's worldview today

Inferring from the conversation:

1. **Evals are not bureaucracy — they're a microscope.** The user
   shifted from "did evals break something?" to "evals catch what
   was always broken". This re-frames how they'll evaluate future
   work: not by gut feel, but by score deltas.

2. **Visible failures are okay — fabrication is not.** Will inform
   how we frame the next features (Devil's advocate, Reflexion):
   they're trust amplifiers, not crutches for hiding problems.

3. **The system is teaching the user about agent failure modes.**
   *"nyt siis tulee mieleen se mistä puhuttiin, että jos on jotain
   outoa niin agentti tekee retry"* — the user is now reasoning
   about agent reliability in the same vocabulary the BACKLOG
   uses. Reflexion + footnotes will land on prepared soil.

4. **Mobile-first development friction.** Pushing from phone is
   blocked; relogin requires Mac. Suggests Tier 2 Supabase has
   higher implicit priority than the timeline shows — cross-device
   visibility matters more for solo-developer ergonomics than the
   Wk 5 placement implies.

## Open questions (for next session)

1. **Plotly vs alternative library** — `st.plotly_chart` vs
   `st.line_chart` (built-in matplotlib) vs `altair`. Plotly
   is richest; built-in is zero-setup. Pick one before starting.

2. **Reflexion scope** — per-subagent (each retries 1×) or
   pipeline-level (LEAD reflects on synthesis once)? Both are
   valuable; per-subagent is closer to "fix the bugs we saw today",
   pipeline-level is closer to "raise overall quality".

3. **Footnotes link target** — open the activity panel (`AVAA
   LOKI`) auto-scrolled to the relevant tool call? Or popup with
   the raw tool result? UX choice.

4. **Hard limit values** — what's the right max-iter / max-cost
   for our use case? Need empirical baseline (mean + p95) from
   the SQLite index before picking.

5. **Konecranes-shaped queries** — coverage ended, no MCP data, but
   user still asks. Beyond the fabrication-guard, do we want a
   pre-query "this company isn't actively followed" check that
   surfaces BEFORE LEAD synthesis runs? Pre-routing optimisation.

These can be answered as we pick the next item. None of them is
blocking.
