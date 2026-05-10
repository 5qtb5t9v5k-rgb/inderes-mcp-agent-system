"""Tests for footnote markers + definitions extraction.

LEAD's prompt requires `[Q1]`/`[R2]`/`[S3]`/`[V4]`/`[P5]` markers
after every grounded claim, plus a `**📚 Lähdeviittaukset:**`
definitions block at the end of the synthesis. The UI parser:

1. Strips the definitions block off the rendered body so it doesn't
   appear twice.
2. Wraps each `[X<n>]` marker in a persona-colored `<sup>` with a
   browser-native `title` tooltip populated from the definitions.

Backward compat: legacy plain `[1]` / `[2]` markers from older runs
still get wrapped, just color-neutrally and tooltip-less when no
definition matches.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Tests run from repo root; ui/ isn't on the package path.
_UI_DIR = Path(__file__).resolve().parent.parent / "ui"
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

from components import (  # noqa: E402
    _extract_footnote_definitions,
    _style_footnote_markers,
)


# ---------------------------------------------------------------------------
# _extract_footnote_definitions
# ---------------------------------------------------------------------------


SYNTHESIS_WITH_DEFS = """\
Suositus on Vähennä[Q1] ja tavoitehinta 24,00 €[Q1].

Q1-tulos oli kädenlämpöinen[R2].

**📚 Lähdeviittaukset:**
- [Q1] quant · get-inderes-estimates → target_price=24.00 €, recommendation=REDUCE
- [R2] research · read-document-sections → "UPM Q1'26: Säilytämme tarkkailuasemat"
- [V4] valuation · engine output → fv_gordon=19.97 €

**📖 Lähteet:**
- [UPM Q1'26](https://www.inderes.fi/research/upm-q126-...)
"""


def test_extract_definitions_returns_marker_to_explanation_map():
    cleaned, defs = _extract_footnote_definitions(SYNTHESIS_WITH_DEFS)
    assert "Q1" in defs
    assert "R2" in defs
    assert "V4" in defs
    assert "target_price=24.00 €" in defs["Q1"]
    assert "Säilytämme tarkkailuasemat" in defs["R2"]
    assert "fv_gordon=19.97" in defs["V4"]


def test_extract_definitions_strips_block_from_cleaned():
    """The definitions section must NOT appear in the cleaned body —
    otherwise the UI renders the content twice (once as tooltips on
    the markers, once as a trailer block in the answer)."""
    cleaned, _ = _extract_footnote_definitions(SYNTHESIS_WITH_DEFS)
    assert "📚 Lähdeviittaukset" not in cleaned
    assert "[Q1] quant · get-inderes-estimates" not in cleaned
    # But the body content above + the **📖 Lähteet** below survive.
    assert "Suositus on Vähennä" in cleaned
    assert "📖 Lähteet" in cleaned


def test_extract_definitions_handles_missing_block():
    """No definitions section → returns text unchanged + empty dict."""
    text = "Just an answer with no footnote definitions block."
    cleaned, defs = _extract_footnote_definitions(text)
    assert cleaned == text
    assert defs == {}


def test_extract_definitions_handles_alternative_headers():
    """Both 'Lähdeviittaukset' (FI) and 'Sources' / 'Footnotes' (EN)
    are recognised so the parser works in both languages."""
    en_text = """\
Recommendation is REDUCE[Q1].

**📚 Sources:**
- [Q1] quant · get-inderes-estimates → target=24

**📖 References:**
- [link](https://example.com)
"""
    cleaned, defs = _extract_footnote_definitions(en_text)
    assert "Q1" in defs
    assert "target=24" in defs["Q1"]
    assert "📚 Sources" not in cleaned


# ---------------------------------------------------------------------------
# _style_footnote_markers — persona-prefixed
# ---------------------------------------------------------------------------


def test_style_persona_marker_gets_color_class():
    """`[Q1]` gets `ia-fn ia-fn-q` (persona color = quant green)."""
    html = "Suositus[Q1] on Vähennä."
    out = _style_footnote_markers(html, {})
    assert 'class="ia-fn ia-fn-q"' in out
    assert "[Q1]" in out  # marker text preserved


def test_style_each_persona_letter_has_distinct_class():
    """Q→q, R→r, S→s, V→v, P→p — all five mapped."""
    html = "Q[Q1] R[R2] S[S3] V[V4] P[P5]"
    out = _style_footnote_markers(html, {})
    assert 'ia-fn-q' in out
    assert 'ia-fn-r' in out
    assert 'ia-fn-s' in out
    assert 'ia-fn-v' in out
    assert 'ia-fn-p' in out


def test_style_marker_with_definition_gets_data_tooltip_and_aria_label():
    """Populated markers get `data-tooltip` (drives the CSS popup, works
    on hover AND tap) plus `aria-label` for screen-reader access. The
    browser's native `title` is intentionally omitted: emitting both
    `title` and a CSS popup made the user see two stacked tooltips on
    hover (reported 2026-05-10)."""
    defs = {"Q1": "quant · get-inderes-estimates → target_price=24.00 €"}
    out = _style_footnote_markers("Suositus[Q1] on Vähennä.", defs)
    # CSS-popup driver + a11y label both present
    assert 'aria-label="quant · get-inderes-estimates → target_price=24.00 €"' in out
    assert 'data-tooltip="quant · get-inderes-estimates → target_price=24.00 €"' in out
    # tabindex makes the marker focusable so mobile tap brings up the popup
    assert 'tabindex="0"' in out
    # Native title attribute MUST NOT appear (would produce double tooltip)
    assert 'title=' not in out


def test_style_marker_html_escapes_dangerous_chars_in_tooltip():
    """A definition body with `<script>` or quotes must be escaped so
    neither the title nor data-tooltip attribute can break out."""
    defs = {"Q1": '<script>alert("xss")</script>'}
    out = _style_footnote_markers("X[Q1]", defs)
    # Both attribute values must NOT contain raw < or unescaped " inside.
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_style_marker_without_definition_uses_persona_fallback_tooltip():
    """A marker that LEAD emitted but didn't define falls back to a
    persona-name tooltip ("quant — numero / suositus / tavoitehinta")
    so the user gets at least the source category. Better than an
    empty tooltip when LEAD drops the Lähdeviittaukset block."""
    out = _style_footnote_markers("Suositus[Q1].", {})
    assert 'class="ia-fn ia-fn-q"' in out
    # Fallback tooltip present — uses persona name
    assert 'aria-label="quant' in out
    assert 'data-tooltip="quant' in out
    assert 'tabindex="0"' in out


def test_style_marker_definition_wins_over_fallback():
    """When LEAD emits a real definition, it overrides the fallback."""
    defs = {"Q1": "quant · get-fundamentals → P/E=14.0"}
    out = _style_footnote_markers("Suositus[Q1].", defs)
    # Real definition is used, not the persona fallback
    assert 'aria-label="quant · get-fundamentals → P/E=14.0"' in out
    # Fallback string should NOT appear
    assert 'numero / suositus' not in out


# ---------------------------------------------------------------------------
# Combined markers — `[Q1, Q2]`, `[R1, R2, R3]`, etc.
#
# LEAD sometimes writes the combined form when several tool calls back
# the same sentence. The parser must render each as a separate sup
# with its own tooltip, NOT leave the bracket-with-comma unstyled.
# ---------------------------------------------------------------------------


def test_style_combined_markers_split_into_separate_sups():
    """`[Q1, Q2]` becomes two separate <sup> badges, each with its
    own persona color + tooltip."""
    defs = {
        "Q1": "quant · search-companies",
        "Q2": "quant · get-fundamentals",
    }
    out = _style_footnote_markers("Sammon ROE[Q1, Q2] on 14 %.", defs)
    # Two distinct sup tags emitted
    assert out.count('<sup') == 2
    # Both keep persona color
    assert out.count('ia-fn-q') == 2
    # Each gets its own tooltip via aria-label
    assert 'aria-label="quant · search-companies"' in out
    assert 'aria-label="quant · get-fundamentals"' in out
    # The literal "[Q1, Q2]" combined form must NOT survive in the output
    assert '[Q1, Q2]' not in out
    # Both Q1 and Q2 surfaces appear
    assert '[Q1]' in out
    assert '[Q2]' in out


def test_style_combined_markers_mixed_personas():
    """Combined markers can mix personas: `[Q1, R2, S3]` — each gets
    its own persona color class."""
    out = _style_footnote_markers("Vertailu[Q1, R2, S3] osoittaa…", {})
    assert 'ia-fn-q' in out
    assert 'ia-fn-r' in out
    assert 'ia-fn-s' in out
    # Three separate sups, not one combined
    assert out.count('<sup') == 3


def test_style_combined_markers_handles_whitespace_variants():
    """`[Q1,Q2]` (no spaces), `[Q1, Q2]`, `[Q1 , Q2]` — all should work."""
    for variant in ("[Q1,Q2]", "[Q1, Q2]", "[Q1 , Q2]", "[ Q1, Q2 ]"):
        out = _style_footnote_markers(f"X{variant} Y", {})
        assert out.count('<sup') == 2, f"failed on variant: {variant!r}"


def test_style_legacy_single_marker_still_works_after_combined_support():
    """Adding combined-marker support must not break the single-marker
    case — still emits one styled sup."""
    out = _style_footnote_markers("Suositus[Q1] on Vähennä.", {})
    assert out.count('<sup') == 1
    assert 'ia-fn-q' in out


# ---------------------------------------------------------------------------
# _style_footnote_markers — legacy plain markers
# ---------------------------------------------------------------------------


def test_style_legacy_plain_marker_still_works():
    """Pre-2026-05-10 runs used plain `[1]` markers without persona
    prefix. They still render — color-neutrally."""
    out = _style_footnote_markers("Old marker[1] here.", {})
    assert 'class="ia-fn"' in out  # neutral, no -q/-r/-etc.
    assert 'ia-fn-' not in out


def test_style_legacy_marker_with_matching_definition():
    """Legacy `[1]` plus a matching `1`-key definition still tooltips."""
    out = _style_footnote_markers("X[1]", {"1": "old style note"})
    assert 'title="old style note"' in out


# ---------------------------------------------------------------------------
# Integration: synthesis with definitions → cleaned + tooltipped
# ---------------------------------------------------------------------------


def test_full_pipeline_synthesis_to_tooltipped_html():
    """End-to-end: extract definitions, then style markers in the
    cleaned body. Markers should have tooltips, definitions block
    should be gone."""
    cleaned, defs = _extract_footnote_definitions(SYNTHESIS_WITH_DEFS)
    out = _style_footnote_markers(cleaned, defs)

    # Three distinct persona-colored markers
    assert 'ia-fn-q' in out
    assert 'ia-fn-r' in out

    # Each populated marker has an aria-label (drives the CSS tooltip)
    assert 'aria-label="quant · get-inderes-estimates' in out
    assert 'aria-label="research · read-document-sections' in out

    # The definitions trailer block is gone
    assert "Lähdeviittaukset" not in out

    # The body content survives
    assert "Suositus on" in out
    assert "kädenlämpöinen" in out
