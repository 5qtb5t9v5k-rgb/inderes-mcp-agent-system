# Design brief — Inderes Agent Desk

> A working draft to take into a design conversation (e.g. Claude Design).
> Captures the **product mental model**, **current UI strengths and
> pain points**, **inspirations** from peer AI surfaces (ChatGPT, Claude,
> Grok), and the **open design questions** that need a designer's
> judgment rather than an engineer's.

---

## 0. What this app is (one paragraph)

A multi-agent stock-research conversation. The user types a natural-language
question about Nordic equities (mostly Helsinki / OMXH). A *router* classifies
the query, a *fan-out workflow* spawns 1–10 specialized subagents in parallel
(QUANT for numbers, RESEARCH for analyst notes, SENTIMENT for forum + insider
trades, PORTFOLIO for the model portfolio), each subagent calls Inderes' MCP
tool API, a *conflict-detector* compares their outputs, and a *LEAD* agent
synthesizes the final answer with sources. Everything runs through Microsoft
Agent Framework on top of Gemini Flash. The whole point is to feel like a
team of specialists answering — not a single chatbot.

The audience is one technical person (the builder) plus invited testers; not
a public product. UI is mostly Finnish, occasionally English.

---

## 1. Current screen, top-to-bottom

(Streamlit, single page, rendered today on the cloud deploy.)

| Section | What it does | Strength | Pain point |
|---|---|---|---|
| **Sidebar — disclaimer** | Red text "Ei Inderes Oyj:n tuottama…" | Sets expectations. | Eats real estate every screen, stays static. |
| **Sidebar — architecture brief** | "LEAD reitittää kysymyksen 1–4 subagentille…" | Educates first-time visitors. | Identical text every visit. |
| **Sidebar — agent roster** | ◆ LEAD / ▲ QUANT / ■ RESEARCH / ● SENTIMENT / ✦ PORTFOLIO with one-line role. | Persona system feels intentional. | No state — doesn't show *which* of these were invoked in the last query. |
| **Sidebar — conversation** | Past chat turns. | Standard. | Cramped. |
| **Sidebar — viimeisimmät ajot** | Last 8 run IDs with truncated query. | Useful for debugging. | "20260507-113828 — …" is engineer-speak; not a usable history view. |
| **Top banner** | "INDERES//AGENT DESK" + "VERKOSSA" status pill | Brand. | Feels stuck-on; doesn't move with the conversation. |
| **Headline strip** | "MULTI-AGENT RESEARCH — INDERES + MCP + AGENTIT = INSIGHTS" + agent glyph row | Marketing. | Repeats sidebar info. |
| **Input box** | Standard chat input at bottom | Standard. | — |
| **Live status during run** | "🧭 Reititän kysymyksen oikeille agenteille…" → "✓ Päädyin: ▲ QUANT — kohde: Nordea, Sampo" → "▲ QUANT käynnistyy → etsii tunnuslukuja…" → "▲ QUANT · Nordea ✓ valmis" → "◆ LEAD yhdistää tulokset synteesiksi…" | The dynamic updating *is* the personality of this product — it feels like a real ops desk. | Lines stack vertically and disappear when synthesis ends; user can't review what the agents *did* without scrolling old log. |
| **💭 Perustelut: callout** | One-paragraph meta reasoning at the start of LEAD's answer. Amber-bordered. | Visually clear "this is meta, not the answer." | Sometimes repeats the answer body. |
| **🧠 Päättely block** | Prompt asks LEAD to emit `<details><summary>` HTML. **Currently fails**: Flash Lite emits the heading text but not the HTML tags, so it bleeds into the answer body as a flat paragraph. | Intent: collapsed-by-default reasoning trace. | Format compliance is the biggest open problem — see §5. |
| **Answer body** | Markdown — paragraphs, tables, lists. | Tables render well. Code blocks styled. | Long answers (Puuilo deluxe) become a wall of text. |
| **📖 Lähteet** | Bullet list of links to Inderes.fi. | Clickable, opens new tab. | Feels like a footnote bin; no relationship to where in the answer the sources were used. |
| **💡 Voisit kysyä myös** | Three follow-up question chips. | Click → submits as new query. | Sometimes these are obvious or repetitive. |
| **🔍 Agenttien toimintaloki** (expander, closed by default) | Routing card · per-run metrics (Duration / Subagents / Errors / Fallbacks) · per-stage timing line · for each subagent: persona row + free-text output + 🔧 Työkalukutsut nested expander showing tool name + args + N items returned + first 20 entity names | This is *the* feature that makes the system trustworthy — every claim is traceable to the tool call that produced it. | Everything is in **one** mega-expander. Inside, info-density goes from low (4 metric cards) to extremely high (10 subagents × 4 tool calls each = 40 nested entries). Hard to skim. |

### Three things the current UI does *right* that any redesign should preserve

1. **Persona color system** is consistent across status bar, log rows, agent
   chips. ◆ amber, ▲ slate-blue, ■ olive, ● teal, ✦ violet (or
   thereabouts). Disambiguates fan-out rows immediately.
2. **Live status during execution** turns a 30-second wait into theatre.
   This is the product's signature — do not flatten into a spinner.
3. **Sources are real links to inderes.fi** with their own published-date
   suffix. The whole project is built on the credibility of citing real
   Inderes content — the link rendering must stay.

---

## 2. Reference experiences worth borrowing from

### ChatGPT / OpenAI
- **Inline reasoning panel** ("Reasoned for 12s", expandable) is closer to
  what `🧠 Päättely` is trying to be. Collapsed by default, summarizes
  the work, expands to a step-by-step trace.
- **Tool-call surfacing**: when the model calls a tool, ChatGPT shows a
  compact card mid-stream ("Called `web_search`"), expandable to args +
  result preview. Closer to our `🔧 Työkalukutsut` but rendered inline
  with the answer rather than buried in a log.
- **Source citations as inline footnote markers** [1][2] rather than a
  bin at the bottom. Each marker links to the source preview on hover.
- **Streaming text** with typing animation for the synthesis answer.

### Claude (claude.ai)
- **Thinking block** styling is best-in-class: minimal chrome, italic
  typography, gentle border, "expand" affordance is subtle. We should
  emulate this for `🧠 Päättely`.
- **Artifacts panel** — a side-panel that opens when the answer contains
  structured output (table, chart, code). Could replace our 🔍
  toimintaloki (which is currently inline-expanded). Imagine: the answer
  stays on the left, the agent activity log opens on the right as a
  sticky panel.
- **Excellent code-block rendering** with copy button.
- **No persona/glyph language** — Claude is one entity. Our system is
  *deliberately* a team. We diverge here.

### Grok
- **DeepSearch live trace**: the streaming "I'm reading X, now Y, now Z"
  format is closer to our existing live-status approach. Validates that
  this style works.
- **Sources surfaced inline as small chips** mid-stream — clickable,
  hover-preview.
- **Loose, conversational tone** in the UI chrome (status messages have
  personality). Our Finnish status messages already have a hint of this
  ("käynnistyy → etsii tunnuslukuja"); could lean further.

### What none of them do (yet) that we could
- Show **per-agent attribution** for every claim. ChatGPT and Claude have
  one model; we have five personas. We can color-code claims in the
  synthesis by which subagent contributed them. This would be a real
  differentiator and ties to the conflict-detector data we already
  collect.

---

## 3. Proposed user mental model

What we want the user to feel, in order, on a 30-second multi-domain query:

1. **"My team is on it."** As soon as I press Enter, I see the router
   pick agents, see them light up by persona color, see them work in
   parallel. This is the moment the multi-agent metaphor pays off.
2. **"Here's the answer."** When synthesis lands, the answer is
   clean — a clear opinion + supporting data. No log clutter.
3. **"Show me how."** If I'm curious, I can peel layers: hover a claim
   to see which subagent said it, expand 🧠 Päättely to see how
   conflicts were resolved, open the activity panel to see every tool
   call and what it returned.
4. **"This was 23.4s. Most of it was the QUANT branch waiting for
   `get-inderes-estimates`."** Performance breakdown is a click away,
   not in my face.

The current UI does (1) reasonably, (2) well, (3) only via one mega-expander
that mixes layers, (4) only by reading a single mid-page line. The
redesign should keep the answer dominant and make peeling layers feel
natural and progressive — not "click expander and now you have 40
nested expanders."

---

## 4. Things the engineering layer already provides — design can rely on this

The provenance pipeline (BACKLOG #10, shipped today) means every run
captures, per subagent, in `~/.inderes_agent/runs/<ts>/subagent-NN.json`:

```json
{
  "domain": "quant", "company": "Sampo",
  "model_used": "gemini-3.1-flash-lite-preview",
  "duration_seconds": 6.4,
  "text": "Ajatus: Haen Sammon ja Nordean… [full agent narrative]",
  "tool_calls": [
    {
      "name": "search-companies", "arguments": {"query": "Sampo"},
      "item_count": 1, "item_names": ["Sampo"],
      "result_text": "{...full JSON...}"
    },
    {
      "name": "get-inderes-estimates",
      "arguments": {"companyIds": ["COMPANY:258", "COMPANY:382"], "fields": ["pe", "dividendYield"]},
      "item_count": 2, "item_names": ["Nordea Bank", "Sampo"],
      "result_text": "{...full JSON with estimates...}"
    }
  ]
}
```

And `meta.json`:

```json
{
  "lead_model": "gemini-3.1-flash-lite-preview",
  "duration_seconds": 24.3,
  "stage_timings": {
    "fanout_seconds": 15.15,
    "conflict_detector_seconds": 2.42,
    "lead_seconds": 5.47,
    "per_subagent": [{"index": 1, "domain": "quant", "company": "Nordea", "duration_seconds": 6.4}, …]
  },
  "subagent_count": 4,
  "fallback_events": 0
}
```

And `conflicts.json`:
```json
{
  "model_used": "...",
  "duration_seconds": 2.42,
  "parsed": {
    "agreements": [{"claim": "...", "supported_by": ["quant — Sampo", "research — Sampo"]}],
    "conflicts": [{"topic": "...", "positions": [{...}, {...}]}],
    "isolated_claims": [{"claim": "...", "supported_by": ["sentiment — Kesko"], "risk": "..."}]
  }
}
```

So the design has access to: (a) full per-agent text, (b) full tool call
arguments and results, (c) entity names extracted from each tool call,
(d) per-stage timings, (e) structural conflict / agreement / isolated-claim
map. **No new data needs to be collected** — design can choose how to
*surface* it.

---

## 5. The biggest open design question

**What should `🧠 Päättely` look like, and how should it interact with
the answer body?**

The intent: make the LEAD's reasoning trace inspectable without
cluttering the answer. Today the prompt asks for an HTML
`<details>` block with four bullets (what subagents disagreed on / how
I resolved it / what's uncertain / what I didn't check). Gemini Flash
Lite ignores the literal HTML format and writes a free-form prose
paragraph instead.

Three options:

- **A — Accept the prose.** Style it as an italic indented quote-block,
  collapsed by an "Avaa päättely" link. Simple, but format compliance
  remains brittle (the prose isn't structured).
- **B — Build the structure on the engineering side.** Don't ask the
  model to emit HTML; have the model emit JSON and the *UI* renders
  the four bullets. This is more reliable and more designable. Adds
  one more model output to parse, but we already do this for the
  conflict detector.
- **C — Switch LEAD to a smarter model** (Claude Sonnet, GPT-4o-thinking)
  that follows literal-format instructions. ~40× cost per query but
  cents/day at this scale. Would also unlock proper "thinking" output
  similar to Claude.ai.

The design conversation should weigh: how much does the *visual* affordance
matter (designer's call) vs. the *content quality* of the reasoning
(my call). My instinct: B is the most defensible — define the slot
shape in JSON, render UI side, model just fills the slots. But there
are visual options worth a designer's eye.

---

## 6. Other open design questions (smaller, but real)

1. **Activity log: side panel vs. inline expander?** Right now it's an
   inline expander. Claude.ai's artifact-side-panel pattern would let
   the answer stay clean while the panel becomes a persistent
   companion. But it doubles the screen real-estate cost.
2. **Per-claim provenance markers.** Should each load-bearing claim in
   the synthesis ("Inderes-suositus on INCREASE, target 10€") carry a
   tiny marker showing which subagent + which tool call it came from?
   Inline footnote `[¹]` style, or a colored dot per persona, or hover-only?
3. **Live-trace persistence.** During a run, the live status updates
   feel alive. After synthesis ends, those messages disappear. Should
   they remain as a collapsed timeline, accessible later via a "📊
   Aikajana" affordance?
4. **Conflict surfacing in the answer.** Currently the conflict-detector
   produces structured JSON, but the user only sees the *resolution*
   (woven into 💭 Perustelut) — not the raw conflicts. Should
   genuine disagreements between subagents be surfaced as a 🔀
   callout in the answer ("QUANT ja RESEARCH eivät olleet samaa
   mieltä Sammon ROE:sta — luotin tuoreempaan dataan…")?
5. **Persona consistency.** Should the agent glyph row at the top fade
   *out* the personas that weren't invoked in the last query?
6. **Mobile.** Streamlit's mobile rendering is acceptable but not
   delightful. The 🔍 toimintaloki nested expanders especially struggle.
   Worth thinking about a separate "compact" mode.
7. **"Recent runs" sidebar.** Right now: `20260507-113828 — "Analysoi…"`
   List. Could become a search-style interface with persona icons
   indicating which agents were used, durations, recommendation badges.
8. **Brand identity.** "INDERES//AGENT DESK" feels like a working
   title. Naming, type system, color refinement: room for a real pass.

---

## 7. Constraints

- **Streamlit.** Current implementation. Means: native components only;
  custom React would be a separate project. Streamlit supports `st.html`,
  `st.markdown(unsafe_allow_html=True)`, and CSS injection — so most
  visual pixel-pushing IS possible, just within Streamlit's component
  model. Some interactions (drag-resize panels, anything truly stateful
  client-side) require workarounds or `streamlit.components.v1`
  custom components.
- **Finnish-first.** Most queries and most UI text are in Finnish.
  English is supported but secondary. Typography decisions should not
  break Finnish ä/ö/å.
- **Streamlit Cloud deploy.** No build step beyond `requirements.txt`
  and a `git push`. Custom React / TypeScript would change the deploy
  model.
- **Single tester audience.** No need to optimize for "first-time
  visitor onboarding" beyond the existing demo card. Power-user
  experience matters more.
- **Inderes brand respect.** The disclaimer at the top is mandatory —
  this app is *not* affiliated with Inderes. The visual language should
  not lean *too* Inderes-y; should feel like a research desk that
  uses Inderes data, not an Inderes product.

---

## 8. What I'd love a designer to deliver

1. **A small set of high-fidelity screen variations** for the main
   query → answer flow:
   - Empty state (before any query)
   - Mid-run (live status visible)
   - Result state (clean answer dominant)
   - Result state with activity panel expanded
   - Mobile equivalent of the result state
2. **A typography + color system spec** that's distinct from
   Streamlit defaults but achievable within Streamlit's CSS injection.
3. **A reasoned answer to §5** — what is the right shape for
   `🧠 Päättely` given that the engineering side will produce
   structured JSON if needed.
4. **A persona system refresh** — keep the five glyphs but with
   sharper visual identity per role.
5. **Optional: an opinion on whether the activity log belongs as a
   side-panel** (Claude.ai-style) **or stays as an inline expander.**

---

## Appendix A — Files

| Path | Role |
|---|---|
| `ui/app.py` | Main Streamlit entrypoint, page layout, chat loop, live-status code |
| `ui/components.py` | Renders agent rows, lead answer (with markdown→HTML), follow-up chips, recommendation badge, sidebar panels, persona system |
| `ui/theme.py` (if exists) / inlined | CSS injection, color tokens |

## Appendix B — Personas (current)

| Glyph | Domain | Role | Color (current) |
|---|---|---|---|
| ◆ | LEAD | Päätoimittaja | amber |
| ▲ | QUANT | Numerot | slate / steel-blue |
| ■ | RESEARCH | Analyytikko | olive / dark green |
| ● | SENTIMENT | Tunnelmat | teal |
| ✦ | PORTFOLIO | Mallisalkku | violet |

## Appendix C — Sample full live-status sequence

```
🧭 Reititän kysymyksen oikeille agenteille…
✓ Päädyin: ▲ QUANT — kohde: Nordea, Sampo
⚙️ Subagentit käynnistyvät rinnakkain…
▲ QUANT käynnistyy → etsii tunnuslukuja ja laskee Pythonissa
▲ QUANT · Nordea ✓ valmis (gemini-3.1-flash-lite-preview)
▲ QUANT · Sampo ✓ valmis (gemini-3.1-flash-lite-preview)
◆ LEAD yhdistää tulokset synteesiksi…
```

---

*Document version: 2026-05-07 · v1, ready for first design review.*
