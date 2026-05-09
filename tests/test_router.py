"""Router unit tests — JSON parsing, fallback behavior, conversation context."""

from __future__ import annotations

import pytest

from inderes_agent.orchestration.router import (
    Domain,
    QueryClassification,
    _enforce_comparison_floor,
    _extract_json,
    query_has_valuation_intent,
)


def test_extract_json_plain():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_code_fence():
    raw = '```json\n{"domains": ["quant"], "is_comparison": false, "companies": ["Konecranes"], "reasoning": "x"}\n```'
    parsed = _extract_json(raw)
    assert parsed["domains"] == ["quant"]


def test_extract_json_with_prose_leak():
    raw = 'Here is the JSON:\n\n{"domains":["quant"],"companies":[],"is_comparison":false,"reasoning":"x"}\n\nOK'
    parsed = _extract_json(raw)
    assert parsed["domains"] == ["quant"]


def test_query_classification_validates_domains():
    cls = QueryClassification(
        domains=[Domain.QUANT, Domain.SENTIMENT],
        companies=["Konecranes"],
        is_comparison=False,
        reasoning="single P/E",
    )
    assert Domain.QUANT in cls.domains
    assert cls.companies == ["Konecranes"]


def test_query_classification_rejects_invalid_domain():
    with pytest.raises(Exception):
        QueryClassification(
            domains=["not-a-domain"],  # type: ignore[list-item]
            companies=[],
            is_comparison=False,
            reasoning="",
        )


# ─────────────────────────────────────────────────────────────────────────────
# query_has_valuation_intent — gate for the alternative-valuation toggle
#
# The toggle MUST NOT add VALUATION to qualitative-only queries. The
# heuristic is intentionally conservative: false negatives (no Greenwald
# table when one might've helped) are much better UX than false positives
# (table appears for "explain why X" questions).
#
# Surfaced from production run 20260508-220611-207 ("selitä mistä Nordean
# kannattavuus oikeasti tulee") where the toggle force-added valuation and
# the user got a fair-value table with no quantitative context to it.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("query", [
    # Explicit valuation requests
    "tee arvonmääritys Nordeasta",
    "Anna Sampolle arvonmääritys",
    "mikä on Nordean fair value",
    "Nordean valuation tällä hetkellä",
    # Sensitivity / scenario probes (the canonical Q2 wording variants)
    "entäs jos roe olisi 13%",
    "mitä jos ROE olisi 11%",
    "jos ROE olisi 13%, mikä on arvostus",
    "jos roe laskee, paljonko vaikutus",
    # Multiples / market relations
    "Nordean P/B-kerroin verrattuna sektoriin",
    "Bittium P/E nyt",
    # Verdict-style
    "onko Nordea aliarvostettu",
    "kannattaako ostaa nyt",
    "Inderesin tavoitehinta Nordealle",
    # Greenwald / model-specific
    "implied growth Nordealle",
    "EPV Sampolle",
    "turvamarginaali nyt",
])
def test_valuation_intent_true_for_explicit_queries(query: str):
    """Gate fires for queries that clearly want valuation output."""
    assert query_has_valuation_intent(query), (
        f"Expected True for {query!r} but got False — heuristic is too narrow."
    )


@pytest.mark.parametrize("query", [
    # Pure qualitative — no numbers, no model
    "selitä mistä Nordean kannattavuus oikeasti tulee",
    "miksi Nordea on niin vahva pohjoismaissa",
    "kerro Nordean strategiasta",
    "miten korkotaso vaikuttaa pankkeihin",
    "Nokian kasvunäkymät 2027",
    # Comparisons that don't ask for valuation
    "miten Nordea eroaa SEB:stä strategisesti",
    "vertaile Nordean ja Swedbankin liiketoimintamalleja",
    # Insider / sentiment / corporate actions
    "onko Nordeassa insider-ostoja viime kuussa",
    "mitä Inderesin foorumilla puhutaan Nokiasta",
    "milloin Nordea julkaisee Q2-tuloksen",
    # General market commentary
    "miten OMXH on kehittynyt tänä vuonna",
])
def test_valuation_intent_false_for_qualitative_queries(query: str):
    """Gate must NOT fire for purely qualitative questions — the user
    asked about strategy/sentiment/timing, not numerical valuation."""
    assert not query_has_valuation_intent(query), (
        f"Expected False for {query!r} but got True — heuristic too aggressive."
    )


def test_valuation_intent_case_insensitive():
    """Match should be case-insensitive — UI doesn't normalize input."""
    assert query_has_valuation_intent("ARVONMÄÄRITYS Nordealle")
    assert query_has_valuation_intent("ENTÄS JOS ROE OLISI 13%")
    assert query_has_valuation_intent("Mikä on Nordean Fair Value")


def test_valuation_intent_handles_typos_and_morphology():
    """Finnish morphology: stem-based matches absorb partitive/genitive.

    Pin a few real morphology variants we expect to hit.
    """
    # "arvostuksen" → matches "arvostuks"
    assert query_has_valuation_intent("Sammon arvostuksen muutos")
    # "arvostusta" → matches "arvostust"
    assert query_has_valuation_intent("anna arvostusta Nordealle")
    # "tavoitehinnasta" → matches "tavoitehint"
    assert query_has_valuation_intent("kerro tavoitehinnasta")


# ---------------------------------------------------------------------------
# Comparison-floor enforcement
#
# Eval baseline (evals/golden.yaml case_001) caught the router emitting
# is_comparison=true with only ["quant"] for "Vertaile Sammon ja Nordean
# kannattavuutta" — 19 historical runs hit this. The post-processor
# below the LLM call is belt-and-braces against Flash Lite ignoring the
# prompt rule.
# ---------------------------------------------------------------------------


def _qc(domains, *, is_comparison, companies=None, reasoning="x"):
    """Tiny helper — easier to read than QueryClassification(...) inline."""
    return QueryClassification(
        domains=list(domains),
        companies=companies or [],
        is_comparison=is_comparison,
        reasoning=reasoning,
    )


def test_comparison_floor_expands_quant_only():
    """Bug from eval baseline: comparison routed to quant only."""
    c = _qc([Domain.QUANT], is_comparison=True, companies=["Sampo", "Nordea"])
    out = _enforce_comparison_floor(c)
    assert set(out.domains) >= {Domain.QUANT, Domain.RESEARCH, Domain.SENTIMENT}
    # Annotation makes the expansion visible in routing.json.
    assert "expanded to comparison floor" in (out.reasoning or "")


def test_comparison_floor_expands_quant_research():
    """Half-routed comparisons (quant+research) still need sentiment."""
    c = _qc([Domain.QUANT, Domain.RESEARCH], is_comparison=True)
    out = _enforce_comparison_floor(c)
    assert set(out.domains) >= {Domain.QUANT, Domain.RESEARCH, Domain.SENTIMENT}


def test_comparison_floor_already_satisfied_unchanged():
    """When the floor is met, the post-processor is a no-op."""
    original = _qc(
        [Domain.QUANT, Domain.RESEARCH, Domain.SENTIMENT],
        is_comparison=True,
        companies=["Sampo", "Nordea"],
    )
    out = _enforce_comparison_floor(original)
    assert out.domains == original.domains
    assert out.reasoning == original.reasoning  # no annotation when no change


def test_comparison_floor_preserves_extra_domains():
    """Valuation toggle adds 'valuation' — floor expansion must not drop it."""
    c = _qc(
        [Domain.QUANT, Domain.VALUATION],
        is_comparison=True,
        companies=["Sampo", "Nordea"],
    )
    out = _enforce_comparison_floor(c)
    # Original domains preserved + floor added.
    assert Domain.VALUATION in out.domains
    assert set(out.domains) >= {
        Domain.QUANT, Domain.RESEARCH, Domain.SENTIMENT, Domain.VALUATION,
    }


def test_comparison_floor_does_not_apply_to_non_comparison():
    """Non-comparison single-quant lookups stay narrow.

    "What's Konecranes' P/E?" → quant alone is correct. The floor is
    a comparison-only rule.
    """
    c = _qc([Domain.QUANT], is_comparison=False, companies=["Konecranes"])
    out = _enforce_comparison_floor(c)
    assert out.domains == [Domain.QUANT]
    assert "expanded" not in (out.reasoning or "")
