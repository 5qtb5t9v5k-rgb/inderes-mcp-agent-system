"""Tests for the päättely parser — case_002 fix.

Eval baseline (evals/golden.yaml case_002_paattely_schema) caught this:
in 183 historical runs LEAD produced 0 structured Päättely outputs but
55 well-formed 4-paragraph prose blocks. The UI's 2×2 slot grid
renderer expects structured `{disagree, resolution, uncertain, skipped}`,
so it was effectively dead code.

Fix: when the prose conforms to the prompt's 4-paragraph spec, the
parser now lifts it into the structured slot dict in paragraph order.
Fewer-than-4-paragraph cases continue to return `{prose: ...}` so the
UI's prose fallback still works.
"""

from __future__ import annotations

from inderes_agent.orchestration.synthesis import _extract_paattely

# ---------------------------------------------------------------------------
# Four-paragraph prose → structured slots
# ---------------------------------------------------------------------------

FOUR_PARA_TEXT = """\
Some preamble text from LEAD before the päättely.

**🧠 Päättely**

quant-Nordea ja quant-Sampo eivät olleet aidosti eri mieltä, vaan data oli jakautunut: kumpikin haki vain oman yhtiönsä numerot.

Otin P/E:t suoraan kummankin get-inderes-estimates -vastauksesta; molemmilla 2026E-arvot.

Sammon ROE 14,9 % on yksilähteinen — vain quant-Sampo raportoi sen, ei ristivahvistettu eri tool-kutsulla.

En hakenut sentimentti- tai foorumi-näkökulmaa (router ei ohjannut), enkä tarkistanut Q1-tuloksien analyytikkokommentteja erikseen.

## Yhteenveto

The actual answer body starts here.
"""


def test_four_paragraph_prose_lifts_to_structured_slots():
    """The case_002 fix in action — 4 paragraphs become 4 named slots."""
    cleaned, raw, parsed, error = _extract_paattely(FOUR_PARA_TEXT)
    assert error is None
    assert parsed is not None

    # Structured form returned, not prose.
    assert "disagree" in parsed
    assert "resolution" in parsed
    assert "uncertain" in parsed
    assert "skipped" in parsed
    assert "prose" not in parsed  # mutually exclusive

    # Order matches the prompt's spec at lead.md §31-53.
    assert "eri mieltä" in parsed["disagree"]
    assert "Otin P/E" in parsed["resolution"]
    assert "yksilähteinen" in parsed["uncertain"]
    assert "En hakenut" in parsed["skipped"]


def test_four_paragraph_prose_strips_block_from_cleaned():
    """The päättely block must be removed from the body so the UI doesn't
    render the same content twice (once in the slot grid, once in the answer)."""
    cleaned, raw, parsed, _ = _extract_paattely(FOUR_PARA_TEXT)
    assert "🧠 Päättely" not in cleaned
    assert "yksilähteinen" not in cleaned  # one of the slot contents
    # But content that came AFTER the päättely block survives.
    assert "Yhteenveto" in cleaned
    assert "answer body starts here" in cleaned


# ---------------------------------------------------------------------------
# Three-paragraph (partial) → prose fallback
# ---------------------------------------------------------------------------

THREE_PARA_TEXT = """\
**🧠 Päättely**

Subagentit linjassa, ei merkittäviä ristiriitoja.

Otin numerot suoraan get-fundamentals-vastauksesta.

En tehnyt erillistä validointia.

## Yhteenveto

Body.
"""


def test_three_paragraph_prose_falls_back_to_prose_form():
    """Fewer than 4 paragraphs → prose form (slot grid would have empty
    slots which reads worse than a styled prose block)."""
    cleaned, raw, parsed, error = _extract_paattely(THREE_PARA_TEXT)
    assert error is None
    assert parsed is not None
    assert "prose" in parsed
    # Structured keys must NOT appear when we fall back.
    assert "disagree" not in parsed
    # Prose body contains all three paragraphs.
    assert "linjassa" in parsed["prose"]
    assert "get-fundamentals" in parsed["prose"]
    assert "validointia" in parsed["prose"]


# ---------------------------------------------------------------------------
# Empty / missing päättely
# ---------------------------------------------------------------------------


def test_no_paattely_block_returns_text_unchanged():
    text = "Just an answer body with no päättely block at all.\n\n## Yhteenveto\nstuff"
    cleaned, raw, parsed, error = _extract_paattely(text)
    assert cleaned == text
    assert raw is None
    assert parsed is None
    assert error is None


# Note: an "empty päättely" edge case (header with literally nothing
# after it) is not asserted here — in practice LEAD always writes at
# least one sentence under the header, and the regex's terminator
# lookahead picks up subsequent headings as part of the body when no
# päättely text exists. The structural fix (4-paragraph → slots) is
# the one we care about for case_002.


# ---------------------------------------------------------------------------
# Five-paragraph case — capped at 4
# ---------------------------------------------------------------------------

FIVE_PARA_TEXT = """\
**🧠 Päättely**

Para 1 disagree content here covering the conflicts found.

Para 2 resolution explaining how I picked the answer.

Para 3 uncertain claims that came from one source only.

Para 4 what I skipped, the things I didn't verify myself.

Para 5 leaks past the four-paragraph cap and should NOT appear in any slot.

## Yhteenveto

Body.
"""


def test_five_paragraph_capped_at_four_into_structured():
    """LEAD occasionally writes 5+ paragraphs. We cap at 4 (matches the
    prompt's hard limit) and the 5th goes back to the answer body."""
    cleaned, raw, parsed, _ = _extract_paattely(FIVE_PARA_TEXT)
    assert parsed is not None
    assert "disagree" in parsed
    assert "Para 4" in parsed["skipped"]
    # Para 5 must NOT appear in any slot.
    for k in ("disagree", "resolution", "uncertain", "skipped"):
        assert "Para 5" not in (parsed.get(k) or "")
    # And Para 5 should land back in cleaned (the answer body).
    assert "Para 5" in cleaned
