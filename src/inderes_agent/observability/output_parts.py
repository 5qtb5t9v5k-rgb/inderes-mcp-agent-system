"""Extract structured rendering from an `AgentResponse`.

`agent_framework_gemini` collapses Gemini's distinct response parts into plain
`Content.from_text(...)` objects:
  - `executable_code` (the Python the model wanted to run) → text
  - `code_execution_result.output` (the stdout)            → text
  - `inline_data` (matplotlib figures etc.)                → DROPPED entirely

Each text Content carries a `raw_representation` that *should* let us tell
these apart, but in practice the field is sometimes stripped or unavailable
through the agent loop. So we use a content-based heuristic: text that looks
like Python source (starts with `import`/`from`/`def`/`class` or contains
distinctive Python tokens like `print(`, `plt.`, `pd.`) gets wrapped in
` ```python ``` `. Anything else passes through as-is.

We also strip stray `![alt](filename)` markdown that the agent sometimes
writes referencing files it `savefig()`'d into the sandbox FS — those would
render as broken icons in the UI. Inline_data (real chart capture) is not
supported by `agent_framework_gemini`, so charts are not extracted in this
build; that's documented as a known limitation.

In addition to text, we also extract **tool-call traces** (BACKLOG #10
provenance threading): every `function_call` / `function_result` Content
in the response is captured as a `ToolCallTrace` so synthesis and the UI
can compare what the agent claimed against what the tool actually returned.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Heuristic patterns for detecting Python source in a text chunk.
_PY_LEAD_RE = re.compile(r"^\s*(import\s+\w+|from\s+\w[\w.]*\s+import\b|def\s+\w+\s*\(|class\s+\w+\s*[:(])")
_PY_TOKEN_RES = [
    re.compile(r"\bplt\.[a-zA-Z_]+\("),
    re.compile(r"\bpd\.(DataFrame|read_[a-zA-Z_]+|Series)\b"),
    re.compile(r"\bnp\.[a-zA-Z_]+\("),
    re.compile(r"^\s*print\(", re.MULTILINE),
    re.compile(r"^\s*\w+\s*=\s*\{", re.MULTILINE),  # dict assignment
    re.compile(r"^\s*for\s+\w+\s+in\s+", re.MULTILINE),
    re.compile(r"^\s*if\s+\w+", re.MULTILINE),
]

_IMG_REF_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)\s*")


@dataclass
class ToolCallTrace:
    """A single tool invocation within a subagent's run.

    Captured for BACKLOG #10 (provenance threading): synthesis sees the
    structured tool data alongside the agent's text summary, so it can
    diff agent claims against what the tool actually returned.

    `result_text` is the full text result from the tool (already
    JSON-serialized in most MCP cases). `result_summary` is a compact
    human-readable summary used in synthesis prompts when the full
    result would blow the context window.
    """
    name: str
    arguments: Any  # dict or str — depends on the model's serialization choice
    result_text: str = ""
    item_count: int | None = None
    item_names: list[str] = field(default_factory=list)
    error: str | None = None
    call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def result_summary(self, max_items: int = 30) -> str:
        """Compact one-line summary suitable for embedding in synthesis prompts."""
        if self.error:
            return f"ERROR: {self.error[:200]}"
        if self.item_count is not None:
            preview = ", ".join(self.item_names[:max_items])
            if len(self.item_names) > max_items:
                preview += f", … (+{len(self.item_names) - max_items} more)"
            return f"{self.item_count} items returned: [{preview}]"
        if self.result_text:
            head = self.result_text[:300].replace("\n", " ")
            return f"text result ({len(self.result_text)} chars): {head}…" if len(self.result_text) > 300 else head
        return "(empty result)"


def _looks_like_python(text: str) -> bool:
    """Heuristic — does this text chunk look like Python source code?"""
    if not text or not text.strip():
        return False
    if _PY_LEAD_RE.match(text.lstrip()):
        return True
    matches = sum(1 for r in _PY_TOKEN_RES if r.search(text))
    return matches >= 2


def _strip_dangling_image_refs(text: str) -> str:
    """Remove `![alt](path)` references from text — image capture isn't supported."""
    return _IMG_REF_RE.sub("", text)


def _parse_arguments(args: Any) -> Any:
    """Normalize tool arguments into a JSON-serializable form.

    Gemini sometimes emits args as a string of JSON, sometimes as a dict.
    We try to parse JSON strings, otherwise pass through.
    """
    if isinstance(args, str):
        try:
            return json.loads(args)
        except (json.JSONDecodeError, TypeError):
            return args
    return args


def _summarize_result(result_text: str) -> tuple[int | None, list[str]]:
    """Try to extract item count and entity names from a JSON result.

    Most Inderes MCP tools return shape `{"items": [{...}], "pageInfo": {...}}`.
    We pull `companyName` from each item if present. This gives synthesis
    explicit ground-truth entity names to diff against the agent's claims.

    Returns (item_count, item_names). Both None/empty if we can't parse.
    """
    if not result_text:
        return None, []
    try:
        parsed = json.loads(result_text)
    except (json.JSONDecodeError, TypeError):
        return None, []

    items = None
    if isinstance(parsed, dict):
        for key in ("items", "results", "data"):
            if isinstance(parsed.get(key), list):
                items = parsed[key]
                break
    elif isinstance(parsed, list):
        items = parsed

    if items is None:
        return None, []

    names: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        # Common name-like fields across Inderes MCP tool schemas
        for key in ("companyName", "name", "title", "topicTitle", "personName"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                names.append(value.strip())
                break
    return len(items), names


def _collect_tool_calls(messages: Any) -> list[ToolCallTrace]:
    """Walk messages and pair function_call → function_result content items by call_id.

    Tool calls and their results land in separate Content items inside the
    response.messages stream, linked via call_id. We pair them and emit one
    ToolCallTrace per call, in order.
    """
    calls: dict[str, dict[str, Any]] = {}
    order: list[str] = []  # preserve call_id insertion order for stable output

    for msg in messages or []:
        for content in (getattr(msg, "contents", None) or []):
            ctype = getattr(content, "type", None)
            if ctype == "function_call":
                call_id = getattr(content, "call_id", None) or f"_anon_{len(order)}"
                if call_id not in calls:
                    calls[call_id] = {}
                    order.append(call_id)
                calls[call_id]["name"] = getattr(content, "name", None) or "<unknown>"
                calls[call_id]["arguments"] = _parse_arguments(getattr(content, "arguments", None))
            elif ctype == "function_result":
                call_id = getattr(content, "call_id", None) or f"_anon_{len(order)}"
                if call_id not in calls:
                    calls[call_id] = {}
                    order.append(call_id)
                result_text = getattr(content, "result", None) or ""
                if not isinstance(result_text, str):
                    try:
                        result_text = json.dumps(result_text, default=str)
                    except (TypeError, ValueError):
                        result_text = str(result_text)
                calls[call_id]["result_text"] = result_text
                calls[call_id]["error"] = getattr(content, "exception", None)

    traces: list[ToolCallTrace] = []
    for call_id in order:
        d = calls[call_id]
        result_text = d.get("result_text", "")
        item_count, item_names = _summarize_result(result_text) if result_text else (None, [])
        traces.append(
            ToolCallTrace(
                name=d.get("name", "<unknown>"),
                arguments=d.get("arguments"),
                result_text=result_text,
                item_count=item_count,
                item_names=item_names,
                error=d.get("error"),
                call_id=call_id if not call_id.startswith("_anon_") else None,
            )
        )
    return traces


def extract_parts(
    response: Any,
    *,
    run_dir: Path,
    agent_label: str,  # kept for API compat; unused now that images aren't extracted
) -> tuple[str, list[str], list[ToolCallTrace]]:
    """Walk the response's content parts and return (markdown, image_paths, tool_calls).

    Returns:
      - markdown: text response with Python source wrapped in ```python``` blocks
      - image_paths: empty list (image extraction not supported in this build)
      - tool_calls: list of ToolCallTrace, one per function_call/result pair found
    """
    messages = getattr(response, "messages", None)
    if messages is None:
        return _strip_dangling_image_refs(_fallback_text(response)), [], []

    tool_calls = _collect_tool_calls(messages)

    rendered: list[str] = []

    for msg in messages:
        for content in (getattr(msg, "contents", None) or []):
            ctype = getattr(content, "type", None)

            if ctype == "text":
                text = getattr(content, "text", None) or ""
                if not text.strip():
                    continue
                if _looks_like_python(text):
                    rendered.append(f"```python\n{text.rstrip()}\n```")
                else:
                    rendered.append(text)

            # function_call / function_result are captured separately into
            # tool_calls; not rendered into the user-facing text.

    md = "\n\n".join(s for s in rendered if s).strip()
    if not md:
        md = _fallback_text(response)

    md = _strip_dangling_image_refs(md)
    return md, [], tool_calls


def _fallback_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text is not None:
        return text
    return str(response)
