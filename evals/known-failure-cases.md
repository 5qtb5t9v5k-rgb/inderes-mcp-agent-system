# Known failure cases

A growing list of concrete observed failure cases on real queries. Each
case documents the query, the expected behavior, the actual behavior,
and the inferred root cause. Used as:

- **Source material** for the golden eval dataset (each case → one
  golden run with expected output)
- **Regression check** when changing prompts or models — replay each
  case, verify the failure mode no longer reproduces
- **Argument for prioritizing** specific BACKLOG items — each case
  links to the BACKLOG features that would fix it

This file is curated by hand; it's not a complete record of every
failure (that's in `~/.inderes_agent/runs/<ts>/`). It's the cases
worth treating as evals.

---

## Case 001 — Calendar today, fabricated companies

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

## Case 002 — Calendar tomorrow, partial Nordic instead of Finnish

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
  source_case: known-failure-cases.md#case-001
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
