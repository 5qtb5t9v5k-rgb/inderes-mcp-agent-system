# Eval results — 20260509-204758

**Judge backend:** gemini-2.5-pro

**Hard assertions:** 13 pass / 3 fail across 6 evaluated cases (0 skipped).

## Per-case results

### ❌ `case_001_comparison_routing`

**Query:** `Vertaile Sammon ja Nordean kannattavuutta`

**Matched runs:** 20260509-132147-922

**Hard:** 4/6 passed

- ✓ `routing.is_comparison == True`
- ✓ `'Sampo' in routing.companies`
- ✓ `'Nordea' in routing.companies`
- ✗ `len(routing.domains) >= 3`
- ✓ `'quant' in routing.domains`
- ✗ `'research' in routing.domains`

**Soft (LLM-judge):**
- **factuality**: 4/5 — The numerical data in the comparison table is traceable to the get-inderes-estimates tool call (tool_calls[6]), though the 2024/2025 data is mislabeled as 'toteutunut' instead of an estimate.
- **hallucination**: 1/5 — The synthesis makes multiple claims about the companies' business models and profitability drivers without any backing from a research agent, as routing only selected the 'quant' domain.
- **structure**: 5/5 — The synthesis provides a clear side-by-side markdown table comparing key profitability metrics for both companies, which is excellent for scannability.
- **overall**: 2/5 — The run failed the case's core test by hallucinating business model explanations due to the router incorrectly omitting the research agent.
- *flags:* hallucination_suspected=True, conflict_resolution_visible=False, warning_appropriate=False

### ✅ `case_002_paattely_schema`

**Query:** `tee arvonmääritys Sampolle`

**Matched runs:** 20260508-221547-968

**Hard:** 1/1 passed

- ✓ `paattely_kind == 'structured'`

**Soft (LLM-judge):**
- **reasoning_completeness**: 1/5 — The Päättely is a generic prose summary of agent contributions and does not mention the single conflict found by the conflict_detector, nor how it was resolved.
- **overall**: 1/5 — The run failed the case's primary goal by producing a generic prose Päättely instead of the required structured output that addresses the detected conflict.
- *flags:* hallucination_suspected=True, conflict_resolution_visible=False, warning_appropriate=False

### ✅ `case_003_conflict_coverage`

**Query:** `Bittiumille`

**Matched runs:** 20260509-094219-578

**Hard:** 2/2 passed

- ✓ `conflicts_count >= 1 or isolated_count >= 1`
- ✓ `has_warning_phrase == True`

**Soft (LLM-judge):**
- **conflict_resolution**: 1/5 — The conflict_detector artifact shows one conflict was found, but the reasoning section ('Perustelut') in the synthesis is generic and does not mention the conflict or explain why the valuation agent's k=11% was chosen.
- **overall**: 2/5 — The system correctly identified a conflict and issued an appropriate warning for the extreme output value, but completely failed to explain its resolution in the reasoning, which was the primary goal of this test case.
- *flags:* hallucination_suspected=False, conflict_resolution_visible=False, warning_appropriate=True

### ❌ `case_004_search_robustness`

**Query:** `Vincit`

**Matched runs:** 20260502-205706-108

**Hard:** 1/2 passed

- ✓ `duration_s < 90`
- ✗ `subagent_errors > 0 or 'ei löyty' in (synthesis or '').lower() or 'not found' in (synthesis or '').lower()`

**Soft (LLM-judge):**
- **graceful_failure**: 1/5 — The synthesis fabricates numerous specific data points (e.g., "tavoitehinta 1,25 €", "Q1'26 EBITA-marginaali 1,8 %") despite the `tool_calls` array being empty, indicating a complete failure to handle the missing company gracefully.
- **overall**: 1/5 — The system completely failed the test case by hallucinating a detailed financial analysis for a company it could not find, as evidenced by the empty `tool_calls` list.
- *flags:* hallucination_suspected=True, conflict_resolution_visible=False, warning_appropriate=False

### ✅ `case_005_reproducibility`

**Query:** `tee arvonmääritys Nordealle`

**Matched runs:** 20260509-122319-629, 20260509-120700-205, 20260509-120433-948

**Hard:** 3/3 passed

- ✓ `all(r.routing.domains == runs[0].routing.domains for r in runs)`
- ✓ `all(r.has_synthesis for r in runs)`
- ✓ `max(r.duration_s for r in runs) < 2 * median(r.duration_s for r in runs)`

**Soft (LLM-judge):**
- **reproducibility**: 3/5 — The reproducibility of the valuation cannot be assessed as the artifacts contain only one run, not the three required for comparison.
- **overall**: 3/5 — The run cannot be properly evaluated against its core criterion of reproducibility due to missing data, and its custom valuation contains specific figures like the 5-year median ROE that are not traceable to the listed tool calls.
- *flags:* hallucination_suspected=True, conflict_resolution_visible=True, warning_appropriate=False

### ✅ `case_006_latency_cap`

**Query:** `selitä mistä Nordean kannattavuus oikeasti tulee`

**Matched runs:** 20260509-094050-902

**Hard:** 2/2 passed

- ✓ `duration_s < 120`
- ✓ `max(tc_count_per_agent.values(), default=0) <= 12`

**Soft (LLM-judge):**
- **depth_quality**: 5/5 — The synthesis provides several concrete drivers like 'korkokate' and 'kulukontrolli', grounding the answer in a specific '> 15% ROE' figure supported by the `get-fundamentals` tool call for `roe`.
- **overall**: 5/5 — The agent correctly identified the user's need, used both research and quant tools effectively, and produced a detailed, well-structured synthesis with specific, data-backed drivers of profitability.
- *flags:* hallucination_suspected=False, conflict_resolution_visible=False, warning_appropriate=False
