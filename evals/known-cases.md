# Known cases

A growing list of concrete observed cases on real queries. Each case
documents the query, the expected behavior, the actual behavior, and
the inferred root cause. **Both failures and successes are
documented** — successes that reveal *how* the system works are as
valuable as failures that reveal *why* it doesn't. Used as:

- **Source material** for the golden eval dataset (each case → one
  golden run with expected output)
- **Regression check** when changing prompts or models — replay each
  case, verify the behavior is preserved (failures stay fixed,
  successes stay passing)
- **Argument for prioritizing** specific BACKLOG items — each case
  links to the BACKLOG features that would fix or strengthen it

This file is curated by hand; it's not a complete record of every
run (that's in `~/.inderes_agent/runs/<ts>/`). It's the cases worth
treating as evals.

Each case is labeled with one of:

- 🔴 **Failure** — system produced a wrong/misleading answer
- 🟢 **Success worth understanding** — system worked, and *how* it
  worked is informative beyond the surface result
- 🟡 **Partial / mixed** — some right, some wrong

---

## 🔴 Case 001 — Calendar today, fabricated companies

**Date observed:** 2026-05-05
**Query:** *"kellä tänään tulosjulkistus?"*
**Region implied:** Finland (Finnish-language query)

### Expected output

The 6 events `list-calendar-events(dateFrom=2026-05-05, dateTo=2026-05-05,
regions=[FINLAND])` returned, in order:

- GRK Infra (INTERIM_REPORT)
- Remedy Entertainment (BUSINESS_REVIEW)
- Kalmar (INTERIM_REPORT)
- NoHo Partners (INTERIM_REPORT)
- KH Group (INTERIM_REPORT)
- KH Group (GENERAL_MEETING)

### Actual output

Listed 6 different companies, all marked INTERIM_REPORT:

- Componenta
- Etteplan
- F-Secure
- Kemira
- Qt Group
- Tietoevry

**None of these companies appear in the MCP tool result for that date.**
All 6 are real Finnish tech companies that have historically reported
Q1 results around early May; the model appears to have generated from
training memory rather than from tool output.

### Trace metadata

- Subagents: 1 (SENTIMENT)
- Errors: 0
- Fallbacks: 0
- Subagent's `**Ajatus:**` line claimed it called `list-calendar-events`
  with `dateFrom=dateTo=2026-05-05` and types filter `[INTERIM_REPORT,
  BUSINESS_REVIEW]`. Tool was called, result returned, ignored.

### Root cause

**Pure hallucination.** Tool was called, returned valid data, model
ignored result and generated answer from training memory. The trace
metadata claims tool success but the synthesis doesn't reflect it.

This is the most dangerous failure mode the system has had:

- Hallucinated names look plausible (real Finnish companies, plausible
  reporting dates)
- User cannot easily detect the failure without external verification
- Calendar events are exactly the kind of detail a user would act on
  (block calendar time, set a watch, prepare questions)

### What would fix this

| Fix | Type | Status |
|---|---|---|
| Tool-result entity validation post-processor | Code | Not yet built (proposed BACKLOG item) |
| BACKLOG #2 Reflektio + retry with red flags | Code | In BACKLOG, not built |
| Per-claim source provenance (forced citations) | Code + prompt | In BACKLOG nice-to-have |
| Stronger synthesis model (Pro vs Flash Lite) | Infrastructure | Parked branch |

Prompt-only fix attempted (added "cite tool result, not training memory"
rule under sentiment.md `## Rules`) — insufficient on its own; see
case 002 for the next failure mode that emerged.

---

## 🔴 Case 002 — Calendar tomorrow, partial Nordic instead of Finnish

**Date observed:** 2026-05-05 (asking about 2026-05-06)
**Query:** *"kellä huomenna osarit?"*
**Region implied:** Finland (Finnish-language query, plain "osarit")

### Expected output

The 13 Finnish events `list-calendar-events(dateFrom=2026-05-06,
dateTo=2026-05-06, regions=[FINLAND])` returned:

- Anora Group, CapMan, Optomed, HKFoods, Sampo (INTERIM_REPORT)
- Kempower (GENERAL_MEETING)
- Exel Composites, Talenom (BUSINESS_REVIEW)
- Toivo Group, Luotea, Lassila & Tikanoja, Lumo Kodit, Sitowise Group
  (INTERIM_REPORT)

### Actual output

Listed 12 companies, mixing Finnish + Nordic:

- Anora Group ✓ (correct)
- Wilh. Wilhelmsen Holding ✗ (Norway)
- Avensia ✗ (Sweden)
- CapMan ✓
- Optomed ✓
- Attendo ✗ (Sweden)
- Nolato ✗ (Sweden)
- Arion Bank ✗ (Iceland)
- Jyske Bank ✗ (Denmark)
- HKFoods ✓
- SHT Smart High-Tech ✗ (Sweden)
- AL Sydbank ✗ (Denmark)

4 of 12 from Finland; 8 from other Nordic countries. **Missed 9 of the
13 Finnish events** (Sampo, Kempower, Exel Composites, Talenom, Toivo,
Luotea, Lassila & Tikanoja, Lumo Kodit, Sitowise).

### Trace metadata

- Subagents: 1 (SENTIMENT)
- Errors: 0, Fallbacks: 0
- `**Ajatus:**` line: *"Etsin huomiselle 2026-05-06 ajoittuvia
  osavuosikatsauksia (INTERIM_REPORT) list-calendar-events-työkalulla."*

### Root cause

**Different from case 001.** When verifying via direct MCP call:
`list-calendar-events(dateFrom=2026-05-06, dateTo=2026-05-06)` *without*
region filter returns ~92 Nordic-wide events. **All 8 "fabricated"
companies in the agent's output are present in this unfiltered result.**

So the model:

1. Called the tool **without `regions=[FINLAND]` filter** despite the
   query being in Finnish (failure: tool-arg selection)
2. Got 92 events covering all Nordic exchanges
3. Cherry-picked 12 of those 92 — no obvious filtering logic, just
   apparently first-N or alphabetical-ish (failure: faithful
   summarization)
4. **Did not tell the user** that 80 events were omitted (failure:
   honesty about partial output)

This is *not* training-memory hallucination — the model used the tool
result. It used it wrong: incomplete and unfiltered presentation of a
larger result set.

### What would fix this

| Fix | Type | Status |
|---|---|---|
| Default-region inference (Finnish query → FINLAND) | Prompt | Could add as quick patch |
| Result-completeness check (N vs M items) | Code | Not yet built (proposed BACKLOG item) |
| BACKLOG #2 Reflektio + retry | Code | In BACKLOG |
| Stronger model for synthesis (Pro) | Infrastructure | Parked |

### Notes

This case is interesting because the **prompt fix from case 001 didn't
help** (it addressed hallucination from memory, not partial-result
presentation). Each prompt patch addresses *one* failure pattern; the
model finds new ones. This is the canonical argument for code-level
post-processing rather than prompt-only fixes.

---

## 🟢 Case 003 — Multi-subagent fan-out filters a hallucination

**Date observed:** 2026-05-06
**Query:** *"Tee kattava ja ajantasainen analyysi Puuilosta toukokuun
2026 tilanteessa. Vertaa sitä samassa toimialassa toimiviin yhtiöihin
(esim. Tokmanni ja Kesko)..."*
**Routing decision:** `domains=[QUANT, RESEARCH, SENTIMENT, PORTFOLIO]`,
`is_comparison=true`, three companies (Puuilo, Tokmanni, Kesko) →
**10 subagents** running in parallel.

### What happened

One of the QUANT subagents (the one analyzing Tokmanni in the
context of the Puuilo question) produced a single sentence that was
factually wrong:

> *"Mallisalkku: Puuilo on ollut pitkään Inderesin mallisalkun
> vakionimi, mikä kertoo luottamuksesta yhtiön laatuun."*

This was a hallucination. Puuilo is **not** in Inderes' model
portfolio in May 2026.

The other subagents working on the same query handled it correctly:

- RESEARCH (Puuilo): *"Puuilo ei ole Inderesin mallisalkussa
  toukokuussa 2026."* ✓
- SENTIMENT (Puuilo): *"Inderesin mallisalkun tiedot ovat
  tarkistettavissa heidän virallisista lähteistään."* (neutral
  hedge)
- SENTIMENT (Tokmanni): *"MALLISALKUN ASEMA: Puuilo ei ole Inderesin
  mallisalkussa."* ✓
- SENTIMENT (Kesko): *"Puuilo ei tällä hetkellä ole Inderesin
  mallisalkun yhtiöiden listalla."* ✓
- PORTFOLIO: *"Mallisalkku-status: Puuilo ei ole Inderesin
  mallisalkun tämänhetkisessä sisällössä (tarkistettu 6.5.2026)."* ✓

So among the 10 subagent outputs, **4 explicitly correct, 1 explicit
hallucination, 5 didn't address it**.

LEAD's final synthesis stated:

> *"Mallisalkku: Puuilo ei ole toukokuussa 2026 Inderesin
> mallisalkussa."*

LEAD picked the correct claim despite one subagent contradicting it.

### Why this is interesting

This is the **first documented case** of the multi-agent system
correcting an internal contradiction emergently. There is no
explicit voting code, no consensus algorithm, no truth-check —
LEAD is just one Gemini Flash Lite call given all 10 subagent
outputs as text in its prompt. Yet it filtered the hallucination.

The mechanism is statistical, not logical:

1. **Repetition signals truth in training data.** When the LLM
   sees four sources agreeing and one disagreeing, training-data
   priors favor the consensus.
2. **Specificity wins.** PORTFOLIO's claim was tool-grounded
   ("tarkistettu 6.5.2026"); QUANT's hallucination was a vague
   narrative claim ("on ollut pitkään vakionimi").
3. **Role appropriateness.** Mallisalkku-claims are PORTFOLIO's
   domain; QUANT's prompt explicitly scopes it to numbers. The
   LLM picks up role mismatches as a credibility hint.
4. **Internal consistency during generation.** Once LEAD has
   committed to "ei mallisalkussa" early in the synthesis, it
   resists later contradiction because that would create
   text-level inconsistency.

### Why this is fragile

The 4-vs-1 ratio is a comfortable margin. The mechanism would not
be reliable at:

- 1-vs-1 (single-domain query, only two opinions)
- 2-vs-2 with equally specific claims
- All hallucinations of equal vagueness/confidence
- Cases where the user's query language hints favor the wrong claim

Case 002 is the cautionary counter-example: with only one subagent
on the question, there was no second opinion to contrast with, and
the wrong filter slipped through.

### Why we don't have a "reasoning trace"

The forensic logs (`~/.inderes_agent/runs/<ts>/`) contain:

- ✓ Each subagent's full output (`subagent-NN-*.json`)
- ✓ LEAD's final synthesis (`synthesis.txt`)
- ✗ **No record of how LEAD weighted the conflicting claims**

The implicit weighting happens inside the LLM forward pass — there
is no externalized reasoning. We see what LEAD received and what it
produced, but not how it chose. This is a fundamental property of
LLM-based synthesis, not a logging gap.

### What would make this stronger

| Fix | Effect |
|---|---|
| Mandatory conflict-trace in `lead.md` | LEAD must list disagreements + how it resolved them in the **💭 Perustelut:** callout. Makes implicit consensus explicit and loggable. |
| ✅ Pre-synthesis conflict detection (BACKLOG #1 plan-then-execute) — *implemented in commit 842fd92* | Separate LLM call before synthesis: parses subagent outputs, emits structured `conflicts.json` with `agreements / conflicts / isolated_claims`. Synthesis sees explicit conflict list. Empirically caught a real `sentiment` disagreement on the Joller insider trade in a 10-subagent Puuilo run; lead resolved it explicitly in the preamble. Statistical → structural shift. |
| Per-claim source provenance | Every synthesis claim cites which subagent(s) backed it. User can see "Mallisalkku: ei [PORTFOLIO, RESEARCH-1, SENTIMENT-2, SENTIMENT-3]". |
| Reflektio + retry (BACKLOG #2) | Code-level entity validation post-synthesis: did LEAD use any claim no subagent made? Did it ignore claims many subagents made? |

These are not "fix this case" — Case 003 is a success — but
"make the success mechanism reliable instead of statistical".

### Notes on the broader principle

Multi-subagent fan-out (rather than single-agent ReAct) gives
**redundancy as a free side-effect**. The system shown here uses
that redundancy as its only defense against hallucination. That is
both impressive (no extra code) and dangerous (statistical
guarantee, not algorithmic). For any non-trivial multi-agent
system, expect to either:

- Engineer the redundancy explicitly (per-claim citations,
  conflict traces, reflection)
- Or accept that the system fails on single-domain queries with
  no second opinion

Case 002 is the failure mode of accepting it; Case 003 is the
success mode when conditions cooperate.

---

## 🔴 Case 004 — Same-day calendar pair: hallucination + false-negative

**Date observed:** 2026-05-07 (post-conflict-detector deployment, on cloud)
**Two queries, same agent (sentiment), single-subagent fan-out, ~10 minutes apart.**

This is one entry covering two related observations because they're
the same family of failure (agent claim ≠ tool result) seen on the
same day, on the same MCP tool, by the same subagent. Together they
demonstrate why **single-subagent calendar queries are the persistent
weak spot** even after the conflict-detector landed.

### 4a — *"kenellä tänään tulosjulkistus?"* (hallucination)

**Tool truth (verified by direct MCP call):**

`list-calendar-events(dateFrom=2026-05-07, dateTo=2026-05-07, regions=[FINLAND])`
returned 18 Finnish events including: Stora Enso, Harvia, SRV Group,
Enersense International, Sanoma, Etteplan, Suominen, Eezy, Oma
Säästöpankki, Musti Group, Orthex, Raute, Elecster, Kesla, Investors
House, NoHo Partners.

**Agent output:**
> *"Tänään torstaina 7. toukokuuta 2026 pörssiyhtiöistä tuloksensa
> julkistaa Admicom. Muita päivän yhtiötapahtumia ovat Eforen ja
> Sievi Capitalin yhtiökokoukset."*

**Three claims, zero overlap with tool result.** Admicom, Efore, and
Sievi Capital are all real Finnish companies that historically
report around early May — perfect hallucination targets from
training-data priors. Same shape as Case 001.

### 4b — *"kuka maksaa tänään osingon?"* (false negative)

**Tool truth:**
`list-calendar-events(dateFrom=2026-05-07, dateTo=2026-05-07,
types=[ANNUAL_DIVIDEND, ..., TRIANNUAL_DIVIDEND], regions=[FINLAND])`
returned **one** event: NoHo Partners TRIANNUAL_DIVIDEND, dividend=0.07€/osake,
**`paymentDate=2026-05-15`**, calendar-event date `2026-05-07`.

**Agent output:**
> *"Tänään, torstaina 7. toukokuuta 2026, pörssissä ei ole yhtiöitä,
> joiden osingonmaksupäivä olisi kalenterin mukaan asetettu tälle
> päivälle."*

The agent silently applied an unstated `paymentDate == today` filter
and dropped the only result. The Inderes user-facing calendar shows
this entry under "Tänään 07.05." (the calendar-event date drives the
listing, not the paymentDate), so the user expected NoHo Partners to
appear. A faithful response would have been: *"Tänään ei makseta
osinkoa, mutta NoHo Partnersilla on triannual-osingon kalenterimerkintä
tänään — varsinainen maksupäivä on 15.5.2026 (0,07€/osake)."*

### Root cause (both 4a and 4b)

Same root: **agent's textual claim does not match tool's structured
return value**. Different mechanisms:

| Sub-case | Mechanism | Documented earlier as |
|---|---|---|
| 4a | hallucination from training memory | Case 001 |
| 4b | false negative via unstated post-filter | new variant |

### Why the conflict-detector did not help

Both queries routed only to `sentiment` (single domain, single subagent).
`detect_conflicts()` skips itself when `len(non_error_subagents) < 2`
(`skipped_reason: "only 1 non-error subagent; nothing to compare"`)
because there's nothing to compare across. Conflict detection is a
**multi-subagent redundancy mechanism**; it cannot catch
agent-vs-tool-result divergence because it doesn't see the tool
results, only the subagents' summarized outputs.

### What would catch this

The fix is exactly the BACKLOG **"Tool-result entity validation
post-processor"** (Tool-result-rehellisyys section). For each
subagent that hit a tool returning structured items
(`list-calendar-events`, `list-insider-transactions`,
`search-forum-topics`):

1. Extract entity names from the tool's structured response
   (`item.companyName` field)
2. Extract entity names from the subagent's text response (regex,
   keyword match against the structured set, or NER)
3. Diff:
   - **Names in agent's response but not in tool's response → 4a-style
     hallucination → flag → retry with explicit context** (*"the tool
     did not return Admicom; do not include companies the tool did
     not return"*)
   - **Names in tool's response but not in agent's response, when
     the user asked for a list → 4b-style false negative → flag →
     retry with explicit context** (*"you must include all 18
     companies the tool returned, or explicitly state which subset
     and why"*)

This is purely code-level (regex over tool response items, regex
over agent text), no LLM call needed. It is the natural successor to
the conflict-detector for the single-subagent case.

### Mapping to BACKLOG

| Status | Item |
|---|---|
| ⏳ Not yet implemented | **Tool-result entity validation post-processor** — Tool-result-rehellisyys section. *4a + 4b are direct evidence of why this is high-priority.* |
| ⏳ Not yet implemented | **Result-completeness check** — same section. *Specifically targets 4b's "list under-reporting" shape.* |
| ✅ Implemented (842fd92) | Pre-synthesis conflict detection. *Does not help here — single subagent.* |

### Notes on scope

Case 004 is observed **after** conflict detection landed, which makes
it a useful negative example: the conflict-detector solves a real
class of bugs (multi-subagent claim divergence, see Case 003) but
does not address the single-subagent class. The system is still
vulnerable to Case 001-style hallucination on any query that routes
to exactly one domain, and to 4b-style false negatives whenever a
subagent applies an unstated post-filter on tool data. Both are
evidence for treating the **tool-result entity validation** BACKLOG
item as the next priority after conflict detection.

---

## How to use this file

### When triaging a new failure

1. Add a new `## Case 0XX — short title` section with the same shape
2. Document expected vs actual with as much specificity as possible
3. Verify the tool-level truth by calling MCP directly (this is part
   of the diagnosis, not optional)
4. Classify root cause: hallucination, tool-arg, partial-summary,
   prompt-ignore, etc.
5. Map to BACKLOG fixes with status

### When promoting to golden eval

Each case here should eventually become a row in
`evals/golden.yaml` (or whatever golden dataset structure we settle
on):

```yaml
- id: calendar-today-finnish
  source_case: known-cases.md#case-001
  query: "kellä tänään tulosjulkistus?"
  expected_routing: { domains: [sentiment], region: FINLAND }
  expected_tools: [list-calendar-events]
  expected_entities_subset_of_tool_result: true
  expected_entity_count: equals_tool_result_count
  forbid_entities_not_in_tool_result: true
```

The exact eval format will be designed when the eval pipeline is
built. For now, the human-readable case docs are the source of truth.

---

*Document version: 2026-05-05 · v1*
