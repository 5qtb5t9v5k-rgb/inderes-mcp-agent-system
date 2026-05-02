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
"""

from __future__ import annotations

import re
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


def _looks_like_python(text: str) -> bool:
    """Heuristic — does this text chunk look like Python source code?"""
    if not text or not text.strip():
        return False
    if _PY_LEAD_RE.match(text.lstrip()):
        return True
    matches = sum(1 for r in _PY_TOKEN_RES if r.search(text))
    return matches >= 2


def _strip_dangling_image_refs(text: str) -> str:
    """Remove `![alt](path)` references from text — image capture isn't supported.

    Inline_data parts are dropped by agent_framework_gemini, so any image
    references the agent writes point to sandbox-only files. Strip them so
    the UI doesn't show broken-icon thumbnails.
    """
    return _IMG_REF_RE.sub("", text)


def extract_parts(
    response: Any,
    *,
    run_dir: Path,
    agent_label: str,  # kept for API compat; unused now that images aren't extracted
) -> tuple[str, list[str]]:
    """Walk the response's content parts and return (markdown, image_paths).

    Returns a markdown string with Python source wrapped in ```python``` blocks,
    and an empty image_paths list (image extraction is not supported in this
    build — see module docstring).
    """
    messages = getattr(response, "messages", None)
    if messages is None:
        return _strip_dangling_image_refs(_fallback_text(response)), []

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

            # function_call / function_result and any non-text parts are
            # intentionally skipped — already in console.log; not user-facing.

    md = "\n\n".join(s for s in rendered if s).strip()
    if not md:
        md = _fallback_text(response)

    md = _strip_dangling_image_refs(md)
    return md, []


def _fallback_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text is not None:
        return text
    return str(response)
