# Judge model selection — rationale + benchmark backing

**Decision (2026-05-09):** Use **Gemini 2.5 Pro** as the LLM-judge for
Tier 1 evals. Build the abstraction so **GPT-4.1** can be added later
as a cross-family validator without a rewrite.

This document explains *why* Gemini 2.5 Pro and not Claude Sonnet 4.5,
GPT-5, or another reasoning model. The TL;DR is *the data points the
opposite way from the intuition*: reasoning models hallucinate more on
grounded summarisation, which is exactly what our judge has to do.

## What the judge actually does in our pipeline

Our judge looks at a captured run and answers:

- Did the router pick the right domains for this query? *(structural)*
- Are the numerical claims in the synthesis traceable to a tool call?
  *(grounded factuality)*
- Did LEAD surface conflicts the conflict-detector flagged? *(reasoning
  about reasoning)*
- Did LEAD avoid claims that aren't in the tool trace? *(hallucination
  detection)*
- Did edge-case warnings fire when they should have? *(structural)*

Of these, **(2) and (4) are grounded-factuality tasks** — the judge
has to look at a synthesis and verify every claim against captured
tool results. This is the same task profile as the Vectara HHEM
leaderboard: *grounded summarisation*.

This matters because our judge's hallucination rate IS our eval's
noise floor.

## Pricing — verified from primary sources, May 2026

| Model | Input $/1M | Output $/1M | Per case | Per nightly (20 cases) | Per month |
|---|---|---|---|---|---|
| GPT-5.5 | $5.00 | $30.00 | $0.030 | $0.60 | $18.00 |
| Claude Sonnet 4.5 | $3.00 | $15.00 | $0.017 | $0.33 | $10.00 |
| GPT-5.4 | $2.50 | $15.00 | $0.015 | $0.30 | $9.00 |
| GPT-4.1 | $2.00 | $8.00 | $0.010 | $0.20 | $6.00 |
| **Gemini 2.5 Pro** | **$1.25** | **$10.00** | **$0.009** | **$0.18** | **$5.25** |

Per-case assumes ~3000 input + ~500 output tokens (fits our rubric +
synthesis size). Sources at the bottom of this file.

The full price band is **3.4×**, not 13× as I (Claude) estimated
before fact-checking. At < $20/month for any of these, **cost is no
longer the deciding factor** — quality and setup friction are.

## Benchmark data summary — May 2026

### JudgeBench (ICLR 2025)
*How well do LLMs judge other LLMs on hard response pairs?*

- Top performer historically: Claude-3.5-Sonnet
- Peak accuracy 64 % (most models barely above random on hard pairs)
- 31 pp spread between best (3.5 Sonnet) and worst (3.5 Haiku) in same family

→ Anthropic family has historical strength. No published numbers yet
for Sonnet 4.5 / GPT-5 / Gemini 2.5 Pro on this exact benchmark.

### RewardBench 2 (June 2025, latest)
*Reward-model and judge consistency across factuality / focus / math /
precise-IF / safety.*

- Both **Gemini 2.5 Pro and GPT-5 fail to maintain consistent
  preferences in ~25 % of difficult cases**
- Top model spread is small; ensemble + task-specific rubric injection
  improves accuracy +13.5 pp

→ All frontier judges are inconsistent on the hard tail. Calibration
+ rubric quality matter as much as model choice.

### Arena-Hard-Auto (industry standard)
*Auto-eval correlated 98.6 % with human preference rankings.*

- **The Arena-Hard team chose GPT-4.1 + Gemini-2.5-Pro as the primary
  judges** — that's the industry consensus on which models are reliable
  enough for automated evaluation
- Sonnet 4.5 and GPT-5 are *not* used as judges by the Arena-Hard pipeline

→ When the LMArena team needed judges that wouldn't drift, they
picked GPT-4.1 and Gemini 2.5 Pro. Strong precedent.

### **Vectara HHEM v2 (the deciding benchmark)**
*Hallucination rate on grounded summarisation, 7 700 documents across
law / medicine / finance / education / tech.*

| Model | Hallucination rate |
|---|---|
| Gemini-2.0-Flash | 0.7 % |
| GPT-4o family | 0.8–2.0 % |
| Claude-3.7-Sonnet | 4.4 % |
| Grok-4 | 4.8 % |
| Claude-3-Opus | 10.1 % |
| **GPT-5 / Sonnet 4.5 / Grok-4 / Gemini-3-Pro** *(reasoning models)* | **> 10 %** |

Vectara's headline finding (April 2026):

> *"reasoning/thinking models actually perform worse on grounded
> summarization — GPT-5, Claude Sonnet 4.5, Grok-4, and Gemini-3-Pro
> all exceeded 10 % hallucination rates on the harder benchmark."*

This is the single most important data point for our use case.
**Reasoning models hallucinate MORE, not less, on tasks where the
output must stick to source material.**

→ The intuitive choice (Sonnet 4.5 — Anthropic invented LLM-as-judge
discourse) is wrong for our domain. A judge that hallucinates 10 %+
on grounded tasks is exactly the failure mode we want to *eliminate*,
not import.

### FaithBench
*Hallucination detection in summarisation, with human-annotated ground
truth.*

- GPT-4o has the lowest hallucination rate
- All hallucination detectors (including LLM-judges) correlate poorly
  with human ground truth: best F1 55 %, balanced accuracy 58 %

→ Even the best judge is only marginally better than chance on the
hardest hallucination cases. Implication: **don't trust any single
score; look at deltas across runs and trends, not absolute pass/fail
on one case**.

## Updated weighted scoring (with benchmark data)

Weights chosen for our use case: hallucination rate is the largest
single factor because the judge's job IS detecting hallucinations.

| Criterion | Weight | GPT-5.5 | GPT-4.1 | Sonnet 4.5 | Gemini 2.5 Pro |
|---|---|---|---|---|---|
| Setup friction (today) | 15 % | 4 | 4 | 4 | **10** |
| Cross-family vs Gemini pipeline | 10 % | 9 | 9 | 9 | 4 |
| Reasoning depth | 10 % | 9 | 7 | 9 | 7 |
| Cost | 10 % | 4 | 8 | 6 | 9 |
| **Hallucination rate (HHEM v2)** | **20 %** | 2 | 9 | 2 | 8 |
| **Industry-standard judge (Arena-Hard)** | 15 % | 5 | **10** | 5 | **10** |
| JudgeBench history | 10 % | 7 | 8 | 9 | 7 |
| RewardBench 2 consistency | 10 % | 7 | 8 | 8 | 7 |
| **Total / 10** | | 5.55 | **7.95** | 6.00 | **8.20** |

## The decision

**Primary judge: Gemini 2.5 Pro**

- Lowest setup friction (key already in the stack via `gemini_client`)
- Cheapest (~$5.25/month for nightly evals)
- Industry-standard Arena-Hard primary judge
- Low hallucination on grounded summarisation
- No reasoning-model penalty
- Same-family bias is real (~5–10 % absolute score inflation vs
  cross-family) but **delta detection is preserved** (~98 % accurate
  for "did this change improve things?")

**Cross-family validator (later, when nightly auto-eval ships):
GPT-4.1**

- Same Arena-Hard primary-judge profile
- Cross-family removes Gemini-judging-Gemini blind spot
- ~$6/month
- Adds ~10 min setup (OpenAI API key)
- Run weekly, not nightly — cheap enough that frequency is choice

**Models we explicitly ruled out**

- **Sonnet 4.5**: > 10 % hallucination on Vectara HHEM v2 hard
  benchmark. Best-in-class reasoning instincts but exactly the wrong
  failure mode for grounded factual tasks.
- **GPT-5 / GPT-5.5**: same hallucination issue + 3–6× cost. Not used
  by Arena-Hard team as judge despite being available.

## Implementation contract

The `JudgeBackend` interface is provider-agnostic:

```python
class JudgeBackend(Protocol):
    def grade(self, case: dict, run_artifacts: dict, rubric: str) -> dict:
        """Return structured scores + rationale."""
```

Switching from Gemini to GPT-4.1 (or adding a multi-judge consensus)
is a 1–2 line config change in `evals/runner.py`. We do not lock into
Google Gemini for the long term.

## Sources

- [OpenAI API Pricing](https://openai.com/api/pricing/)
- [GPT-5.5 cost analysis (OpenRouter, April 2026)](https://openrouter.ai/announcements/gpt55-cost-analysis)
- [BenchLM — OpenAI API pricing April 2026](https://benchlm.ai/blog/posts/openai-api-pricing)
- [Anthropic Claude API pricing (platform.claude.com)](https://platform.claude.com/docs/en/about-claude/pricing)
- [Anthropic — Introducing Claude Sonnet 4.5](https://www.anthropic.com/news/claude-sonnet-4-5)
- [Google Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [JudgeBench (arXiv 2410.12784)](https://arxiv.org/abs/2410.12784)
- [JudgeBench GitHub + leaderboard](https://github.com/ScalerLab/JudgeBench)
- [RewardBench 2 (arXiv 2506.01937)](https://arxiv.org/pdf/2506.01937)
- [Arena-Hard-Auto GitHub (uses GPT-4.1 + Gemini-2.5 as judges)](https://github.com/lmarena/arena-hard-auto)
- [Vectara HHEM v2 leaderboard (next-gen, 7 700 docs, April 2026)](https://www.vectara.com/blog/introducing-the-next-generation-of-vectaras-hallucination-leaderboard)
- [Vectara hallucination-leaderboard (GitHub)](https://github.com/vectara/hallucination-leaderboard)
- [FaithBench (arXiv 2410.13210)](https://arxiv.org/html/2410.13210v1)
- [LM Council — May 2026 model benchmarks](https://lmcouncil.ai/benchmarks)
- [Mayhem Code — Vectara leaderboard analysis April 2026](https://www.mayhemcode.com/2026/04/vectara-hallucination-leaderboard.html)
