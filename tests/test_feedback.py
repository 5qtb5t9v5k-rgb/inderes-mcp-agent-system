"""Tests for 👍/👎 feedback persistence (Wk 1 #4 sprint roadmap).

The widget itself lives in `ui/components.py` and needs a Streamlit
runtime to exercise — out of scope for these unit tests. What IS
testable (and where bugs would silently corrupt our feedback signal)
is the read/write layer in `run_log.py`. These tests cover:

- Round-trip integrity: write a rating, read it back unchanged.
- Last-write-wins semantics: a user changing their mind from 👍 to 👎
  must overwrite cleanly, not append a second record.
- Input validation: typoed sentiments must raise, not silently produce
  garbage on disk.
- Comment normalisation: empty / whitespace-only comments collapse to
  `None` so the UI's "show comment if present" check stays simple.
- Read robustness: missing file → None, corrupt JSON → None (we never
  want a stale feedback file to crash the page render).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inderes_agent.observability.run_log import (
    read_feedback,
    write_feedback,
)


# ---------------------------------------------------------------------------
# write_feedback — happy path
# ---------------------------------------------------------------------------


def test_write_feedback_creates_json_file(tmp_path: Path):
    write_feedback(tmp_path, sentiment="up")
    assert (tmp_path / "feedback.json").exists()


def test_write_feedback_round_trip(tmp_path: Path):
    """write → read returns the same sentiment + comment."""
    write_feedback(tmp_path, sentiment="up", comment="Erinomainen analyysi!")
    fb = read_feedback(tmp_path)
    assert fb is not None
    assert fb["sentiment"] == "up"
    assert fb["comment"] == "Erinomainen analyysi!"
    # Timestamp is set, in ISO format
    assert "ts" in fb
    assert "T" in fb["ts"]  # iso datetime separator


def test_write_feedback_without_comment(tmp_path: Path):
    """Most 👍 clicks come with no comment — the comment field
    should be ``None``, not an empty string."""
    write_feedback(tmp_path, sentiment="down")
    fb = read_feedback(tmp_path)
    assert fb["comment"] is None


def test_write_feedback_strips_whitespace_only_comment(tmp_path: Path):
    """A user who clicks Lähetä without typing should get the same
    result as not submitting a comment — a whitespace-only string is
    semantically empty."""
    write_feedback(tmp_path, sentiment="down", comment="   \n  ")
    fb = read_feedback(tmp_path)
    assert fb["comment"] is None


# ---------------------------------------------------------------------------
# write_feedback — last-write-wins
# ---------------------------------------------------------------------------


def test_write_feedback_overwrites_previous(tmp_path: Path):
    """User changes their mind: 👍 first, then 👎. The second write
    must replace the first — a side-by-side aggregation would mean
    both ratings count, which is wrong for our metrics."""
    write_feedback(tmp_path, sentiment="up", comment="Hyvä!")
    write_feedback(tmp_path, sentiment="down", comment="Eipäs ollutkaan.")
    fb = read_feedback(tmp_path)
    assert fb["sentiment"] == "down"
    assert fb["comment"] == "Eipäs ollutkaan."

    # Only one feedback file on disk — no -v2 / -prev sidecar.
    assert len(list(tmp_path.glob("feedback*.json"))) == 1


def test_write_feedback_overwrites_with_no_comment(tmp_path: Path):
    """👎 with comment, then 👍 without — the previous comment must
    NOT bleed through."""
    write_feedback(tmp_path, sentiment="down", comment="Lähde puuttui.")
    write_feedback(tmp_path, sentiment="up")
    fb = read_feedback(tmp_path)
    assert fb["sentiment"] == "up"
    assert fb["comment"] is None  # NOT "Lähde puuttui."


# ---------------------------------------------------------------------------
# write_feedback — validation
# ---------------------------------------------------------------------------


def test_write_feedback_rejects_invalid_sentiment(tmp_path: Path):
    """A typoed sentiment from a future caller must raise, not silently
    produce garbage on disk that breaks downstream aggregation."""
    with pytest.raises(ValueError, match="sentiment"):
        write_feedback(tmp_path, sentiment="meh")
    # No file written
    assert not (tmp_path / "feedback.json").exists()


def test_write_feedback_rejects_empty_sentiment(tmp_path: Path):
    with pytest.raises(ValueError):
        write_feedback(tmp_path, sentiment="")


# ---------------------------------------------------------------------------
# read_feedback — robustness
# ---------------------------------------------------------------------------


def test_read_feedback_returns_none_when_missing(tmp_path: Path):
    """Most run dirs have no feedback yet — must return None, not raise."""
    assert read_feedback(tmp_path) is None


def test_read_feedback_returns_none_on_corrupt_json(tmp_path: Path):
    """A half-written or hand-edited corrupt file must NOT crash the
    render path. Feedback is non-critical telemetry — degrade gracefully."""
    (tmp_path / "feedback.json").write_text("{not valid json", encoding="utf-8")
    assert read_feedback(tmp_path) is None


def test_read_feedback_returns_dict_with_sentiment_field(tmp_path: Path):
    """Smoke check: the returned dict has the documented schema fields."""
    write_feedback(tmp_path, sentiment="up", comment="x")
    fb = read_feedback(tmp_path)
    assert isinstance(fb, dict)
    assert set(fb.keys()) == {"sentiment", "comment", "ts"}


# ---------------------------------------------------------------------------
# Disk format — JSON is human-readable + utf-8 safe
# ---------------------------------------------------------------------------


def test_feedback_json_is_utf8_safe_for_finnish(tmp_path: Path):
    """Finnish comments contain ä, ö, å — must round-trip without
    \\uXXXX escaping that makes manual file inspection painful."""
    write_feedback(tmp_path, sentiment="down", comment="Ennusteet näyttävät vääriltä")
    raw = (tmp_path / "feedback.json").read_text(encoding="utf-8")
    # Direct unicode chars in the file, not ä
    assert "näyttävät" in raw
    assert "\\u" not in raw
