# Testing strategy

**Status:** Draft for Wk 2 implementation
**Date:** 2026-05-10
**Owner:** core
**Audience:** future you (3 months from now), and the AI pair that will write most of the tests

---

## 1. Why we need a strategy, not just more tests

Coverage today is 48 % (14/29 src modules) but **vino**: valuation,
charts, router, parser are well-covered (~3 000 LOC of tests against
~1 200 LOC of logic). Auth, agents, MCP client, and observability/narrate
have **zero tests** (~1 000 LOC of untested logic, all on critical paths).

This is the worst kind of coverage shape: it gives a false sense of
safety. CI would pass on a refactor that breaks OAuth in production —
because OAuth has no tests, the suite is silent. We saw this exact
failure mode this morning: `render_feedback_widget` ImportError landed
on main and ran for 4 hours before being noticed (separately: it
was actually a hot-reload cache issue, but the principle stands).

A strategy answers three questions:
1. What level of safety do we need on each part of the system?
2. What is the **cheapest** test that delivers that safety?
3. When do we accept that a part is intentionally untested?

**The goal is not 90 % coverage. The goal is "I can refactor without
fear" on the 5 areas that matter, and explicit acceptance of risk on
the rest.**

---

## 2. The pyramid we actually want

```
                   /\
                  /  \    Eval suite (Tier 1)
                 /    \   - golden.yaml, 6 cases
                /  ~10 \  - LLM judge (Pro)
               /========\ - quality drift detection
              /          \
             /  Integration\  Workflow integration
            /    ~30 tests  \  - end-to-end via fakes
           /                 \ - one per critical path
          /===================\
         /                     \  Unit tests
        /     ~120–150 tests    \ - parsers, validators,
       /                         \  estimators, formatters,
      /===========================\ pure logic
```

We currently have ~140 unit tests, ~3 integration tests (cost-tracker,
fallback, valuation tool guard) and 6 evals. The shape is roughly
right; what's missing is **coverage of the right modules**, not more
tests of valuation engine.

---

## 3. Module-by-module risk classification

This is the load-bearing table. Anything in **Tier A** must have tests.
Tier B is "nice to have, plan when refactoring". Tier C is intentionally
not unit-tested.

### Tier A — Must have tests (refactor safety net)

| Module | Why critical | Current | Target |
|---|---|---|---|
| `mcp/oauth.py` | Production auth, headless flow on Streamlit Cloud, refresh + gist sync | 0 tests | 8–12 unit tests |
| `mcp/inderes_client.py` | All MCP tool calls flow through here | 0 tests | 4–6 tests |
| `agents/_common.py` | Boilerplate every agent depends on (build_chat_client etc.) | 0 tests | 3–5 tests |
| `agents/lead.py`, `lead_planner.py` | Synthesizer + planner — touched by Reflexion + HITL | 0 tests | 4–6 tests each (prompt-output shape) |
| `valuation/parser.py` | Already in Tier A — keep coverage | 451 LOC tested | maintain |
| `valuation/engine.py` | Excel parity is a hard SLA | 619 LOC tested | maintain |
| `orchestration/router.py` | Query classification, all queries flow through | 250 LOC tested | maintain |
| `orchestration/limits.py` | Hard caps, OWASP T1 | already tested | maintain |
| `orchestration/estimator.py` (NEW Wk 2) | HITL gate decisions depend on it | will ship with tests | 8+ tests |
| `orchestration/gate.py` (NEW Wk 2) | Pure function but high-stakes | will ship with tests | 6 tests |

### Tier B — Plan tests when refactoring

| Module | Why deferred | When to add |
|---|---|---|
| `orchestration/synthesis.py` | Big (1 032 LOC) but mostly formatters | When splitting into engine + formatter (Wk 3) |
| `orchestration/workflows.py` | Already partial coverage; integration test exists | Add unit tests when adding mid-run pause (Level 2 HITL) |
| `observability/narrate.py` | Log narration; visual bug, not data corruption | When Reflexion changes log format |
| `agents/research.py`, `valuation.py`, `sentiment.py` | Identical builder boilerplate — testing one tests all | Add 1 parameterised test after Wk 3 builder DRY |

### Tier C — Intentionally not unit-tested

| Module | Justification |
|---|---|
| `ui/app.py`, `ui/components.py`, `ui/charts.py` | Streamlit UI — manual smoke + eval suite catches behavioural regressions; unit tests fight the framework |
| `cli/render.py`, `cli/repl.py` | Personal CLI tools, low blast radius |
| `__main__.py`, `__init__.py` | Entry points, no logic |
| `logging.py` | Stdlib wrapper |

**Coverage target after Wk 2:** Tier A reaches ~95 %, Tier B/C unchanged.
This is the right ratio — we are not chasing line coverage on UI; we are
locking down the load-bearing core.

---

## 4. Test categories — what each is for

### 4.1 Unit tests (`tests/test_*.py`)
Pure logic with deterministic inputs. No network, no LLM, no Streamlit.
Run on every push.

**Examples:**
- `test_parser.py` — given a JSON blob, assert dataclass structure
- `test_router.py` — given a query string, assert classification
- `test_oauth_bootstrap.py` — given a tokens.json shape, assert state

**Style guide:**
- One concept per test function (`test_parser_handles_missing_roe`)
- Arrange / Act / Assert pattern
- Synthetic fixtures, not network captures
- No asyncio sleep, no real time
- Aim for ≤50 ms each, suite ≤30 s total

### 4.2 Integration tests
Test the *wiring* between components. May span 2–3 modules.

**Examples (current + planned):**
- `test_valuation_tool_guard.py` — synthesis + parser + valuation
- `test_fallback.py` — Gemini client fallback logic across model tiers
- NEW: `test_workflow_smoke.py` — fake MCP responses → run full workflow → assert run_log shape
- NEW: `test_oauth_flow.py` — happy path + refresh failure + gist fallback (HTTP mocked via pytest-httpx)

**Boundary:** if it needs >3 mocks, it's testing too much; split into units.

### 4.3 Eval suite (`evals/`)
Live LLM calls, real MCP, real prompts. Quality regression detection.

**When run:**
- Manual before merging anything that touches `agents/prompts/*.md`
- Manual before tagging a release
- (Future) nightly cron when we have an eval budget

**What it catches that unit tests don't:**
- Prompt regressions (e.g. agent stops citing sources)
- Model behaviour drift (Gemini Pro changes output style)
- End-to-end answer quality

**What it does NOT catch:**
- Code logic bugs (those break unit tests first)
- Performance regressions (no timing assertions yet)
- Cost regressions (planned: add cost ceiling per case)

### 4.4 Manual smoke
Streamlit UI + visual rendering. ~5 minutes of clicking through.

**When:**
- Before any push touching `ui/*`
- After any deploy that changed dependencies (Streamlit Cloud)

**What we test:** the 5 query types in BACKLOG §6 — single-company
analysis, multi-company comparison, sector overview, news/event lookup,
clarification fall-through.

### 4.5 Unit-testit vs evals — milloin kumpi?

Yksi virhe josta kannattaa varoittaa erikseen: niitä **helppo sekoittaa**,
koska molemmat "ajavat agenttia ja katsovat onko output OK". Ne testaavat
silti eri asioita ja eri kerroksilla.

> **Unit-testit testaavat että koodi toimii.
> Evals testaavat että AI-systeemi tuottaa hyviä vastauksia.**

| Ulottuvuus | Unit/agent-testit | Evals |
|---|---|---|
| Mitä testaa | Koodin **rakenne** — builderit, parserit, schemat | Vastauksen **laatu** — sitooko lähteet, hallusinoiko |
| Determinismi | Deterministinen | Stochastinen (LLM-judge voi vaihtaa mieltä) |
| Nopeus | ms–s | 10 s–1 min / case |
| Hinta | $0 | ~$0.05–0.50 / case |
| Ajetaan | CI:ssä joka push | Manuaalisesti ennen merge/release |
| Regressio kiinni | Refactor-bugin | Promptin tai mallin laadun rapautumisen |

#### Konkreettiset skenaariot — kuka kiinniottaa minkä

| Bugi | Unit | Eval |
|---|:---:|:---:|
| Multi-company valuation parser saa array, hajoaa | ✅ | ❌ (fall back to Tila B näyttää siedettävältä) |
| Promptin regressio mallin päivityksen jälkeen | ❌ (rakenne sama) | ✅ |
| Agentti hallusinoi ROE 25 % (oikea 8 %) | ❌ | ✅ |
| OAuth-refaktori rikkoo refreshin | ✅ (HTTP-mockit) | ❌ (token vielä voimassa kun eval ajetaan) |
| Streamlit-import ImportError (aamun bugi) | ✅ (`test_app_imports.py`) | ❌ (eval ei käynnistä Streamlit-prosessia) |

#### Kerrosajattelu

```
┌────────────────────────────────────────────────────────────────┐
│  Vastauksen laatu (faktat, lähteet, selkeys)                   │ ← Evals
└──────────────────────────▲─────────────────────────────────────┘
                           │
┌──────────────────────────┴─────────────────────────────────────┐
│  Agentin käyttäytyminen (oikeat toolit oikeassa järjestyksessä)│ ← Tool-call mockit (Taso 4)
└──────────────────────────▲─────────────────────────────────────┘
                           │
┌──────────────────────────┴─────────────────────────────────────┐
│  Output-skeeman tolerance (parser kestää LLM:n satunnaisuuden) │ ← Schema-testit (Taso 3)
└──────────────────────────▲─────────────────────────────────────┘
                           │
┌──────────────────────────┴─────────────────────────────────────┐
│  Builder + prompt-loading + dependency-wiring                  │ ← Builder-testit (Taso 1+2)
└────────────────────────────────────────────────────────────────┘
```

Alimmat tasot ajetaan joka push (millisekunteja). Ylin (evals) ajetaan
manuaalisesti kun **promptia, mallia tai agentin käytöstä** muutetaan.

#### Käytännön ohje — kun kohtaat bugin, mihin se kuuluu?

| Bugi näkyy näin | Kategoria | Testikerros |
|---|---|---|
| Streamlit kaatuu, exception trace | Koodibugi | Unit + smoke |
| Vastaus on tyhjä / "no data" virheellisesti | Koodibugi (parseri) | Unit |
| Vastaus on muotoiltu väärin (HTML rikki) | Koodibugi (formatter) | Unit |
| Vastaus on **väärä** (faktavirhe) | Laatuvirhe | Eval |
| Vastaus on kelvollinen mutta huono (lähteet puuttuvat) | Laatuvirhe | Eval |
| Hallusinaatio | Laatuvirhe | Eval |
| Refactor onnistuu, tuotannossa kaatuu | Kattavuusaukko | Lisää unit-testi sille alueelle |
| Laatu putoaa kun vaihdetaan Pro → Flash | Mallin valinta | Eval per malli |

#### Yhteen lauseeseen

> Unit-testit testaavat **että koodi toimii kun maailma toimii kuten odotat**.
> Evals testaavat **että lopputulos on hyvä kun maailma toimii satunnaisesti**
> (kuten LLM:t toimivat).

Eivät korvaa toisiaan. Pelkät unit-testit päästävät hallusinaatiot läpi.
Pelkät evals päästävät koodibugit läpi.

---

## 5. CI strategy (what to ship in Wk 2)

### 5.1 Minimum viable CI — `.github/workflows/ci.yml`

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.13" }
      - run: pip install ruff
      - run: ruff check src/ ui/ tests/
      - run: ruff format --check src/ ui/ tests/

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.13" }
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --extra dev
      - run: uv run pytest -q
        env:
          GEMINI_API_KEY: dummy-for-tests
```

### 5.2 What CI does NOT do (yet)

- **No mypy gate.** Type checking is currently aspirational; gating on
  it would block development. Plan: add `mypy src/inderes_agent/valuation/`
  in Wk 3 once a clean baseline exists, then expand module-by-module.
- **No eval suite in CI.** Live LLM calls cost money and are flaky.
  Manual + scheduled cron later.
- **No deploy gate.** Streamlit Cloud auto-deploys on push; we accept
  that until we have a staging slot.

### 5.3 What CI catches that the morning's `render_feedback_widget`
incident would have surfaced

- `ruff check` would have caught nothing (the import was syntactically valid).
- `pytest` would have caught nothing (no test imports `app.py`).
- A new test `tests/test_app_imports.py`:
  ```python
  def test_app_imports():
      """Smoke test: app.py + components.py import cleanly."""
      import importlib, sys
      sys.path.insert(0, "ui")
      importlib.import_module("components")
      # Don't run app.py top-level (it calls st.set_page_config),
      # but import-check it via py_compile:
      import py_compile
      py_compile.compile("ui/app.py", doraise=True)
  ```
  Would have caught it. **Add this in Wk 2.**

---

## 6. Conventions

### 6.1 Test file naming
- `tests/test_<module>.py` — unit tests for `src/inderes_agent/<module>.py`
- `tests/integration/test_<flow>.py` — multi-module flows (when we have ≥3)
- `evals/cases/<id>.yaml` — single eval case (existing)

### 6.2 Fixtures
- `tests/conftest.py` — global fixtures (dummy GEMINI_API_KEY, tmp_path
  helpers)
- Module-specific fixtures live next to the tests they serve
- No shared in-memory database fixtures — tests are independent

### 6.3 What to mock
- ✅ Network: HTTP via `pytest-httpx` (already in dev deps)
- ✅ Time: `freezegun` for token-expiry tests
- ✅ Filesystem: `tmp_path` (pytest builtin)
- ❌ Don't mock LLM responses with custom `MagicMock`. If you need to
  fake an LLM, capture a real response and store as a fixture file.
- ❌ Don't mock the agent-framework SDK internals. If a test is fighting
  the SDK, the test is wrong.

### 6.4 What to NOT test
- LLM output content. We have an eval suite for that.
- Streamlit widget rendering. Manual smoke.
- Third-party libraries. Trust them.

---

## 7. Wk 2 testing tasks (concrete)

| Task | Files | Effort | Tier |
|---|---|---|---|
| Add CI workflow | `.github/workflows/ci.yml` | 1 h | A |
| Add `test_app_imports.py` (smoke) | `tests/test_app_imports.py` | 30 min | A |
| OAuth tests (8–12) | `tests/test_oauth_runtime.py` | 4 h | A |
| MCP client tests (4–6) | `tests/test_inderes_client.py` | 2 h | A |
| Agent common tests (3–5) | `tests/test_agents_common.py` | 1.5 h | A |
| Agent builder + schema -testit (Tier A agents, ks. §11.8) | `tests/test_<agent>.py` × 5 | 4 h | A |
| Cost-tracker tests (HITL Step 1) | `tests/test_cost_tracker.py` | 1 h | A |
| Estimator tests (HITL Step 2) | `tests/test_estimator.py` | 2 h | A |
| Gate tests (HITL Step 3) | `tests/test_gate.py` | 30 min | A |
| Multi-company valuation parser fix + regression test | `tests/test_parser.py` (extend) | 30 min on top of fix | A |

Total: ~13 h spread across the foundation + HITL days.

---

## 8. Anti-patterns (things we will not do)

- **Test the implementation, not the behaviour.** Asserting on private
  function names breaks on every refactor.
- **Test framework code.** Streamlit, agent-framework, anthropic SDK —
  trust them.
- **Mock the world.** A test that mocks 8 things tests the mocks, not
  the code.
- **Snapshot test JSON output for everything.** Snapshots are useful
  for stable formats (eval reports). They are dangerous for evolving
  data shapes (run_log.json, agent outputs) — they make every output
  change look like a regression.
- **Skip a flaky test.** Flakiness is information. Either fix the
  underlying race, or delete the test if it's not load-bearing.
- **Add a test "for coverage."** Tests exist to catch real failure
  modes. Coverage is a side-effect, not a goal.

---

## 9. Maintenance

### 9.1 When tests fail
1. Read the failure. Don't immediately re-run.
2. If the failure is real, fix the code.
3. If the failure is a test bug, fix the test.
4. If the failure is "the SDK changed", update the test fixture, note
   in CHANGELOG.md.
5. Never `pytest -k "not flaky"`-skip without an issue tracker entry.

### 9.2 When tests block a refactor
- Update the tests in the same commit as the refactor.
- The diff should make obvious *what behaviour* changed and *why*.
- If the tests were testing implementation rather than behaviour, treat
  the test as legacy and rewrite — note the rewrite in the commit.

### 9.3 When new code is added
- Tier A code: tests in the same PR. No exceptions.
- Tier B code: tests within the same sprint, or explicit BACKLOG entry.
- Tier C code: smoke-checked manually, noted in PR description.

---

## 10. Definition of Done (Wk 2 testing)

- [ ] `.github/workflows/ci.yml` exists, passes on main
- [ ] All Tier A modules from §3 have tests (or explicit deferred
      BACKLOG entry)
- [ ] `test_app_imports.py` exists and would have caught the morning's
      ImportError
- [ ] HITL ships with cost-tracker, estimator, gate tests
- [ ] Multi-company valuation regression test added
- [ ] Coverage of Tier A modules ≥ 80 %, measured via `pytest --cov`
- [ ] LESSONS.md updated with one-line entry: "CI gate caught X bug
      week of YYYY-MM-DD" — when it actually does, write the note.

---

## 11. Agent-koodin testaus erityistapauksena

Agentit ovat erikoinen testauskohde kolmesta syystä:

1. **Stochastic output.** Sama input voi tuottaa eri vastauksen — pelkkä
   `assert agent.run(...) == "expected"` ei toimi.
2. **Ulkoiset I/O:t.** Agentti kutsuu MCP-tooleja, tooli kutsuu Inderes-APIa.
   Testin pitää eristää tämä ilman että testataan SDK:n sisuksia.
3. **Promptti on koodia.** Promptin muutos muuttaa käytöstä, mutta
   promptti ei lähde unit-testillä rikki — se lähtee eval-suitella.

Jaetaan agent-testit **viiteen tasoon ROI-järjestyksessä**. Tasot 1–3
ovat pakollisia Tier A -agenteille (lead, lead_planner, _common,
research, valuation). Taso 4 vain herkille agenteille. Taso 5 on eval
suite, ei unit-testi.

### 11.1 Taso 1 — Builder-testit (5 min per agent)

Testaa että `build_*_agent()` tuottaa toimivan `Agent`-instancen ilman
ympäristön rikkoutumista. **Ei kutsu LLM:ää.**

```python
# tests/test_lead_planner.py
def test_build_lead_planner_default():
    """Planner builds with Flash, no tools."""
    from inderes_agent.agents.lead_planner import build_lead_planner_agent
    agent = build_lead_planner_agent(deep=False)
    assert agent.name == "aino-lead-planner"
    assert agent.tools is None
    assert "PLANNER" in agent.instructions  # prompt loaded

def test_build_lead_planner_deep_mode():
    """deep=True selects Pro tier via resolver."""
    from inderes_agent.agents.lead_planner import build_lead_planner_agent
    agent = build_lead_planner_agent(deep=True)
    # Don't assert on internal client config (SDK detail).
    # Assert on observable: instructions still loaded, agent constructible.
    assert agent.instructions
    assert agent.name == "aino-lead-planner"
```

**Mitä tämä kiinniottaa:**
- Promptin tiedostonimi vääräksi muutettuna → `FileNotFoundError`
- Builder-funktion API rikki refaktorin jälkeen
- Riippuvuus `_common.py`:hin rikki

**Mitä tämä EI kiinniota:** käytöstä, output-laatua, prompt-regressioita.

Aikaa: ~15 min koko 9 agentin builder-katos.

### 11.2 Taso 2 — Promptien sanity-testit (10 min)

Promptit ovat `agents/prompts/*.md`. Ne **eivät ole dokumentaatiota,
ne ovat koodia**. Yksi parametrisoitu testi varmistaa peruskunto:

```python
# tests/test_prompts.py
import pytest
from pathlib import Path

PROMPTS = list((Path("src/inderes_agent/agents/prompts")).glob("*.md"))

@pytest.mark.parametrize("prompt_path", PROMPTS, ids=lambda p: p.name)
def test_prompt_well_formed(prompt_path):
    text = prompt_path.read_text(encoding="utf-8")
    assert len(text) > 100, f"{prompt_path.name} liian lyhyt — typo?"
    assert len(text) < 50_000, f"{prompt_path.name} liian pitkä — token-budjetti"
    # Promptit eivät saa sisältää kovakoodattuja päivämääriä jotka
    # kovakoodaavat agentin vuoden 2024 ajatteluun:
    assert "2024-" not in text, f"{prompt_path.name} sisältää kovakoodatun 2024-päivän"
    # Vaaditaan otsikko (struktuuri):
    assert text.lstrip().startswith("#"), f"{prompt_path.name} ei aloita otsikkoa"

def test_prompt_loader_resolves_all():
    """_common.load_prompt() löytää jokaisen referoimansa tiedoston."""
    from inderes_agent.agents._common import load_prompt
    for p in PROMPTS:
        loaded = load_prompt(p.name)
        assert loaded.startswith("# CURRENT DATE")  # date prefix injected
```

**Mitä tämä kiinniottaa:**
- Promptin uudelleennimeäminen ilman koodimuutosta
- Päivämäärä-bug joka tunnetaan LESSONS.md:stä (Gemini juuttuu 2024:ään)
- Promptin tyhjä tiedosto (commit-vahinko)

### 11.3 Taso 3 — Output-schema -testit (30 min per herkkä agentti)

Tärkein taso. Agentti tuottaa JSON / strukturoidun outputin → parser
muuttaa sen Pydantic-malliksi. Testataan **parserin contract**, ei LLM:ää.

```python
# tests/test_lead_planner_output.py
def test_planner_output_canonical_shape():
    """Tunnettu hyvä Gemini-vastaus → planner_parser hyväksyy."""
    from inderes_agent.orchestration.synthesis import _extract_planner_plan
    
    # Fixture: oikea vastaus tallennettu manuaalisesti yhdestä run:sta
    sample_output = (Path(__file__).parent / "fixtures/planner_sampo.json").read_text()
    plan = _extract_planner_plan(sample_output)
    
    assert plan.subagents
    assert all(s.name in {"RESEARCH", "VALUATION", "SENTIMENT", "QUANT", "PORTFOLIO"} 
               for s in plan.subagents)

def test_planner_output_handles_extra_whitespace():
    """LLM:t lisäilevät satunnaisia välilyöntejä — parserin kestettävä."""
    sample = '   \n\n  {"subagents": [{"name": "RESEARCH"}]}  \n  '
    plan = _extract_planner_plan(sample)
    assert plan.subagents[0].name == "RESEARCH"

def test_planner_output_rejects_garbage():
    """Jos LLM palauttaa täysin pielessä, throw — ei silent fallback."""
    with pytest.raises(ValidationError):
        _extract_planner_plan("This is not JSON at all")

def test_planner_output_handles_markdown_code_fence():
    """Gemini ympäröi joskus JSON:in ```json ...``` -fenceen."""
    sample = "```json\n{\"subagents\": [{\"name\": \"RESEARCH\"}]}\n```"
    plan = _extract_planner_plan(sample)
    assert plan.subagents[0].name == "RESEARCH"
```

**Avain: testaa parserin tolerance LLM:n epäjohdonmukaisuudelle.**
Tämä on missä **multi-company valuation -bugi** olisi jäänyt kiinni —
testissä joka antaa `[{...}, {...}, {...}]` (array) ja varmistaa että
parser käsittelee sen oikein.

**Fikstuurit:**
- Tallenna oikeat LLM-vastaukset `tests/fixtures/<agent>_<scenario>.json`
- Yksi kanonen "good" + 2–3 edge case (whitespace, code fence, partial)
- Älä luo niitä tyhjästä mielikuvituksella — captureta oikeasta ajosta

### 11.4 Taso 4 — Tool-call -mockit (1 h per workflow-skenaario)

Vain niille agenteille joiden **tool-kutsujen järjestys** on osa
contract-määritelmää (lähinnä RESEARCH joka tekee
`search-companies → get-fundamentals → list-content`-pattenin).

Käytä `pytest-httpx`-kirjastoa MCP-vastauksiin:

```python
# tests/test_research_tool_flow.py
import pytest
from pytest_httpx import HTTPXMock

@pytest.mark.asyncio
async def test_research_calls_search_then_fundamentals(httpx_mock: HTTPXMock):
    """RESEARCH-agentti hakee yhtiön ID:n ennen fundamentals-kutsua."""
    
    # Mock MCP-vastaukset
    httpx_mock.add_response(
        url="https://mcp.inderes.com",
        match_content=b'"name":"search-companies"',
        json={"result": [{"id": 258, "ticker": "SAMPO", "name": "Sampo"}]},
    )
    httpx_mock.add_response(
        url="https://mcp.inderes.com",
        match_content=b'"name":"get-fundamentals"',
        json={"result": {"company_id": 258, "fundamentals": [...]}},
    )
    
    # Ajetaan agentti — tämä OIKEASTI kutsuu Geminiä, mutta MCP on faked.
    # Vaihtoehto: capturetaan myös Gemini-vastaus replay-fixturena.
    from inderes_agent.agents.research import build_research_agent
    async with build_research_agent() as agent:
        result = await agent.run("Mikä on Sampon ROE?")
    
    # Verify tool order
    requests = httpx_mock.get_requests()
    assert b"search-companies" in requests[0].content
    assert b"get-fundamentals" in requests[1].content
```

**Tämä on raskasta. Tee vain kun:**
- Tool-järjestys on osa contractia (RESEARCH:in 3-step pattern)
- Bugi on jo tapahtunut tällä alueella (regressioesto)

Jätä **muut** agentit Tason 1–3 testeihin.

### 11.5 Taso 5 — Eval suite (jo olemassa, älä unit-testi)

`evals/golden.yaml` + LLM judge → quality drift. **Älä yritä replikoida
tätä unit-testillä.** Eval suite on rakennettu juuri stochastisille
output-laatu-arvioille; unit-testi joka yrittää sitä on hauras.

**Milloin lisäät evalin (et unit-testin):**
- Uusi feature muuttaa output-laatua
- Promptin muutos (mikä tahansa muutos!)
- Uuden tool:n liittäminen agenttiin

### 11.6 Replay-fixture-strategia

Kun haluat **deterministisen** testin oikealle LLM-outputille:

```bash
# 1. Aja oikeassa systeemissä, capture vastaus run-logista
cat ~/.inderes_agent/runs/20260510-143022-abc/research_subagent.json \
  | jq '.output' > tests/fixtures/research_sampo_canonical.json

# 2. Käytä testissä
def test_research_parser_canonical():
    text = Path("tests/fixtures/research_sampo_canonical.json").read_text()
    parsed = parse_research_output(text)
    assert parsed.company_id == 258
```

**Säännöt fixtureille:**
- Capturetaan **oikeasta ajosta**, ei käsin kirjoitetusta
- Anonymisoi PII jos sellaista ilmenee (ei ole tällä hetkellä)
- Kommentoi `# Captured from run YYYYMMDD-HHMMSS, Gemini Pro`
- Päivitä **vain kun behavior intentionally changes** — älä päivitä
  vaiennaaksesi flaky-testin
- Älä committaa fixtureja jotka ovat >100 KB — ne kuuluvat erilliseen
  data-pakettiin

### 11.7 Anti-patternit (mitä EI testata agent-koodissa)

| Anti-pattern | Miksi väärin | Mitä tee sen sijaan |
|---|---|---|
| `assert agent.run(...) == "expected text"` | Stochastic output | Eval suite |
| Mocketaan `Agent.run()` palauttamaan kovakoodattu string | Testataan mockia, ei agenttia | Replay fixture parser-tasolla |
| `assert "ROE" in agent_output` (tarkistetaan että keyword esiintyy) | Hauras: pieni promptin sanavalinnan muutos rikkoo | Output-schema testaa rakennetta, eval suite testaa sisältöä |
| Mocketaan `agent_framework_gemini` SDK:n sisäluokat | Tied SDK:n versioon, hajoaa joka päivityksessä | HTTP-tason mock (`pytest-httpx`) |
| Yksi monoliittinen test_agent_e2e | Kun rikkoutuu, ei tiedä mikä taso | Pilko: builder + schema + tool-call -tasoiksi |
| Snapshot-testaus agentin täydestä outputista | Joka prompt-tweak näyttää regressiolta | Snapshot vain stabiileja (eval-raportit) |

### 11.8 Tier A agent-testit Wk 2:ssa — konkreettinen lista

| Agent | Taso 1 | Taso 2 | Taso 3 | Taso 4 |
|---|---|---|---|---|
| `_common.py` | ✅ load_prompt + today_header | — | — | — |
| `lead.py` | ✅ build_lead_agent | — | ✅ output schema (jo osin tehty) | — |
| `lead_planner.py` | ✅ build × 2 (deep/normal) | ✅ planner.md sanity | ✅ Plan-objektin parserit | — |
| `research.py` | ✅ build | (per-agent shared) | ✅ company_id-parser | ⚠️ Vasta jos bugi |
| `valuation.py` | ✅ build | (shared) | ✅ FV/target-price -parser (laajenna olemassa olevaa) | — |
| `sentiment.py` | ✅ build | (shared) | ✅ paattely-parser | — |
| `quant.py`, `portfolio.py`, `conflict_detector.py` | ✅ build (yksi parametrisoitu) | (shared) | Vasta kun bugi | — |

**Aika-arvio:**
- Taso 1 (kaikki 9 agenttia, parametrisoitu): 1 h
- Taso 2: 0.5 h
- Taso 3 (5 agenttia × 30 min): 2.5 h
- **Yhteensä Wk 2:lle:** ~4 h, ei 1.5 h kuten oletin §7:ssä

Päivitän §7:n alla olevien tehtävien aikoja vastaavasti.

### 11.9 Mistä tunnistat että testit ovat oikein rakennettu

**Hyvä merkki:** kun muutat `lead_planner.md`:n sisältöä parantaaksesi
laatua → unit-testit pysyvät vihreinä, eval-suite näyttää uudet/paremmat
tulokset.

**Huono merkki:** prompt-tweak rikkoo 5 unit-testiä — testit ovat
liian läheisiä LLM-outputin sisältöön. Refaktoroi pois.

**Hyvä merkki:** kun joku rikkoo `_common.py:load_prompt()`:n →
*kaikki* agenttitestit punertuu välittömästi. Vahva regressioverkko.

**Huono merkki:** OAuth-refaktori menee mainiin ja testit pysyvät vihreinä —
puuttuva kattavuus, ei testien laatu (tämä on tämänhetkinen tila!).

---

## 12. Anti-goals — explicit non-targets

- We are NOT chasing 90 % overall line coverage.
- We are NOT testing every UI render path.
- We are NOT writing tests as documentation. The code is the documentation.
- We are NOT running evals in CI. They cost money and are slow.
- We are NOT introducing a separate test framework. pytest + pytest-asyncio
  + pytest-httpx is enough.

---

## 13. Open questions

- Should we add `pytest --cov` reporting? **Probably not yet.** Coverage
  reports are political — they incentivise low-quality "for coverage"
  tests. Revisit in Wk 4 if coverage of Tier A drops below 80 %.
- Should evals run on a cron? **Yes, eventually.** Once we have a
  monthly eval budget allocated, schedule weekly. Track in BACKLOG.
- Should we mock Gemini at the SDK level or the HTTP level? **HTTP via
  pytest-httpx.** Mocking SDK objects ties tests to SDK internals.
