# Eval results — 20260509-201747

**Judge backend:** gemini-2.5-pro

**Hard assertions:** 12 pass / 4 fail across 6 evaluated cases (0 skipped).

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
- **factuality**: 5/5 — The numerical data in the comparison table for ROE and EBIT-% is directly supported by the `get-inderes-estimates` tool call.
- **hallucination**: 1/5 — The synthesis makes several claims about the companies' business models, but the `routing` artifact shows only the `quant` agent was called, meaning these qualitative claims are not grounded in any tool output.
- **structure**: 5/5 — The synthesis contains a clear, scannable markdown table that directly compares profitability metrics for both companies over time.
- **overall**: 2/5 — While the answer was well-structured and factually correct on the numbers, it failed the core task of grounding its qualitative business model analysis by not routing to the research agent, resulting in hallucinated reasoning.
- *flags:* hallucination_suspected=True, conflict_resolution_visible=True, warning_appropriate=True

### ❌ `case_002_paattely_schema`

**Query:** `tee arvonmääritys Sampolle`

**Matched runs:** 20260508-221547-968

**Hard:** 0/1 passed

- ✗ `paattely_kind == 'structured'`

**Soft (LLM-judge):**
- **reasoning_completeness**: 1/5 — The `Päättely` is a generic prose statement that does not mention the single conflict found by the `conflict_detector` or explain how it was resolved.
- **overall**: 1/5 — The run failed the case's primary objective by producing a generic prose `Päättely` instead of a structured one, and it completely ignored the conflict identified by the conflict detector.
- *flags:* hallucination_suspected=False, conflict_resolution_visible=False, warning_appropriate=False

### ✅ `case_003_conflict_coverage`

**Query:** `Bittiumille`

**Matched runs:** 20260509-094219-578

**Hard:** 2/2 passed

- ✓ `conflicts_count >= 1 or isolated_count >= 1`
- ✓ `has_warning_phrase == True`

**Soft (LLM-judge):**
- **conflict_resolution**: 1/5 — The `päättely` prose makes a generic statement about combining agent outputs but fails to mention the specific conflict that the `conflict_detector` identified (`conflicts_count`: 1), nor does it explain why one agent's value was chosen over another.
- **overall**: 1/5 — The run failed the case's primary objective, as the LEAD agent completely ignored the conflict identified by the conflict detector in its reasoning.
- *flags:* hallucination_suspected=False, conflict_resolution_visible=False, warning_appropriate=True

### ❌ `case_004_search_robustness`

**Query:** `Vincit`

**Matched runs:** 20260502-205706-108

**Hard:** 1/2 passed

- ✓ `duration_s < 90`
- ✗ `subagent_errors > 0 or 'ei löyty' in (synthesis or '').lower() or 'not found' in (synthesis or '').lower()`

**Soft (LLM-judge):**
- **graceful_failure**: 1/5 — The synthesis fabricates numerous specific data points (e.g., "tavoitehinta 1,25 €", "Q1'26 EBITA-marginaali 1,8 %") despite the `tool_calls` artifact being empty, indicating a complete failure to retrieve any real data.
- **overall**: 1/5 — The system completely failed the test case by hallucinating a detailed financial report for a company it could not find, as evidenced by the empty `tool_calls` list.
- *flags:* hallucination_suspected=True, conflict_resolution_visible=False, warning_appropriate=False

### ✅ `case_005_reproducibility`

**Query:** `tee arvonmääritys Nordealle`

**Matched runs:** 20260509-122319-629, 20260509-120700-205, 20260509-120433-948

**Hard:** 3/3 passed

- ✓ `all(r.routing.domains == runs[0].routing.domains for r in runs)`
- ✓ `all(r.has_synthesis for r in runs)`
- ✓ `max(r.duration_s for r in runs) < 2 * median(r.duration_s for r in runs)`

**Soft (LLM-judge):**
- **reproducibility**: 5/5 — While only one run was provided for a multi-run comparison, the synthesis presents a clear, internally consistent valuation structure with an explicit target price of 16.50 € and a model-implied value near 14.85 €, making it a strong candidate for reproducibility.
- **overall**: 5/5 — The agent produced a well-structured and nuanced valuation, correctly identifying and transparently resolving conflicts between historical data and analyst forecasts as noted in the päättely.
- *flags:* hallucination_suspected=False, conflict_resolution_visible=True, warning_appropriate=False

### ✅ `case_006_latency_cap`

**Query:** `selitä mistä Nordean kannattavuus oikeasti tulee`

**Matched runs:** 20260509-094050-902

**Hard:** 2/2 passed

- ✓ `duration_s < 120`
- ✓ `max(tc_count_per_agent.values(), default=0) <= 12`

**Soft (LLM-judge):**
- **depth_quality**: 5/5 — The synthesis provides a detailed breakdown of specific profitability drivers like net interest income, operational efficiency from IT, and credit loss provisions, directly addressing the query beyond generic points.
- **overall**: 3/5 — The answer correctly identifies and explains specific profitability drivers, but the synthesis contains multiple hallucinated dates (2026), which is a major factual error that undermines the response's credibility.
- *flags:* hallucination_suspected=True, conflict_resolution_visible=False, warning_appropriate=False
