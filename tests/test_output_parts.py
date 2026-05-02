"""Tests for `extract_parts` — turning MAF response objects into structured markdown."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from inderes_agent.observability.output_parts import (
    _looks_like_python,
    _strip_dangling_image_refs,
    extract_parts,
)


# ---------------------------------------------------------------------------
# Fakes mimicking the shape of MAF Content / Message / AgentResponse
# ---------------------------------------------------------------------------

@dataclass
class FakeContent:
    type: str
    text: str | None = None


@dataclass
class FakeMessage:
    contents: list[FakeContent]


@dataclass
class FakeResponse:
    messages: list[FakeMessage]
    text: str = ""


# ---------------------------------------------------------------------------
# Heuristic detection
# ---------------------------------------------------------------------------

def test_python_detection_import_lead():
    assert _looks_like_python("import pandas as pd\nimport numpy as np")


def test_python_detection_from_import():
    assert _looks_like_python("from collections import defaultdict\n\ndefaultdict(list)")


def test_python_detection_def():
    assert _looks_like_python("def hello():\n    print('hi')\n")


def test_python_detection_pandas_token_pattern():
    code = "data = {'Year': [2020]}\ndf = pd.DataFrame(data)\nprint(df)"
    assert _looks_like_python(code)


def test_prose_not_detected_as_python():
    assert not _looks_like_python("Tässä on Konecranesin liikevaihto vuosittain.")


def test_short_string_not_detected():
    assert not _looks_like_python("Hello!")


def test_empty_not_detected():
    assert not _looks_like_python("")
    assert not _looks_like_python("   \n  ")


# ---------------------------------------------------------------------------
# Image-ref stripping
# ---------------------------------------------------------------------------

def test_image_refs_stripped():
    text = "Tässä kuvaaja: ![chart](revenue_comparison.png) Loppu."
    cleaned = _strip_dangling_image_refs(text)
    assert "![chart]" not in cleaned
    assert "Tässä kuvaaja:" in cleaned
    assert "Loppu." in cleaned


def test_no_image_refs_passes_through():
    text = "Plain text without images."
    assert _strip_dangling_image_refs(text) == text


# ---------------------------------------------------------------------------
# extract_parts integration
# ---------------------------------------------------------------------------

def test_text_only(tmp_path):
    response = FakeResponse(messages=[FakeMessage(contents=[
        FakeContent(type="text", text="Sammon P/E on 12,53."),
    ])])
    md, images = extract_parts(response, run_dir=tmp_path, agent_label="quant")
    assert md == "Sammon P/E on 12,53."
    assert images == []


def test_python_text_wrapped_as_code_block(tmp_path):
    code = "import pandas as pd\ndata = {'a': [1, 2]}\nprint(data)"
    response = FakeResponse(messages=[FakeMessage(contents=[
        FakeContent(type="text", text=code),
    ])])
    md, _ = extract_parts(response, run_dir=tmp_path, agent_label="quant")
    assert md.startswith("```python\n")
    assert md.rstrip().endswith("```")
    assert "import pandas" in md


def test_mixed_prose_and_code(tmp_path):
    """Multiple text chunks: prose then code then prose."""
    response = FakeResponse(messages=[FakeMessage(contents=[
        FakeContent(type="text", text="Lasken CAGR:n:"),
        FakeContent(type="text", text="import math\ncagr = (b/a) ** (1/n) - 1\nprint(cagr)"),
        FakeContent(type="text", text="Tulos: 7,4 %."),
    ])])
    md, _ = extract_parts(response, run_dir=tmp_path, agent_label="quant")
    assert "Lasken CAGR:n:" in md
    assert "```python\nimport math" in md
    assert "Tulos: 7,4 %." in md


def test_function_calls_skipped(tmp_path):
    """MCP function-call/result parts shouldn't appear in the rendered output."""
    response = FakeResponse(messages=[FakeMessage(contents=[
        FakeContent(type="function_call", text=None),
        FakeContent(type="function_result", text="this should not appear"),
        FakeContent(type="text", text="Final answer."),
    ])])
    md, _ = extract_parts(response, run_dir=tmp_path, agent_label="quant")
    assert md == "Final answer."
    assert "should not appear" not in md


def test_dangling_image_ref_stripped(tmp_path):
    response = FakeResponse(messages=[FakeMessage(contents=[
        FakeContent(type="text", text="Tässä: ![chart](revenue.png) and ![](other.png)"),
    ])])
    md, images = extract_parts(response, run_dir=tmp_path, agent_label="quant")
    assert images == []
    assert "![chart]" not in md
    assert "![" not in md


def test_fallback_when_no_messages(tmp_path):
    @dataclass
    class WeirdResponse:
        text: str = "fallback content"

    md, images = extract_parts(WeirdResponse(), run_dir=tmp_path, agent_label="quant")
    assert md == "fallback content"
    assert images == []


def test_empty_response_returns_empty_text(tmp_path):
    @dataclass
    class EmptyResponse:
        messages: list = field(default_factory=list)
        text: str = ""

    md, _ = extract_parts(EmptyResponse(), run_dir=tmp_path, agent_label="quant")
    assert md == ""
