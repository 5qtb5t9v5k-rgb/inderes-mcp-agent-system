-- Diagnostic SQL queries for the runs_index.sqlite database.
-- Build the index first:  python scripts/build_runs_index.py
-- Then:                   sqlite3 ~/.inderes_agent/evals/runs_index.sqlite < evals/sample_queries.sql
--
-- Each query in this file targets a known weakness category we want to
-- regression-test against. As more weaknesses are discovered (via user
-- feedback or the LLM-judge), add a new query here and a corresponding
-- entry in evals/golden.yaml.

-- --------------------------------------------------------------------
-- Q1: Comparison-style queries that got under-routed (< 3 domains).
-- Expected fix: router should detect "vertaile X ja Y" / "X vs Y" and
-- always include {quant, research, sentiment} at minimum.
-- --------------------------------------------------------------------
SELECT substr(ts, 1, 16) AS ts, query, domains, subagent_count
FROM runs
WHERE is_comparison = 1
  AND has_query = 1
  AND domains_count < 3
ORDER BY ts DESC LIMIT 20;

-- --------------------------------------------------------------------
-- Q2: Noise — empty / trivial / zero-subagent runs that pollute eval data.
-- These should be filtered out before any LLM-judge sees them.
-- --------------------------------------------------------------------
SELECT
    SUM(CASE WHEN has_query = 0 THEN 1 ELSE 0 END) AS empty_query,
    SUM(is_trivial_query) AS trivial,
    SUM(CASE WHEN subagent_count = 0 THEN 1 ELSE 0 END) AS zero_subagents,
    COUNT(*) AS total
FROM runs;

-- --------------------------------------------------------------------
-- Q3: Repeat queries — same normalised query run 3+ times.
-- Reproducibility check: same query → should give structurally similar
-- output. A delta in domains/companies/synthesis structure between runs
-- of the same query is a strong signal of model drift.
-- --------------------------------------------------------------------
SELECT
    query_norm,
    COUNT(*) AS times_run,
    MIN(substr(ts, 1, 16)) AS first_ts,
    MAX(substr(ts, 1, 16)) AS last_ts
FROM runs
WHERE has_query = 1 AND is_trivial_query = 0
GROUP BY query_norm
HAVING COUNT(*) >= 3
ORDER BY times_run DESC;

-- --------------------------------------------------------------------
-- Q4: Päättely shape distribution — structured vs prose vs empty.
-- The structured form (disagree/resolution/uncertain/skipped slots) is
-- our spec, but in practice LEAD produces almost none. Either fix the
-- prompt to make structured the default, or accept prose and drop the
-- structured branch.
-- --------------------------------------------------------------------
SELECT paattely_kind, COUNT(*) AS n
FROM runs
WHERE has_query = 1 AND is_trivial_query = 0
GROUP BY paattely_kind
ORDER BY n DESC;

-- --------------------------------------------------------------------
-- Q5: Conflict-detector hit rate.
-- Of the runs with ≥2 subagents (where the detector is meaningful), how
-- many actually surfaced any agreements / conflicts / isolated claims?
-- A detector that finds nothing on most multi-agent runs is suspicious —
-- could be a parser issue (LEAD's combined output not in expected shape).
-- --------------------------------------------------------------------
SELECT
    SUM(CASE WHEN conflicts_count > 0 THEN 1 ELSE 0 END) AS runs_with_conflicts,
    SUM(CASE WHEN agreements_count > 0 THEN 1 ELSE 0 END) AS runs_with_agreements,
    SUM(CASE WHEN isolated_count > 0 THEN 1 ELSE 0 END) AS runs_with_isolated_claims,
    SUM(CASE WHEN conflict_skipped IS NOT NULL THEN 1 ELSE 0 END) AS skipped,
    COUNT(*) AS total_eligible
FROM runs
WHERE has_query = 1
  AND is_trivial_query = 0
  AND subagent_count >= 2;

-- --------------------------------------------------------------------
-- Q6: Top tools + per-tool error rate.
-- High-error tools point to: typos in input, MCP rate-limits, or schema
-- drift. search-companies is the obvious candidate to fix — it sees
-- almost every query's first call.
-- --------------------------------------------------------------------
SELECT
    tool_name,
    COUNT(*) AS calls,
    SUM(has_error) AS errors,
    ROUND(100.0 * SUM(has_error) / COUNT(*), 1) AS error_pct
FROM tool_calls
GROUP BY tool_name
ORDER BY calls DESC;

-- --------------------------------------------------------------------
-- Q7: Pro-tier vs Flash Lite — quantitative comparison.
-- Naive but useful: average synthesis length, conflict-signal density,
-- warning-phrase frequency. Once we have judge scores, replace this with
-- avg(judge.score) by tier.
-- --------------------------------------------------------------------
SELECT
    CASE WHEN lead_model LIKE '%pro%' THEN 'pro_lead' ELSE 'flash_lite' END AS tier,
    COUNT(*) AS runs,
    ROUND(AVG(duration_s), 1) AS avg_duration_s,
    ROUND(AVG(synthesis_chars), 0) AS avg_synthesis_chars,
    ROUND(AVG(agreements_count + conflicts_count + isolated_count), 1) AS avg_conflict_signals,
    SUM(has_warning_phrase) AS warnings_surfaced
FROM runs
WHERE has_query = 1 AND is_trivial_query = 0
GROUP BY tier;

-- --------------------------------------------------------------------
-- Q8: Valuation runs that did NOT surface any warning phrase.
-- Most should — extreme safety_margin, "tuhoutuva" classification, etc.
-- Runs without warnings on long synthesis are candidates for review:
-- maybe the engine output an extreme value and LEAD failed to flag it.
-- --------------------------------------------------------------------
SELECT substr(ts, 1, 16) AS ts, query, has_warning_phrase, synthesis_chars
FROM runs
WHERE has_valuation = 1
  AND has_synthesis = 1
  AND has_warning_phrase = 0
ORDER BY ts DESC LIMIT 20;

-- --------------------------------------------------------------------
-- Q9: Routes per query-shape. Useful for golden-set construction.
-- Group queries by their domain set + comparison flag → see how many
-- distinct routes we've actually exercised in real use.
-- --------------------------------------------------------------------
SELECT domains, is_comparison, COUNT(*) AS n
FROM runs
WHERE has_query = 1 AND is_trivial_query = 0
GROUP BY domains, is_comparison
ORDER BY n DESC LIMIT 20;

-- --------------------------------------------------------------------
-- Q10: Latency outliers. Anything above 60 s is suspicious — usually a
-- subagent that got stuck or fell back. Inspect these runs to confirm
-- the timeout / fallback path triggered correctly.
-- --------------------------------------------------------------------
SELECT substr(ts, 1, 16) AS ts, query, duration_s, fanout_s, lead_s, subagent_errors
FROM runs
WHERE has_query = 1 AND duration_s > 60
ORDER BY duration_s DESC LIMIT 10;
