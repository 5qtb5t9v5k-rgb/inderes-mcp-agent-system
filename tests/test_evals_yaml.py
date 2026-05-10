"""Structural validation of evals/golden.yaml.

These run as part of `pytest` (no LLM, no SQLite, no network) so they
gate every push the same way the rest of the suite does. They catch
the kind of yaml-side mistakes that would otherwise only surface
during a live `evals/runner.py` invocation:

  - golden.yaml parses as YAML
  - each case has the required fields
  - case IDs are unique (the indexer's filter assumes uniqueness)
  - each hard assertion is a syntactically valid Python expression
    that can be eval'd against the context namespace exposed by
    `evals/runner.py:_eval_context`
  - soft assertions reference identifiable rubric criteria

Why this matters: a typo like `'Sampo' en synthesis` (en vs in) won't
fail at YAML-load time but will explode the moment the runner tries
to eval() it — and right now that's only caught when an operator
runs the suite by hand. CI is the right place to gate this.

Out of scope: the actual *truth* of any assertion (whether
"comparison routing must include research" is the right rule). That's
a design call captured in the case rationale; testing it requires a
live run.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "evals" / "golden.yaml"

# ---------------------------------------------------------------------------
# Names that hard assertions in golden.yaml are allowed to reference.
#
# This must stay in sync with `_eval_context` in evals/runner.py. If a new
# field is added there, add it here too — the test will fail otherwise and
# point at the missing entry, which is the desired feedback loop.
# ---------------------------------------------------------------------------

ALLOWED_NAMES: frozenset[str] = frozenset({
    # _Bag-wrapped namespaces
    "routing",
    # Top-level scalar / collection context
    "duration_s",
    "subagent_count",
    "subagent_errors",
    "agreements_count",
    "conflicts_count",
    "isolated_count",
    "paattely_kind",
    "has_synthesis",
    "has_warning_phrase",
    "synthesis",
    "tc_count_per_agent",
    # Multi-run cases (case_005 reproducibility) expose `runs` as a list
    "runs",
    # Stdlib helpers passed into the eval globals
    "median",
    "len",
    "all",
    "any",
    "max",
    "min",
    "sum",
    # Builtins the parser exposes implicitly
    "True",
    "False",
    "None",
})


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def golden_data() -> dict:
    assert GOLDEN_PATH.exists(), f"golden.yaml missing at {GOLDEN_PATH}"
    return yaml.safe_load(GOLDEN_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Top-level structure
# ---------------------------------------------------------------------------


def test_golden_yaml_parses(golden_data):
    """yaml.safe_load returns a dict with `cases` key."""
    assert isinstance(golden_data, dict)
    assert "cases" in golden_data
    assert isinstance(golden_data["cases"], list)
    assert len(golden_data["cases"]) > 0, "no cases defined"


def test_case_ids_are_unique(golden_data):
    """Indexer filters on case_id; duplicates would silently shadow."""
    ids = [c["id"] for c in golden_data["cases"]]
    seen: dict[str, int] = {}
    for i in ids:
        seen[i] = seen.get(i, 0) + 1
    duplicates = {i: n for i, n in seen.items() if n > 1}
    assert not duplicates, f"duplicate case IDs: {duplicates}"


def test_each_case_has_required_fields(golden_data):
    """Every case needs id + query_match + at least one of hard/soft."""
    missing: list[str] = []
    for case in golden_data["cases"]:
        cid = case.get("id", "<no-id>")
        if "id" not in case:
            missing.append("<unnamed>: missing 'id'")
        if "query_match" not in case:
            missing.append(f"{cid}: missing 'query_match'")
        if not case.get("hard") and not case.get("soft"):
            missing.append(f"{cid}: must have at least one of hard/soft")
    assert not missing, "field issues: " + "; ".join(missing)


def test_each_case_has_rationale(golden_data):
    """Rationale is documentation but it's a strong norm — flag if missing."""
    missing = [
        c["id"] for c in golden_data["cases"]
        if not (c.get("rationale") or "").strip()
    ]
    assert not missing, (
        f"cases missing rationale: {missing}. "
        "Rationale is required so a future reader knows WHY the case exists."
    )


# ---------------------------------------------------------------------------
# Hard assertions: syntactic validity
# ---------------------------------------------------------------------------


def _names_referenced(expr: str) -> set[str]:
    """Pull all FREE identifier names out of a Python expression via AST.

    "Free" = not bound by a comprehension target. Without this, an
    expression like `all(r.has_synthesis for r in runs)` would flag `r`
    as an unknown name even though it's locally bound by the `for r in
    runs` clause.
    """
    tree = ast.parse(expr, mode="eval")

    # Collect names introduced by comprehension targets (these are local).
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.GeneratorExp, ast.ListComp, ast.SetComp, ast.DictComp)):
            for gen in node.generators:
                # `for x in iter` — x is ast.Name; `for x, y in iter` — Tuple of Names.
                target = gen.target
                if isinstance(target, ast.Name):
                    bound.add(target.id)
                elif isinstance(target, ast.Tuple):
                    for elt in target.elts:
                        if isinstance(elt, ast.Name):
                            bound.add(elt.id)

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id not in bound:
                names.add(node.id)
        elif isinstance(node, ast.Attribute):
            # routing.domains -> we want the root, "routing"
            cur = node
            while isinstance(cur, ast.Attribute):
                cur = cur.value
            if isinstance(cur, ast.Name) and cur.id not in bound:
                names.add(cur.id)
    return names


def test_hard_assertions_parse_as_python_expressions(golden_data):
    """Every hard string must compile as a Python eval-able expression.

    Catches typos like `routing.domain` (singular) → SyntaxError-free
    but fails at runtime; we don't catch those here, but we do catch
    actual SyntaxErrors (unbalanced brackets, missing operators, etc.)
    that would crash the runner immediately.
    """
    failures: list[str] = []
    for case in golden_data["cases"]:
        cid = case["id"]
        for i, expr in enumerate(case.get("hard") or []):
            try:
                ast.parse(expr, mode="eval")
            except SyntaxError as e:
                failures.append(f"{cid} hard[{i}]: {expr!r} → SyntaxError: {e}")
    assert not failures, "\n".join(failures)


def test_hard_assertions_reference_only_known_names(golden_data):
    """Every name in a hard assertion must be in `_eval_context`'s namespace.

    Catches typos like `routing.domain` (singular), `tool_calls` (the
    key is `tc_count_per_agent`), `paatelly_kind` (Päättely typos), etc.
    These would not raise SyntaxError but would NameError at eval time.

    If you add a new context field in `evals/runner.py:_eval_context`,
    add the same name to ALLOWED_NAMES at the top of this file.
    """
    unknown: list[str] = []
    for case in golden_data["cases"]:
        cid = case["id"]
        for i, expr in enumerate(case.get("hard") or []):
            referenced = _names_referenced(expr)
            extra = referenced - ALLOWED_NAMES
            if extra:
                unknown.append(
                    f"{cid} hard[{i}]: {expr!r} references unknown name(s) {extra}. "
                    "If this is a real new field, add it to evals/runner.py:_eval_context "
                    "AND to ALLOWED_NAMES in this test."
                )
    assert not unknown, "\n".join(unknown)


# ---------------------------------------------------------------------------
# Soft assertions: structure
# ---------------------------------------------------------------------------


def test_soft_assertions_are_dicts_of_strings(golden_data):
    """soft is a {criterion_name: rubric_text} mapping. Catches yaml shape drift."""
    bad: list[str] = []
    for case in golden_data["cases"]:
        cid = case["id"]
        soft = case.get("soft")
        if soft is None:
            continue
        if not isinstance(soft, dict):
            bad.append(f"{cid}: soft is not a dict: {type(soft).__name__}")
            continue
        for k, v in soft.items():
            if not isinstance(k, str):
                bad.append(f"{cid} soft key {k!r}: not a string")
            if not isinstance(v, str) or not v.strip():
                bad.append(f"{cid} soft[{k!r}]: rubric text is empty or non-string")
    assert not bad, "\n".join(bad)


def test_soft_criterion_keys_are_snake_case(golden_data):
    """Convention check: soft criterion keys are snake_case.

    The judge prompt embeds these into the JSON output schema. Mixed-case
    or hyphenated keys break the LLM judge's response shape.
    """
    bad: list[str] = []
    import re
    snake = re.compile(r"^[a-z][a-z0-9_]*$")
    for case in golden_data["cases"]:
        cid = case["id"]
        for k in (case.get("soft") or {}).keys():
            if not snake.match(k):
                bad.append(f"{cid} soft criterion {k!r} is not snake_case")
    assert not bad, "\n".join(bad)


# ---------------------------------------------------------------------------
# Sanity: the cases we expect to exist actually exist
# ---------------------------------------------------------------------------


def test_known_cases_present(golden_data):
    """Tier 1 baseline cases (case_001 .. case_006) must remain in the suite.

    They map to specific findings in `evals/findings_2026-05-09.md`. If
    one is removed, that finding is no longer being regression-tested,
    which is a design decision worth surfacing in PR review — not
    something that should slip in via a yaml edit.
    """
    ids = {c["id"] for c in golden_data["cases"]}
    required = {
        "case_001_comparison_routing",
        "case_002_paattely_schema",
        "case_003_conflict_coverage",
        "case_004_search_robustness",
        "case_005_reproducibility",
        "case_006_latency_cap",
        # case_007 + case_008 added later, post-baseline; not "required" but
        # tracked here so the test file flags any removal:
        "case_007_valuation_tila_c_renders",
        "case_008_multi_company_valuation_comparison",
    }
    missing = required - ids
    assert not missing, (
        f"required eval cases removed from golden.yaml: {missing}. "
        "If intentional, update this test and reference the BACKLOG entry "
        "explaining why."
    )
