"""Lead synthesis: feed subagent outputs to aino-lead, get a final answer.

A pre-synthesis pass (`detect_conflicts`) runs a separate LLM call that
reads all subagent outputs and emits structured JSON describing
agreements, conflicts, and isolated single-source claims. The lead then
sees that structured map as additional context — making the emergent
self-correction observed in Case 003 (evals/known-cases.md) explicit
and loggable rather than implicit in the lead's training-data priors.

This is the BACKLOG #1 plan-then-execute extension.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from ..agents import build_conflict_detector_agent, build_lead_agent
from ..valuation import (
    Valuation,
    ValuationAgentOutput,
    ValuationAgentSkipped,
    ValuationParseError,
    parse as parse_valuation_agent,
    value_stock,
)
from .router import Domain
from .workflows import WorkflowResult

log = logging.getLogger(__name__)


@dataclass
class ConflictReport:
    """Structured map produced by the conflict-detector pass.

    `raw` is the model's literal JSON string (preserved for the run log,
    even when it failed to parse). `parsed` is the dict if parsing
    succeeded, else None.
    """
    raw: str = ""
    parsed: dict[str, Any] | None = None
    model_used: str = "skipped"
    skipped_reason: str | None = None
    error: str | None = None
    duration_seconds: float = 0.0

    @property
    def has_signal(self) -> bool:
        if not self.parsed:
            return False
        return any(
            self.parsed.get(k)
            for k in ("agreements", "conflicts", "isolated_claims")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_used": self.model_used,
            "skipped_reason": self.skipped_reason,
            "error": self.error,
            "duration_seconds": round(self.duration_seconds, 3),
            "raw": self.raw,
            "parsed": self.parsed,
        }


def _format_subagent_results(result: WorkflowResult) -> str:
    """Render subagent outputs as a structured prompt for the lead."""
    lines: list[str] = []
    for i, sr in enumerate(result.subagent_results, 1):
        label = sr.domain.value
        if sr.company:
            label += f" — {sr.company}"
        header = f"### {i}. {label}  [model: {sr.model_used}]"
        lines.append(header)
        if sr.error:
            lines.append(f"_subagent error: {sr.error}_")
        else:
            lines.append(sr.text or "_(empty response)_")
        lines.append("")
    return "\n".join(lines)


def _format_tool_call_trace(result: WorkflowResult) -> str:
    """Render every subagent's tool calls as ground-truth context for synthesis.

    BACKLOG #10 provenance threading: lead synthesis needs to see what tools
    actually returned, not just the subagent's text summary, so it can:
      - drop hallucinated entities (in agent text but not in tool output)
      - surface omitted-but-relevant entities (in tool output but not in agent text)
      - cross-check numbers and attributions against raw data
    """
    lines: list[str] = []
    for i, sr in enumerate(result.subagent_results, 1):
        if not sr.tool_calls:
            continue
        label = sr.domain.value
        if sr.company:
            label += f" — {sr.company}"
        lines.append(f"### Subagent {i} ({label}) — {len(sr.tool_calls)} tool call(s):")
        for tc in sr.tool_calls:
            args_repr = json.dumps(tc.arguments, ensure_ascii=False) if tc.arguments is not None else "{}"
            if len(args_repr) > 300:
                args_repr = args_repr[:300] + "…"
            lines.append(f"- `{tc.name}` args={args_repr}")
            lines.append(f"    → {tc.result_summary(max_items=30)}")
        lines.append("")
    if not lines:
        return "_no tool calls captured for any subagent_"
    return "\n".join(lines)


def _strip_json_fences(text: str) -> str:
    """Defensively strip ```json fences in case the model added them despite the prompt."""
    s = text.strip()
    if s.startswith("```"):
        # drop opening fence (```json or just ```) and trailing ```
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


async def detect_conflicts(
    workflow_result: WorkflowResult,
    *,
    deep: bool = False,
) -> ConflictReport:
    """Pre-synthesis pass. Skips automatically when there's nothing to compare.

    ``deep=True`` upgrades the detector's model to Pro — used by the
    "Tarkka kaikki" tier so conflict resolution gets the same reasoning
    quality as subagents.
    """
    non_error = [sr for sr in workflow_result.subagent_results if not sr.error]
    if len(non_error) < 2:
        return ConflictReport(
            skipped_reason=f"only {len(non_error)} non-error subagent(s); nothing to compare",
        )

    subagents_block = _format_subagent_results(workflow_result)
    prompt = f"""\
SUBAGENT OUTPUTS:
{subagents_block}

Now produce the conflict report as STRICT JSON per your instructions.
"""

    t_start = time.time()
    try:
        async with build_conflict_detector_agent(deep=deep) as detector:
            result = await detector.run(prompt)
            raw = result.text if hasattr(result, "text") else str(result)
            model_used = getattr(detector.client, "last_used_model", "unknown")
    except Exception as exc:
        log.warning("conflict-detector call failed: %s", exc)
        return ConflictReport(error=str(exc)[:500], duration_seconds=time.time() - t_start)

    duration = time.time() - t_start

    cleaned = _strip_json_fences(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log.warning("conflict-detector returned non-JSON output: %s", exc)
        return ConflictReport(
            raw=raw, model_used=model_used,
            error=f"JSON parse failed: {exc}",
            duration_seconds=duration,
        )

    return ConflictReport(raw=raw, parsed=parsed, model_used=model_used, duration_seconds=duration)


def _format_conflict_block(report: ConflictReport) -> str:
    """Render the conflict report as a prompt section for the lead."""
    if not report.has_signal:
        if report.skipped_reason:
            return f"_conflict-detector skipped: {report.skipped_reason}_"
        if report.error:
            return f"_conflict-detector errored: {report.error}_"
        return "_conflict-detector found no notable agreements, conflicts, or isolated claims._"
    return json.dumps(report.parsed, ensure_ascii=False, indent=2)


@dataclass
class ValuationRecord:
    """One company's alternative-valuation result.

    Holds the agent's parsed output + the engine's deterministic computation,
    so run_log.write_run can persist both the agent's parameter rationale
    and the resulting fair value to ``valuation.json``.
    """
    company: str
    agent_output: ValuationAgentOutput | None = None
    valuation: Valuation | None = None
    skipped: ValuationAgentSkipped | None = None
    parse_error: str | None = None
    raw_text: str | None = None  # for forensic logging when parse fails


@dataclass
class SynthesisTrace:
    """Per-stage timings + conflict report + parsed Päättely from one synthesize() call.

    `paattely` is the parsed JSON the LEAD emits as its visible-reasoning
    block (BACKLOG #9). Schema: `{disagree, resolution, uncertain, skipped}`,
    each value a string or null. None when LEAD did not emit a parseable
    block. The UI renders this as a 2×2 slot grid.

    `paattely_raw` is the raw text matched (block-with-fences) for forensics
    even when JSON parse fails.

    `valuations` is the list of per-company alternative-valuation records,
    populated only when the user enabled the "Käytä vaihtoehtoista
    arvonmääritystä" toggle and the workflow dispatched VALUATION agents.
    Empty list otherwise.
    """
    conflict_report: ConflictReport
    lead_seconds: float = 0.0
    paattely: dict[str, Any] | None = None
    paattely_raw: str | None = None
    paattely_error: str | None = None
    valuations: list[ValuationRecord] = field(default_factory=list)


# Compiled once. The Päättely block can be EITHER:
#   (a) a fenced JSON object (legacy / structured) — `**🧠 Päättely**\n```json {...}````
#   (b) free prose (current default) — `**🧠 Päättely**\n\n<paragraphs>...\n## next-section`
# We try (a) first because it gives the UI more structure; fall back to (b)
# capturing everything until the next markdown heading or another bold marker
# (📖 Lähteet / 💡 Voisit kysyä myös) or end of text.
# Marker can be **🧠 Päättely**, ## 🧠 Päättely, ### 🧠 Päättely, or just
# 🧠 Päättely on its own line — Flash Lite picks any of these. We anchor
# on a line-start to avoid matching inside other markdown bullets/text.
_PAATTELY_JSON_RE = re.compile(
    r"(?:^|\n)\s*(?:\*\*|#{1,3})?\s*🧠\s*(?:Päättely|Reasoning)\s*(?:\*\*|:)?\s*\n+"
    r"\s*```(?:json)?\s*\n(?P<body>\{.*?\})\s*\n```",
    re.DOTALL | re.IGNORECASE,
)
_PAATTELY_PROSE_RE = re.compile(
    r"(?:^|\n)\s*(?:\*\*|#{1,3})?\s*🧠\s*(?:Päättely|Reasoning)\s*(?:\*\*|:)?\s*\n+"
    r"(?P<body>.+?)"
    r"(?=\n\s*#{1,3}\s|\n\s*\*\*\s*(?:📖|💡)|\Z)",
    re.DOTALL | re.IGNORECASE,
)


def _extract_paattely(text: str) -> tuple[str, str | None, dict[str, Any] | None, str | None]:
    """Pull the **🧠 Päättely** block out of the LEAD's response.

    Returns (cleaned_text, raw_block_or_None, parsed_or_None, error_or_None).
    `parsed` may be:
      - a dict {disagree, resolution, uncertain, skipped} when LEAD emitted
        the structured JSON form (UI renders 2×2 grid); OR
      - a dict {prose: str} when LEAD emitted free prose covering the four
        points (UI renders prose in a styled expander).

    `cleaned_text` has the matched block stripped so the UI doesn't render
    the body twice (once in the answer body, once as the Päättely callout).

    On no match, returns (text, None, None, None).
    """
    # First try the structured JSON form (legacy / preferred when present).
    m = _PAATTELY_JSON_RE.search(text)
    if m:
        raw_full = m.group(0)
        body = m.group("body")
        cleaned = (text[: m.start()] + text[m.end() :]).rstrip() + "\n"
        try:
            parsed = json.loads(body)
            if not isinstance(parsed, dict):
                # JSON valid but not an object — fall through to prose.
                pass
            else:
                normalized = {k: parsed.get(k) for k in ("disagree", "resolution", "uncertain", "skipped")}
                return cleaned, raw_full, normalized, None
        except json.JSONDecodeError:
            # Treat as prose — fall through.
            pass

    # Prose form — capture body until next section.
    m2 = _PAATTELY_PROSE_RE.search(text)
    if not m2:
        return text, None, None, None

    raw_full = m2.group(0)
    body = m2.group("body").strip()
    if not body:
        cleaned_empty = (text[: m2.start()] + text[m2.end() :]).rstrip() + "\n"
        return cleaned_empty, raw_full, None, "päättely block was empty"

    # Defensive cap: take at most the first 4 double-newline-separated
    # paragraphs from the captured body. The prompt asks for exactly 4
    # paragraphs (one per slot: erimielisyys / ratkaisu / epävarma /
    # jätin tekemättä). When LEAD forgets to start the answer body with
    # `## Yhteenveto` heading, the prose regex would otherwise suck the
    # whole answer into päättely. Strict cap at 4 keeps päättely focused
    # and pushes the rest back to the answer body.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    paragraphs_capped = paragraphs[:4]
    capped_body = "\n\n".join(paragraphs_capped)

    # Compute what we actually consumed from the original text — only the
    # capped portion, not the entire greedy match. The rest of the greedy
    # match goes back to the answer body so render_lead_answer renders it.
    if capped_body == body:
        consumed_end = m2.end()
    else:
        # Find where the capped body ends in the original text.
        body_start_in_text = m2.start() + (m2.group(0).find(body))
        consumed_end = body_start_in_text + len(capped_body)

    cleaned = (text[: m2.start()] + text[consumed_end:]).rstrip() + "\n"

    # When the prose conforms to the prompt's 4-paragraph spec, lift it
    # into the structured slot dict the UI's 2×2 grid renderer expects.
    # Eval baseline (case_002) caught this: 0 of 183 historical runs
    # produced structured output via JSON, but 55 did emit well-formed
    # 4-paragraph prose. Mapping prose → slots in-parser gives the UI
    # the structure it always expected, without changing the LEAD
    # prompt or losing the more readable prose form for partial cases.
    #
    # Order matches the prompt at agents/prompts/lead.md §31-53:
    #   ¶1 → disagree   (mistä subagentit olivat eri mieltä)
    #   ¶2 → resolution (miten ratkaisin)
    #   ¶3 → uncertain  (mitkä väitteet ovat epävarmoja)
    #   ¶4 → skipped    (mitä jätin tekemättä)
    if len(paragraphs_capped) == 4:
        structured = {
            "disagree":   paragraphs_capped[0],
            "resolution": paragraphs_capped[1],
            "uncertain":  paragraphs_capped[2],
            "skipped":    paragraphs_capped[3],
        }
        return cleaned, raw_full, structured, None

    # Fewer than 4 paragraphs → prose fallback (UI renders as styled
    # block). Better than forcing slots with empty values.
    return cleaned, raw_full, {"prose": capped_body}, None


def _process_valuation_subagents(
    workflow_result: WorkflowResult,
) -> list[ValuationRecord]:
    """Parse each VALUATION subagent's JSON output and run the engine.

    For per-company comparisons we get one VALUATION subagent per company;
    for single-company queries we get one. Each result either:
      - parses cleanly + engine returns a Valuation → ValuationRecord with both
      - parses to ValuationAgentSkipped → record carries the skip reason
      - fails to parse → record carries the error + raw text for forensics

    Logged warnings rather than raised exceptions: a malformed VALUATION
    output should not break the rest of the synthesis pipeline.
    """
    records: list[ValuationRecord] = []
    for sr in workflow_result.subagent_results:
        if sr.domain != Domain.VALUATION:
            continue
        # Default company label: subagent's per-company tag for fanout, or
        # "<unknown>" until the parser succeeds and we can use parsed.company.
        # We deliberately do NOT fall back to sr.text[:80] — that pulls the
        # **Ajatus:** line into the run-log's company field.
        company = sr.company or "<unknown>"
        if sr.error:
            records.append(ValuationRecord(
                company=company,
                parse_error=f"agent error before output: {sr.error}",
                raw_text=sr.text,
            ))
            continue

        # ── Tool-call guard: reject hallucinated outputs at the boundary ──
        # The valuation agent's whole job is to fetch data from MCP and emit
        # JSON. Without ≥1 get-fundamentals call there is no MCP-sourced data
        # in the output — by definition the JSON is invented. We saw this in
        # run 20260508-205057-769 ("entäs jos roe olisi 13%"): Flash Lite
        # decided the prior turn's context was "enough" and emitted a fully
        # hallucinated bundle (wrong company_id COMPANY:345 instead of 382,
        # invented price 12.85€ vs actual 16.09€, invented ROE history).
        #
        # Engine math is deterministic but garbage-in → garbage-out: the
        # +18.2% safety margin shown to the user was the visible artifact of
        # a 100% fabricated input price. Catching this BEFORE parser.parse()
        # routes the run cleanly into Tila B (LEAD shows the honest
        # "valuation skipped" message instead of fabricated numbers).
        #
        # Why count get-fundamentals specifically (not search-companies):
        # search-companies returns only IDs, not the BVPS/ROE/price needed.
        # An agent that did only search-companies still couldn't produce a
        # real valuation. get-fundamentals is the load-bearing call.
        fundamentals_calls = sum(
            1 for tc in (sr.tool_calls or [])
            if getattr(tc, "name", "") == "get-fundamentals"
        )
        if fundamentals_calls == 0:
            log.warning(
                "valuation tool-call guard rejected %s: 0 get-fundamentals calls "
                "(agent skipped MCP — output is hallucinated)",
                company,
            )
            records.append(ValuationRecord(
                company=company,
                parse_error=(
                    "agentti ei tehnyt yhtään get-fundamentals-kutsua — "
                    "output ei perustu MCP-dataan, todennäköisesti hallusinoitu"
                ),
                raw_text=sr.text,
            ))
            continue

        try:
            parsed = parse_valuation_agent(sr.text)
        except ValuationParseError as exc:
            log.warning("valuation-parser failed for %s: %s", company, exc)
            records.append(ValuationRecord(
                company=company,
                parse_error=str(exc),
                raw_text=exc.raw_text,
            ))
            continue

        if isinstance(parsed, ValuationAgentSkipped):
            records.append(ValuationRecord(
                company=parsed.company,  # use parser's company name once we have it
                skipped=parsed,
                raw_text=sr.text,
            ))
            continue

        # Happy path: agent emitted clean JSON → run the deterministic engine.
        # Use parsed.company once available — it's the canonical name from
        # the structured output, free of "**Ajatus:**" leakage.
        company = parsed.company
        try:
            valuation = value_stock(**parsed.to_engine_kwargs())
        except ValueError as exc:
            log.warning("valuation-engine rejected %s: %s", company, exc)
            records.append(ValuationRecord(
                company=company,
                agent_output=parsed,
                parse_error=f"engine validation failed: {exc}",
                raw_text=sr.text,
            ))
            continue

        records.append(ValuationRecord(
            company=company,
            agent_output=parsed,
            valuation=valuation,
            raw_text=sr.text,
        ))

    return records


def _price_date_age_days(price_date: str | None) -> int | None:
    """Compute the age in days of an ISO `price_date` string vs today.

    Accepts:
      - ``None`` / empty / unparseable → returns ``None`` (no warning)
      - ``"YYYY-MM-DD"`` → age in calendar days (today − date)
      - ``"YYYY-MM-DDTHH:MM:SS..."`` (ISO datetime) → date part only

    Used by ``_format_valuation_block`` to flag stale price observations
    in the LEAD prompt block. The valuation agent fetches the price from
    ``get-inderes-estimates``'s ``sharePrice`` + ``transactionDate`` —
    Inderes MCP does not offer intraday or real-time quotes, so the
    freshest price has SOME age. The synthesis layer warns the user
    transparently when that age exceeds 30 days, and warns more strongly
    above 90 days.

    Returns ``None`` (= no warning) when:
      - price_date is missing
      - the string can't be parsed (we don't want a parsing edge case
        to spuriously warn the user; if anything, no warning is the
        safer default)
      - the parsed date is in the future (sanity guard — should never
        happen in practice)
    """
    if not price_date or not isinstance(price_date, str):
        return None
    # Take only the date portion if it's an ISO datetime (Inderes MCP
    # returns transactionDate as e.g. "2026-04-22T16:17:30.000Z").
    date_part = price_date.split("T", 1)[0].strip()
    try:
        observed = date.fromisoformat(date_part)
    except (ValueError, TypeError):
        return None
    today = date.today()
    delta_days = (today - observed).days
    if delta_days < 0:
        # Future date → don't warn, just ignore
        return None
    return delta_days


def _format_valuation_block(records: list[ValuationRecord]) -> str:
    """Render valuation records as a prompt block for the LEAD agent.

    Returns a human-readable structured text — not JSON, because LEAD's
    job is to weave this into prose. For each company shows: chosen
    parameters with rationale, computed fair value with quality label,
    and the comparison-relevant numbers (yli/ali %, entry levels).
    """
    if not records:
        return "_user did not enable alternative valuation; default flow only_"

    lines: list[str] = []
    for rec in records:
        lines.append(f"### {rec.company}")
        if rec.parse_error and not rec.valuation:
            lines.append(f"_valuation skipped: {rec.parse_error}_")
            lines.append("")
            continue
        if rec.skipped:
            lines.append(f"_agent flagged invalid: {'; '.join(rec.skipped.warnings)}_")
            lines.append("")
            continue

        a = rec.agent_output
        v = rec.valuation
        assert a is not None and v is not None  # narrowed by branches above

        lines.append(f"Parametrit: BVPS {a.bvps:.2f} ({a.bvps_date or '?'}), "
                     f"price {a.price:.2f} ({a.price_date or '?'}), "
                     f"ROE {a.roe_used:.1%} ({a.roe_version}), "
                     f"k {a.k:.1%}, g {a.g:.1%}")

        # BVPS-freshness disclaimer — Inderes MCP only exposes yearly
        # taseen tietoja (marketCap, sharesTotal, pb), all NULL at
        # quarterly resolution. So BVPS is always derived from LFY
        # (last fully-reported year) year-end figures — the LATEST
        # PUBLISHED *YEARLY* result available, but quarterly book-value
        # updates post-Q1/Q2/Q3 reports are NOT extractable here. For
        # fast-growing quality companies (e.g. Puuilo with ROE 50 %+),
        # actual BVPS at end of latest quarter may be meaningfully
        # higher than the LFY year-end figure used here. LEAD must
        # surface this when the date is more than ~120 days old.
        bvps_age_days = _price_date_age_days(a.bvps_date)
        if bvps_age_days is not None and bvps_age_days > 120:
            lines.append(
                f"  ℹ️ BVPS:n lähde: tasearvo per {a.bvps_date} "
                f"({bvps_age_days} pv vanha) — yhtiön viimeisin "
                f"vuosittainen tase. Inderes MCP ei tarjoa quarterly-"
                f"tason tase-eriä (Q1/Q2/Q3-päivityksiä ei voi poimia "
                f"automaattisesti). **Mainitse käyttäjälle erityisesti "
                f"laatuyhtiöillä että BVPS perustuu vuodenvaihteen "
                f"tilanteeseen — Q1–Q3-tuloksia ei ole päivitetty "
                f"taseeseen tässä laskennassa.**"
            )

        # Price-freshness disclaimer — ALWAYS surfaced, regardless of age.
        # Inderes MCP empirically does NOT expose any per-stock real-time
        # or even daily price endpoint:
        #   - get-fundamentals yearly = year-end close (locked, 130+ days
        #     stale by mid-year)
        #   - get-fundamentals quarterly = Q-end close (Q4 always null,
        #     in-progress Q always null)
        #   - get-inderes-estimates.sharePrice = analyst's snapshot,
        #     typically 1-3 weeks old (refreshed when analyst writes)
        #   - get-model-portfolio-price daily = portfolio NAV, not per-stock
        #   - list-insider-transactions.price = TX execution price, only
        #     when a transaction has occurred recently (unreliable)
        # Inderes' own website shows live prices via a separate market
        # data feed not exposed via MCP.
        #
        # The price comparison vs fair value is the headline takeaway of
        # the whole valuation. The user MUST always know how recent the
        # price actually is — not just when it crosses an arbitrary
        # threshold. So we emit the freshness info on every Tila-C run
        # and graduate the urgency by age.
        price_age_days = _price_date_age_days(a.price_date)
        if price_age_days is not None:
            if price_age_days > 90:
                tier = "⚠️ KURSSI MAHDOLLISESTI MERKITTÄVÄSTI VANHENTUNUT"
                soften = (
                    "Merkittäviä markkinaliikkeitä on voinut tapahtua. "
                    "Tee käyttäjälle eksplisiittinen muistutus että vertailu "
                    "fair valueen perustuu vanhaan kurssiin."
                )
            elif price_age_days > 30:
                tier = "ℹ️ KURSSI HIEMAN VANHENTUNUT"
                soften = (
                    "Inderes ei ole päivittänyt analyytikkokurssia "
                    "viimeiseen kuukauteen — markkinaliikkeitä on voinut "
                    "tapahtua sen jälkeen."
                )
            else:
                tier = "ℹ️ Kurssin lähde"
                soften = (
                    "Käytännössä tuore (alle kk vanha), mutta ei real-time."
                )
            lines.append(
                f"  {tier}: price_date={a.price_date} ({price_age_days} pv vanha). "
                f"Inderes MCP ei tarjoa real-time-kurssia per yhtiö — tämä on "
                f"Inderesin viimeisin analyytikkohavainto. **Mainitse "
                f"vastauksessa käyttäjälle aina kurssin päivämäärä ja "
                f"kehota tarkistamaan live-hinta inderes.fi:stä tai "
                f"Nasdaqista ennen sijoituspäätöksiä.** {soften}"
            )

        # Multi-line rationales (the agent now produces 2-4 sentence
        # explanations per parameter — surface them in full so LEAD
        # can paraphrase or quote them).
        lines.append(f"  ROE-perustelu: {a.roe_rationale}")
        lines.append(f"  k-perustelu: {a.k_rationale}")
        lines.append(f"  g-perustelu: {a.g_rationale}")
        if a.warnings:
            for w in a.warnings:
                lines.append(f"  ⚠ {w}")

        # Engine output — full set so LEAD can build the perussetti table.
        lines.append(
            f"Engine: quality={v.quality}, fair_value={v.fair_value:.2f} €, "
            f"FV_Gordon={v.fv_gordon:.2f}, FCF_ps={v.fcf_ps:.3f}, "
            f"EPV_pure={v.epv_pure:.2f}, growth_value={v.growth_value_pure:.2f}, "
            f"GM={v.gm:.2f}x, Rock_Bottom={v.rock_bottom:.2f}, P/B={v.pb:.2f}"
        )

        # EPV / growth-pricing decomposition + dual implied reading.
        # Gordon's equation has TWO unknowns (ROE, g) but only ONE constraint
        # (price). A price below model's fair value can be explained by
        # EITHER lower growth OR lower ROE. Surface both so LEAD doesn't
        # pick one dimension as "the" answer.
        implied_g_str = (
            f"{v.implied_g:+.2%}" if v.implied_g is not None
            else "ei laskettavissa (P/B ≈ 1 tai implied_g ≥ k)"
        )
        lines.append(
            f"  EPV-dekompositio: kurssi on {v.market_premium_to_epv_pct:+.1f}% "
            f"yli/alle EPV:n; kasvun osuus nykyhinnasta "
            f"{v.growth_priced_in_share*100:+.1f}%."
        )
        lines.append(
            f"  Markkinan implisiittinen näkemys (DUAALI — sama hinta selittyy "
            f"joko alemmalla g:llä TAI alemmalla ROE:lla):"
        )
        lines.append(
            f"    • Kun ROE pidetään mallin arvossa ({a.roe_used:.1%}): "
            f"implied_g = {implied_g_str} (oma g = {a.g:.1%})"
        )
        lines.append(
            f"    • Kun g pidetään mallin arvossa ({a.g:.1%}): "
            f"implied_ROE = {v.implied_roe:+.2%} (oma ROE = {a.roe_used:.1%})"
        )
        lines.append(
            f"  Turvamarginaali oman fair valuen suhteen: "
            f"{v.safety_margin_to_fv_pct:+.1f}% "
            f"(positiivinen = aliarvostettu)"
        )

        # EPV-ankkuri: Greenwald's framing for laatuyhtiöitä — "how much
        # of the expected GROWTH VALUE has the market priced in?". More
        # actionable than 90/80/75 % FV thresholds because it answers the
        # user's real question: "by paying today's price, what fraction
        # of the upside am I locking in vs leaving on the table?". Only
        # emitted for laatu (ROE > k); for tuhoutuva and keskinkertainen
        # the framing inverts/explodes and is omitted.
        if v.growth_paid_for_pct is not None:
            free_pct = 100.0 - v.growth_paid_for_pct
            lines.append(
                f"  EPV-ankkuri (laatuyhtiö): kurssi − EPV = "
                f"{v.price - v.epv_pure:+.2f}€, mikä on "
                f"{v.growth_paid_for_pct:.1f}% odotetusta kasvuvarannosta "
                f"({v.growth_value_pure:.2f}€). Eli {free_pct:+.1f}% "
                f"kasvusta tulee 'kaupan päälle' jos malli oikeaan."
            )

        # Entry-tasot — two parallel anchorings (engine carries both):
        #   - For LAATU companies, surface the EPV-anchored 3-tier scale.
        #     EPV-taso = "pay only for current earning power, all growth
        #     free", midpoint = "pay 50 % of expected growth", FV =
        #     "pay 100 % of expected growth". Semantically richer than the
        #     arbitrary 90/80/75 % thresholds.
        #   - For tuhoutuva / keskinkertainen, the EPV-anchor framing
        #     doesn't apply (growth_value ≤ 0), so fall back to the
        #     90/80/75 % FV thresholds from the original Excel methodology.
        if v.entry_growth_midpoint is not None:
            lines.append(
                f"  EPV-ankkuroidut entry-tasot: "
                f"EPV-taso {v.epv_pure:.2f}€ (0 % kasvua hinnoiteltu), "
                f"kasvun puoliväli {v.entry_growth_midpoint:.2f}€ "
                f"(50 % kasvua), fair value {v.fair_value:.2f}€ "
                f"(100 % kasvua). Tulkinta: pörssin nykyhinta "
                f"({v.price:.2f}€) vastaa "
                f"{v.growth_paid_for_pct:.0f} % maksettua kasvua "
                f"(loput tulisi mallin mukaan 'ilmaiseksi')."
            )
        else:
            lines.append(
                f"  Entry-tasot (90/80/75 % FV): "
                f"aloitus {v.entry_aloitus:.2f}€, "
                f"nosto {v.entry_nosto:.2f}€, täysi {v.entry_taysi:.2f}€"
            )

        # ── Sanity-check: extreme safety margins are a red flag ──
        # When |safety_margin| > 100% the model says price differs from FV
        # by more than the entire FV — almost always a sign of mismatched
        # parameters (e.g. manual_override ROE 5% on a stock priced for
        # 13%, run 20260508-221645-249 had Bittium showing -3155 %).
        # Flag it so LEAD softens the takeaway in synthesis instead of
        # presenting the absurd number as a confident verdict.
        if abs(v.safety_margin_to_fv_pct) > 100.0:
            lines.append(
                f"  ⚠️ HUOM REUNATAPAUS: turvamarginaali ({v.safety_margin_to_fv_pct:+.1f}%) "
                f"on poikkeuksellisen suuri. Tämä viittaa siihen että annetut "
                f"parametrit (ROE {a.roe_used:.1%}, k {a.k:.1%}, g {a.g:.1%}) "
                f"ovat kaukana siitä mitä markkina hinnoittelee — joko "
                f"manuaalinen oletus on epärealistinen tai parametrit "
                f"keskenään epäsuhdassa. **Mainitse tämä epävarmuus käyttäjälle**, "
                f"älä esitä lukua varmana tuomiona."
            )
        elif v.quality == "tuhoutuva" and a.roe_version == "manual_override":
            # Subtler case: tuhoutuva-luokka manual override:lla. ROE < k
            # tarkoittaa että kasvu syö arvoa — käyttäjän on tärkeää tietää
            # että manuaalinen ROE-arvo aiheutti tämän tuomion, ei objektii-
            # vinen havainto yhtiön kannattavuudesta.
            lines.append(
                f"  ⚠️ HUOM: 'tuhoutuva'-luokitus johtuu **manuaalisesta "
                f"ROE-overridesta** ({a.roe_used:.1%}), ei agentin tekemästä "
                f"havainnosta. Mainitse käyttäjälle että tämä on skenaario, "
                f"ei ennuste."
            )

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _all_subagents_failed_or_fabricated(workflow_result: WorkflowResult) -> bool:
    """True iff every dispatched subagent either errored or got
    fabrication-guarded.

    Empty subagent_results (zero dispatched) returns False — this is a
    routing failure rather than a data-availability failure, and LEAD
    should still produce a generic answer in that edge case.
    """
    results = workflow_result.subagent_results or []
    if not results:
        return False
    return all(sr.error is not None for sr in results)


def _no_data_response(
    query: str,
    workflow_result: WorkflowResult,
    *,
    lead_model_when_skipped: str = "skipped_no_data",
) -> tuple[str, str, SynthesisTrace]:
    """Construct the fixed answer when no subagent retrieved real data.

    Three pieces of context drive the message: the original query, the
    companies the router identified (so we can name them in the
    response), and the union of subagent error reasons (so a curious
    user can dig into why).

    The intent is the opposite of LEAD's normal job: instead of
    synthesising from data, we explicitly tell the user there IS no
    data so the user can decide whether to retry, rephrase, or move on.
    No invented numbers, no recommendations.
    """
    cls = workflow_result.classification
    companies = cls.companies or []
    company_str = ", ".join(companies) if companies else None

    error_reasons: list[str] = []
    for sr in workflow_result.subagent_results or []:
        if sr.error and sr.error not in error_reasons:
            error_reasons.append(sr.error)

    if company_str:
        head = (
            f"En löytänyt yhtiötä **{company_str}** Inderes-tietokannasta tai "
            f"datalähteet eivät palauttaneet tietoja tähän kysymykseen."
        )
    else:
        head = (
            "En saanut palautettua dataa tähän kysymykseen mistään käytössä "
            "olevasta lähteestä."
        )

    body_parts = [
        f"**💭 Perustelut:** Kaikki {len(workflow_result.subagent_results or [])} "
        f"subagenttia kuolivat ennen synteesiä, joten synteesi ohitettiin "
        f"keksittyjen lukujen estämiseksi.",
        "",
        head,
        "",
        "**Mitä voit tehdä:**",
        "- Tarkista yhtiön nimen kirjoitusasu (esim. *Sampo Oyj* → *Sampo*)",
        "- Kokeile yhtiön Inderes-listattua nimeä — kaikkia pörssiyhtiöitä ei ole katalogissa",
        "- Jos kysymys ei koske tiettyä yhtiötä, kokeile tarkennusta",
    ]
    if error_reasons:
        body_parts.append("")
        body_parts.append("**Syyt agenttien epäonnistumisille:**")
        for reason in error_reasons[:3]:  # cap to keep the answer short
            short = reason[:160] + ("…" if len(reason) > 160 else "")
            body_parts.append(f"- `{short}`")

    final_text = "\n".join(body_parts)

    log.warning(
        "synthesize() short-circuited: all %d subagents failed/fabricated, "
        "returning no-data response for query=%r companies=%r",
        len(workflow_result.subagent_results or []),
        query[:80],
        companies,
    )

    trace = SynthesisTrace(
        conflict_report=ConflictReport(
            skipped_reason="all_subagents_failed_or_fabricated",
        ),
        lead_seconds=0.0,
        paattely=None,
        paattely_raw=None,
    )
    return final_text, lead_model_when_skipped, trace


async def synthesize(
    query: str,
    workflow_result: WorkflowResult,
    *,
    deep_lead: bool = False,
    deep_subagents: bool = False,
) -> tuple[str, str, SynthesisTrace]:
    """Run the lead agent over the subagents' outputs.

    Args:
        query: original user question
        workflow_result: results from the subagent fan-out
        deep_lead: when True, builds LEAD with Gemini Pro for synthesis.
            Use for high-stakes queries where synthesis nuance matters.
            Subagents/conflict-detector unaffected by this flag.
        deep_subagents: when True, the conflict-detector is also built
            on Pro. The subagents themselves are upgraded by the
            workflow (passing ``subagents_deep=True`` to ``run_workflow``);
            this synthesize parameter only governs whether the
            conflict-detector also gets the upgrade in the same tier.
            Used by the "Tarkka kaikki" UI radio.

    Returns (final_answer_text, lead_model_used, synthesis_trace) where
    `synthesis_trace.conflict_report` is the conflict-detector output and
    `synthesis_trace.lead_seconds` is the wall clock for the LEAD synthesis call.
    """
    from ..agents._common import today_prompt_prefix

    # Short-circuit: if every subagent failed or got fabrication-guarded,
    # there is no MCP-sourced data for LEAD to synthesise. Returning a
    # fixed "no data" response is the only safe option — running LEAD on
    # empty inputs has historically led it to fill the void with
    # plausible-sounding but invented analysis (case_004 in
    # evals/golden.yaml: "Vincit" returned a complete fabricated answer
    # because the catalog miss was hidden from LEAD by 0-tool-call
    # fabricated subagent text).
    if _all_subagents_failed_or_fabricated(workflow_result):
        return _no_data_response(
            query, workflow_result, lead_model_when_skipped=(
                "skipped_no_data" if not deep_lead else "skipped_no_data"
            )
        )

    conflict_report = await detect_conflicts(workflow_result, deep=deep_subagents)

    # Process VALUATION subagents (if any) — parse their JSON, run the
    # deterministic engine, and stash records for run_log + LEAD prompt.
    valuation_records = _process_valuation_subagents(workflow_result)

    subagents_block = _format_subagent_results(workflow_result)
    tool_trace_block = _format_tool_call_trace(workflow_result)
    conflict_block = _format_conflict_block(conflict_report)
    valuation_block = _format_valuation_block(valuation_records)
    cls = workflow_result.classification

    # Plan-then-execute: when enabled, LEAD planner has run BEFORE the
    # subagents. Surface its plan here so synthesis can reference what
    # was intended vs what was actually delivered (e.g. "we set out to
    # compare ROE; quant returned only one company's data — adjust").
    plan = workflow_result.plan
    if plan is not None and plan.parsed is not None:
        plan_block = (
            f"PRE-DISPATCH PLAN (LEAD planner ran before subagents):\n"
            f"  thinking:   {plan.parsed.get('thinking', '?')}\n"
            f"  axis:       {plan.parsed.get('axis') or '(not a comparison)'}\n"
            f"  watchouts:  {plan.parsed.get('watchouts') or '[]'}\n"
            f"  per-subagent guidance: "
            f"{plan.parsed.get('per_subagent') or {}}\n"
        )
    else:
        plan_block = "_no pre-dispatch plan; subagents ran on default behaviour_"

    prompt = today_prompt_prefix() + f"""\
USER QUESTION:
{query}

ROUTING DECISION:
domains   = {[d.value for d in cls.domains]}
companies = {cls.companies}
comparison = {cls.is_comparison}
reasoning = {cls.reasoning}

{plan_block}

SUBAGENT OUTPUTS (the agent's own narrative summary):
{subagents_block}

TOOL CALL TRACE (ground truth — what the MCP tools actually returned):
{tool_trace_block}

How to use the tool call trace:
- This is the **structured ground truth**. The subagent text above is its summary; this section shows what the tools actually returned.
- **Hallucination check**: if a subagent named a specific entity (company, person, date) that does NOT appear in the tool result's `item_names`, **drop that entity from your answer**. Do not surface unsupported claims.
- **Completeness check**: if the tool returned N items and the subagent only mentioned M < N when the user asked for a list, either include the missing items or explicitly state which subset and why. Do not silently truncate.
- **Numerical & attribution check**: if a subagent quoted a specific number, name, or date, the tool result is the source of truth — prefer it when there's a conflict.
- If `item_names` is empty for a tool call, the result was non-structured (e.g. document body, transcript) and the subagent's summary is the best you have.

CONFLICT REPORT (pre-synthesis structural analysis of subagent outputs):
{conflict_block}

How to use the conflict report:
- Treat `agreements` as load-bearing: claims confirmed by multiple subagents are safer to surface.
- For each item in `conflicts`: do NOT silently pick one side. Either resolve it (state which subagent's claim is more likely correct AND why), or flag the disagreement explicitly to the user.
- For `isolated_claims`: be skeptical. A specific factual claim (a company name in a list, a number, an attributed quote) that only one subagent made and that no other corroborated is the most common hallucination shape. Either drop it, or surface it with an explicit "single-source" caveat.

ALTERNATIVE VALUATION (user's own methodology, opt-in — present only when user enabled the toggle):
{valuation_block}

How to use the alternative valuation:
- This is the **user's own valuation methodology** (Greenwald-Gordon hybrid: FV = ((ROE-g)/(k-g)) × BVPS, with quality classification by ROE-vs-k). The numbers are deterministically computed by a Python engine; do NOT recalculate them.
- If the block is the placeholder "_user did not enable alternative valuation; default flow only_", **skip the comparison section entirely** — do not invent it.
- If real valuation records are present, add a section titled `## Oma malli vs Inderes` (FI) or `## Own model vs Inderes` (EN) to the answer body. In it, **per company**:
  1. State own fair value with one number (the engine's `fair_value`).
  2. State Inderes' target price (from QUANT subagent's INDERES VIEW).
  3. State the percentage delta and explain the source of the difference (different k? different g? different ROE-version chosen?).
  4. State the quality classification (laatu / keskinkertainen / tuhoutuva) and what it implies.
  5. Flag any agent warnings about data quality.
- Do NOT invent numbers not in this block. The engine has full precision; round to 2 decimals when displaying.
- The comparison section sits **after** the standard answer body but **before** `**📖 Lähteet:**`.

Now synthesize a final answer for the user, following your instructions.
"""

    t_lead = time.time()
    async with build_lead_agent(deep=deep_lead) as lead:
        result = await lead.run(prompt)
        text = result.text if hasattr(result, "text") else str(result)
        model_used = getattr(lead.client, "last_used_model", "unknown")
    lead_seconds = time.time() - t_lead

    # Pull out the JSON Päättely block — UI renders it as a 2×2 slot grid,
    # not inline text. The raw text returned to the caller has the block
    # stripped so render_lead_answer doesn't dump JSON into the answer body.
    cleaned_text, paattely_raw, paattely, paattely_err = _extract_paattely(text)
    if paattely_err:
        log.warning("päättely JSON extraction failed: %s", paattely_err)

    trace = SynthesisTrace(
        conflict_report=conflict_report,
        lead_seconds=lead_seconds,
        paattely=paattely,
        paattely_raw=paattely_raw,
        paattely_error=paattely_err,
        valuations=valuation_records,
    )
    return cleaned_text, model_used, trace
