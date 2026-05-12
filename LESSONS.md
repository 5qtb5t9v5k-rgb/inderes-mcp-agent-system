# Lessons learned: building an agentic system

A reflective companion to `README.md` and `ARCHITECTURE.md`. Where the other
docs describe **what** this system does and **how** it's built, this one is
about **what the build taught me** — about multi-agent systems generally, about
the gap between "demo" and "actually shipping", and about where time really
goes when you set out to build one of these things end-to-end.

Treat this as one engineer's notebook after ~3 weeks of iteration. Your
mileage will differ. Some of these lessons are obvious in hindsight; that's
the nature of lessons.

---

## Table of contents

- [The three pillars: AI / UI / Infra](#the-three-pillars-ai--ui--infra)
- [The AI layer — what makes it "agentic"](#the-ai-layer--what-makes-it-agentic)
- [The UI layer — multi-agent UX is not cosmetic](#the-ui-layer--multi-agent-ux-is-not-cosmetic)
- [The infra layer — boring but critical, and the biggest time sink](#the-infra-layer--boring-but-critical-and-the-biggest-time-sink)
- [Cross-cutting lessons](#cross-cutting-lessons)
- [Things I'd do differently next time](#things-id-do-differently-next-time)
- [Open questions](#open-questions)

---

## The three pillars: AI / UI / Infra

A multi-agent system is rarely "an AI project" in practice. It's an AI core
wrapped in a UI surface and held up by an infra scaffold, and all three are
load-bearing. Rough estimate of where the lines of code in this repo go:

| Pillar | % of code | % of "this is what makes the product work" |
|---|---|---|
| **AI** (agents, prompts, router, synthesis) | ~30 % | ~100 % of *result quality* |
| **UI** (Streamlit app, theme, REPL, render) | ~20 % | ~80 % of *user trust* |
| **Infra** (OAuth, MCP plumbing, fallback, observability, deploy) | ~50 % | ~100 % of *running at all* |

The percentages don't add to 100 — they're not exclusive shares, they're how
much each pillar matters along its own axis. The AI is what produces the
answer. The UI is what makes the answer believable. The infra is what
prevents the system from silently dying when no one's looking.

If any one pillar is missing or weak, the other two can't compensate.

---

## The AI layer — what makes it "agentic"

### Per-agent tool partitioning is the single highest-leverage decision

A monolithic agent with all 16 Inderes MCP tools makes worse tool-call
choices at every step than four agents with 3–8 tools each. This isn't
subtle — it shows up as wrong tools being called, missed data, and
much longer reasoning chains. Splitting by responsibility (`quant`,
`research`, `sentiment`, `portfolio`) keeps each LLM context tight and
each system prompt focused, and dropped tool-call error rates noticeably.

Multiplicative cost (4× LLM calls) is offset by fewer wasted iterations and
a clearer mental model when something goes wrong. You can read one
subagent's prompt + tool list and understand exactly why it picked the tool
it picked.

### Prompts are code

The Markdown files in `agents/prompts/*.md` are not documentation. They are
programs. Each one defines a persona's behavior, tool-call ordering,
output format, refusal rules, and reasoning rubric. Changing them changes
results.

This has practical consequences:
- They belong in version control (they are).
- They deserve a code review when they change (in practice, they didn't
  always get one — that's a lesson).
- Diffing prompts across runs to see what changed is a real debugging tool.
- Adding a single sentence to a prompt can be more impactful than 200 lines
  of orchestration code.

### Structured-output classification beats handoff dances

The router is one Gemini call with a structured-output JSON schema and a
handful of few-shot examples. It returns `(domains, companies,
is_comparison, reasoning)` deterministically.

The alternative — a multi-turn handoff/group-chat orchestration where
agents themselves negotiate routing — was tempting because Microsoft Agent
Framework has builders for it. But for a domain with ~7 categories, the
structured-output classifier is more reliable, faster, and easier to
debug. You see exactly what the router decided and why, every time.

The general lesson: **prefer reliable narrow components over flexible
broad ones** when you can. You can replace the router with something
smarter later if you actually need to. Until then, simplicity wins.

### Lead-with-no-tools forces a clean synthesis

The lead agent has zero MCP tools. It can only synthesize from the text the
subagents returned. This sounds limiting — and is, deliberately — because:
- It prevents the lead from re-querying and duplicating MCP calls.
- It forces a single bottleneck (the subagent output text) for "what the
  team knows", which is debuggable.
- It keeps lead latency low (one LLM call, no tool-call loop).
- You can read the lead's input prompt and see exactly what it had to work
  with.

The cost: any data the subagents missed is invisible to the lead. The lead
can't "go check itself". This trade-off has been worth it. When the lead
synthesizes badly, the fix is almost always in the subagent prompts.

### Thought traces are non-optional

Every subagent prompt mandates a `**Ajatus:**` line at the top of its
response explaining which tools it'll call and why. The lead mandates a
`**💭 Perustelut:**` callout describing how it combined the subagents'
outputs.

These exist for two reasons:
1. **For users**: surface the multi-agent reasoning instead of burying it
   behind tool-call logs in an expander.
2. **For me**: when an answer is wrong, the thought trace tells me whether
   the agent reasoned wrongly or executed correctly on a wrong premise.

A multi-agent system without thought traces is a black box even to its
author. Forcing reasoning into the response itself, in a fixed format, was
one of the higher-impact prompt changes I made.

---

## The UI layer — multi-agent UX is not cosmetic

This was the surprise. I started thinking the UI was "the easy part"
because the agents already worked in the CLI. The UI ended up being where
half the iterations went, and for good reason.

### Multi-agent systems hide their work by default

In a single-agent system, the UI shows the answer and maybe a "thinking"
spinner. In a multi-agent system, hiding the work makes the system feel
like a magic box that occasionally lies. Users don't know whether the
answer came from one model, four models, fresh data, cached data, or a
dropped subagent.

The UI work — persona glyphs (◆▲■●✦), color-coded routing pills,
per-agent rows in the activity log, persona-styled live status messages,
recommendation badge above the synthesis, clickable Inderes source links —
is what builds trust that the answer is grounded.

It's not decoration. It's epistemic infrastructure.

### Trust-building features compound

Three changes that look small individually but compound:

- **Recommendation badge** above the synthesis (PR #28). Users see Inderes'
  own call (LISÄÄ / OSTA / VÄHENNÄ) before reading the synthesis prose, so
  the synthesis is read as commentary on a known anchor rather than a
  free-floating claim.
- **Clickable source links** in the "Lähteet:" footer (PR #29). Tool-result
  URLs like `pageUrl` get rewritten as proper links to inderes.fi. The
  user can verify any claim with one click.
- **Persona-styled live status** (PR #23). Replaced generic
  "Subagentit"/"LEAD" labels with descriptive lines in persona color, e.g.
  `▲ aino-quant: hakee P/E:tä ja tavoitehintaa…`. Users now see exactly
  what's happening rather than just a spinner.

Each one alone is a small win. Together they change how the product feels
from "AI-generated text" to "research desk".

### Streamlit is the right tool for this scale

Streamlit's "rerun the script on every interaction" model is
philosophically wrong for chat (history rebuilds every turn), but the
ergonomics for a single-developer multi-agent demo are unbeatable. Custom
CSS, Markdown rendering, expanders, sidebars — everything for a
respectable interface in ~1500 lines, no React build chain.

It does eventually push back: large chat histories slow the rerun cycle.
The fix here was to drop the inline `narrative.md` rendering for old
messages — keep the trace expander, drop the full narrative. Both moves
were UI-driven decisions that fed back into how data was persisted.

---

## The infra layer — boring but critical, and the biggest time sink

If you're tempted to think a multi-agent system is "mostly the agents",
this is the section that will disabuse you. Roughly half the code in
this repo isn't AI at all. It's plumbing — and the plumbing was the
hardest part to get right.

### OAuth was the biggest single time sink

Inderes' MCP server sits behind an OAuth 2.0 Authorization Code + PKCE
flow against Keycloak. Microsoft Agent Framework's `MCPStreamableHTTPTool`
exposes a `header_provider` callback for tool invocations but **not** for
the connection-time `initialize` call. Since the 401 happens during
`initialize`, that hook is useless. We had to:

1. Discover endpoints via RFC 9728 (`/.well-known/oauth-protected-resource`).
2. Implement the PKCE dance with a localhost callback server.
3. Cache tokens to `~/.inderes_agent/tokens.json` with `0600` permissions.
4. Inject Bearer auth via `httpx.AsyncClient.auth=` so every request
   including `initialize` carries the token.
5. Pre-fetch the token in `__main__.py` before fanning out four agents in
   parallel — otherwise four browsers open at once on cold start.

None of this is "AI work". All of it was required to make the agents able
to call any tool at all.

### Cloud deployment kills you with idle timeouts (and that's not the only cap)

Local development was fine: tokens cached on disk, refresh token used
silently on subsequent runs, OAuth happens once a week if you're lucky.
Streamlit Cloud broke that model in the obvious way (ephemeral container
loses the local cache between restarts) **and** in a non-obvious way: an
idle Keycloak SSO session eventually invalidates the refresh token chain,
even with a valid refresh token in hand.

Three fixes were needed, all infra-only, none AI:

- **Gist mirror** (PRs #16, #17, #27): refreshed tokens get pushed to a
  private GitHub gist; cold start pulls from the gist. Survives container
  restarts.
- **GitHub Actions cron** (PR #25): runs every 15 min, refreshes tokens
  via the gist. Keeps the SSO session warm in principle.
- **cron-job.org as actual scheduler** (final fix): GitHub Actions
  free-tier scheduling turned out to be unreliable in practice — observed
  gaps of 1-4 hours between scheduled runs even with `*/5` cadence
  configured. Switched to cron-job.org, which fires the same workflow
  via GitHub's `workflow_dispatch` API every 5 minutes reliably. Idle
  timeout problem solved.

The cron is conceptually a heartbeat for an absent user. The lesson: if
your auth provider has session timeouts, you can't rely on user activity
to keep them alive. You need an authenticated heartbeat — and you need to
verify the heartbeat actually fires at the cadence you configured.

**But:** even with reliable keepalive, the IdP can have a wall-clock
**Session Max** that no amount of pinging can extend. We measured this
empirically against Inderes' Keycloak: SSO Session Max = exactly 10
hours from login, regardless of activity. Cron-job.org-driven token
rotation succeeded ~120 times in a row over those 10 hours, then failed
with `invalid_grant: Token is not active` on minute 601. There is no
client-side fix for this — it requires either the IdP team to extend the
cap, or accepting a daily re-auth cadence.

The deeper lesson: with third-party identity, **you don't control session
lifetime**. The infrastructure layer can hide *some* of the user-visible
pain (gist mirror across container restarts, keepalive across idle
timeouts), but the absolute cap is set by someone else. Plan operational
runbooks accordingly.

### "Free tier" has hidden cliffs

The system is designed for Google's free Gemini tier. The headline limit
(`gemini-3.1-flash-lite-preview`: 500 req/day) sounds generous. The reality
is grittier:

- Both primary and fallback models get 503-ed simultaneously during global
  capacity spikes. This is not "free tier vs paid tier" — it happens
  globally.
- `gemini-2.5-pro` has zero quota on the free tier even though it's listed.
  Selecting it returns a confusing "function calling config" error rather
  than a clean quota error. (See the parked Pro-toggle below.)
- Daily limits don't reset at midnight your time. They reset at midnight
  Pacific. Plan accordingly.

The fallback wrapper (`FallbackGeminiChatClient`) was originally written to
handle 503s. It now also handles 429 (`RESOURCE_EXHAUSTED`) and emits a
clean `QuotaExhaustedError` when both primary and fallback are dead. Most
of that code is error-handling, not "doing the LLM call".

### Per-run forensic records beat a database

Every query writes a directory at `~/.inderes_agent/runs/<timestamp>/`
with `query.txt`, `routing.json`, `subagent-NN-*.json`, `synthesis.txt`,
`meta.json`, `console.log`, `narrative.md`. The narrative parses
`console.log` for tool-call timings and combines everything into a
human-readable timeline.

A SQLite or JSONL log would be more queryable. But for a personal
project — and arguably for any debugging-heavy multi-agent system — the
per-run directory wins on:

- **Readability**: `cat narrative.md` and you have everything.
- **Shareability**: zip it, send it, the recipient needs nothing.
- **Greppability**: `grep -r "503" ~/.inderes_agent/runs/`.
- **Forensic completeness**: every byte of every LLM call is on disk.

The trade-off is inode count grows with usage. That's a real but small
problem.

### MAF is a useful primitive, not a finished framework

Microsoft Agent Framework gave us:
- The `Agent` lifecycle, AFC tool-calling loop, MCP integration.
- Per-agent chat client, system instructions, tool list.
- OpenTelemetry span emission for free.

What it didn't give us:
- An orchestrator that handles `asyncio.Semaphore` for free-tier quota.
- Per-company comparison fan-out at runtime.
- A chat-client wrapper that can fall back across models on 503/429.
- OAuth bridging for MCP `initialize` calls.
- Schema sanitization for MCP servers that include JSON-Schema metadata
  Gemini's `FunctionDeclaration` rejects.

We subclassed and extended in five places (`FallbackGeminiChatClient`,
`_SanitizingMCPTool`, `_InderesBearerAuth`, `attach_console_log_handler`,
the workflow). Each one was 50–200 lines and each one was load-bearing.

The lesson: agent frameworks are scaffolding, not turn-key. Plan to
subclass.

#### Concrete vendor-quirks MAF does NOT abstract away

The "plan to subclass" lesson is abstract until you have specific
examples. Three from this project that each cost an afternoon:

1. **Gemini Pro rejects `function_calling_config` when
   `function_declarations` is empty.** Flash silently accepts the
   same request shape. LEAD synthesis has `tools=None`, so it goes
   through this path. MAF's `_prepare_config` builds the config
   without checking — we override it in `FallbackGeminiChatClient`
   to clear `tool_config` whenever the resolved tool list contains
   no `function_declarations`. Was the parked-Pro-toggle blocker
   for weeks before being root-caused.

2. **`gemini-2.5-flash` does NOT support multi-turn tool-call loops
   with the Code Execution tool**, but `gemini-3.1-flash-lite-preview`
   does. The error is `400 INVALID_ARGUMENT: Tool call context
   circulation is not enabled for models/gemini-2.5-flash`. So
   QUANT and PORTFOLIO (which use `with_code_execution(...)`) cannot
   run on Flash; they need Lite-Preview. RESEARCH and SENTIMENT can
   run on Flash for better instruction-following. **Different agents
   need different models — and MAF gives you no warning about this
   capability matrix until a request fails at runtime.** The fix is
   per-agent model selection (e.g. `RESEARCH_MODEL` env var) rather
   than a single `PRIMARY_MODEL` for everything.

3. **MCP-server schemas include JSON-Schema keys (`$schema`, `$ref`,
   `$defs`) that Gemini's `FunctionDeclaration` validator rejects.**
   The Inderes MCP returns clean schemas in human eyes, but the
   keys get added at protocol level. `_SanitizingMCPTool` strips
   them in the connect step. If you don't have this and your MCP
   server happens to include those keys, every tool call fails
   silently with a schema-validation error that doesn't point at
   the source.

The meta-lesson: **vendor capability matrices are sparse and
undocumented.** Pro vs Flash vs Lite-Preview have different feature
support, and the differences only surface when a specific request
shape hits a specific model. Test each agent on the model you
intend to ship with — don't assume "Flash is just a faster Flash-Lite".

---

## Cross-cutting lessons

### The pillars are inseparable when something breaks

A user reports "the answer is wrong". The cause could be:
- AI: subagent's prompt missing a constraint.
- UI: rendering bug truncated a code block.
- Infra: a tool call timed out and the subagent reported "data not
  available" without flagging it.

You learn to read the trace top-to-bottom every time, because the layer
that broke is rarely the layer that surfaced the breakage. UI bugs mask
AI bugs. Infra issues look like AI issues. AI hallucinations look like
infra issues.

The forensic per-run directory was the single most important
debugging tool I built, exactly because it cuts across all three pillars.

### The parked Pro-toggle is the canonical example

We tried adding a sidebar toggle that would let LEAD use `gemini-2.5-pro`
for synthesis only — bigger model, only one extra LLM call per query, low
cost impact, big quality upside. AI-layer idea, simple in principle.

It blocked on infrastructure: Pro rejects requests with `Function calling
config is set without function_declarations` even though LEAD has
`tools=None`. Three attempts in `_prepare_config()` to clear `tool_config`
when no function declarations are present did not unblock it. Root cause
is in MAF's internal config building — somewhere the
`function_calling_config` is being set without us asking, and Pro is
stricter about it than Flash.

The toggle is parked on `feat/lead-pro-toggle` with debug logging
(`INDERES_DEBUG_GEMINI_CONFIG=1`) for the next investigation pass.

The lesson: **AI-layer features die on infra-layer compatibility issues
all the time, and it's not always cheap to dig out.** Budget for that.

### Documentation is part of the agent loop

Strange but true: keeping `BACKLOG.md`, `CHANGELOG.md`, and this file
current makes the build itself faster. Why?

- The backlog forces a planning pass before each iteration: which item
  am I doing, why, what's the acceptance test?
- The changelog forces a "what actually shipped" reflection at PR time,
  which catches regressions before they accumulate.
- These docs serve as the persistent memory of the project across
  sessions when an LLM-pair-programmer is involved.

Roughly: the docs are where the project's intent lives. Without them, you
end up rediscovering decisions you already made.

### Verify before specifying — your own docs lie

Most "obvious" features turn out smaller (or non-existent) once you
check them against the actual data source. Two examples from one
afternoon:

- **The "stock-split adjustment" bug that wasn't.** A line in
  `data_sources_analysis_2026-05-10.md` flagged the Sampo 1:5 split as
  the cause of a Plotly P/E "cliff" and proposed a 0.5-day chart-side
  normalisation feature. Verified by querying `get-fundamentals`
  directly: prices €7-10 across 2020-2026, sharesTotal 2.5-2.8B for
  the entire window — i.e. **already split-adjusted server-side**.
  The "cliff" was either a misread of the historical data or a false
  memory of an earlier rendering bug. Saved 0.5d of unnecessary work
  by spending 5 minutes calling the tool.

- **The "BUY-only insider filter" that would have hidden signal.** The
  same document proposed `types=["BUY"]` as the SENTIMENT default —
  "order-of-magnitude lift in signal quality". A senior-PM-style push-
  back (from the user, not from me) caught this immediately: sells
  ARE signal, especially big-ticket sells and cluster patterns
  preceding guidance cuts. Filtering them out is cherry-picking. The
  real problem was that SENTIMENT didn't differentiate compulsory
  share-premium grants from voluntary on-market trades. Different
  problem, different fix (taxonomy in the prompt, not a filter at the
  tool boundary).

The pattern: my own docs (data-source analysis, feature menu) made
strong claims that didn't survive contact with the data. **Treat
project documentation as a hypothesis until you've poked it with
the actual tool.** This is especially true for "found a bug" notes
written in passing — the verification step is part of the spec
process, not post-implementation.

Cost-benefit: the MCP tool calls that verified these were free and
took ~5 minutes total. The features they killed would have been ~1
day each. The ratio is so lopsided it should be a default workflow
step.

### Eval baselines decay fast — status audit is a real chore

The Tier 1 eval baseline was recorded 2026-05-09: 12 pass / 4 fail
across 6 cases. **Five days later, all four fail-cases had shipped
fixes** in commits `5e5dea7` (router comparison floor), `80c6fd0`
(päättely schema lift), `2039967` (hard MCP gate broadly), and
`870749a` (fabrication guard). The baseline number was already
obsolete; nobody had re-run the suite to update it.

The trap: when you cite "12 pass / 4 fail" in a planning doc, that
number reads as current state and influences priority calls. In
this case it nearly led me to spend a Wk 2 sprint "fixing" cases
that were already fixed.

Two practices that emerged from catching this:

1. **Status audit doc.** `evals/findings_2026-05-10.md` was written
   purely to map the 2026-05-09 baseline against shipped commits.
   Predicted post-rerun baseline: 7/8 pass. Cheap (no live LLM run
   needed), keeps the BACKLOG honest.

2. **Live re-baseline cadence.** A baseline that doesn't get re-run
   weekly is a baseline that lies. Even more so once a repair-agent
   loop is shipping prompt-only changes nightly. The §10 autonomous
   nightly eval is partly a forcing function for this.

Lesson: **a number with a date is a hypothesis after the date.**
Either re-test or qualify it.

### Prompt length erodes hard gates

The `research.md` prompt has a HARD GATE at the top — explicit, all-
caps, with concrete failure example:

> A response with ZERO MCP tool calls is automatically rejected as
> fabrication and discarded by the orchestration boundary.

Verified working in commit `2039967` ("verified locally with 2
diverse queries, all 6 subagent dispatches made tool calls"). Then
later, a transcript-default workflow case got added to the same
prompt — 36 new lines between the HARD GATE block and the output-
format section. **Fabrication guard started firing again.** Same
prompt, same gate text at the top, but the gate's effective weight
in the model's attention budget had decayed because of the new
content in between.

The fix was not to strengthen the gate text — it was to **delete
30 of those 36 lines** and fold the transcript guidance into a
6-line addition to an existing workflow pattern. Prompt went from
174 lines back to 143 lines. Fabrication stopped.

Three takeaways:

1. **Prompt length is itself part of a hard rule's enforcement.**
   You can write the gate in 100-point bold but if the prompt is
   long, weaker models will still drift past it.
2. **Additive prompt edits compound.** Each PR seems harmless ("just
   adding 5 lines about transcripts"); over a sprint the prompt
   doubles and the model behaves differently. Version-control the
   prompt LENGTH, not just the diff.
3. **When a previously-working gate starts failing, look at what's
   been added since, not at the gate itself.** The gate didn't
   change; everything around it did.

### Branch hygiene needs automation, not discipline

Snapshotted today: 23 stale remote branches. Of those, 22 were
already squash-merged into `main` — the change had landed but the
branch pointer was never deleted. The 23rd (`feat/trading-desk-ui`)
was an early UI iteration that had been entirely superseded by
~12 follow-up commits to `main`. None of the 23 contained unique
work; all could be deleted with zero risk.

The buildup happened over ~7 days of solo work, mostly because
**squash-merge in the GitHub UI doesn't auto-delete the source
branch unless the repo setting is on**. Each merge-then-forget felt
free in the moment; together they made `git branch -a` unreadable.

Two minutes of repo configuration would have prevented all of it:

```
GitHub repo → Settings → Pull Requests
  ☑ Allow squash merging
  ☑ Automatically delete head branches    ← this one
```

Lesson: **the squash-merge workflow is incomplete without auto-
delete.** Set this on day one of any new repo. Discipline alone
won't catch up — the branch list grows monotonically until you do a
big cleanup, and the cleanup is uncomfortable enough that you
delay it (which I did, for a week).

Bonus: when the cleanup did happen, the diagnostic command was a
one-liner:

```bash
git for-each-ref --format='%(refname:short) ahead=%(upstream:track)' refs/heads/
```

Anything `ahead=0` is fully merged. Anything with `ahead=1` is the
squash-merge artefact. The handful with `ahead>1` are the only ones
that need a real review.

---

## Things I'd do differently next time

1. **Build the gist mirror + cron from day one.** I shipped them after
   getting woken up by 401 errors. If I'd known the SSO-session timeout
   pattern earlier, I'd have built the heartbeat first. (Lesson:
   investigate your auth provider's session lifecycle before deploying.)

2. **Add per-claim source provenance earlier.** PR #29 made source links
   clickable in the synthesis footer. But each *claim* in the synthesis
   prose still doesn't carry an inline source. That's a trust gap I
   should have closed sooner — once the synthesis exists, retrofitting
   per-claim provenance requires changes in both the prompt and the
   rendering layer. Doing it on day one would have been cheaper.

3. **Confirm Pro-tier compatibility before committing to lite-only
   architecture.** The fallback chain was built around lite + flash
   because that's what the free tier offers. Now that we want to opt
   into Pro for LEAD, we hit a config-mismatch the fallback wrapper
   wasn't designed for. Even a 30-minute test against Pro at the start
   would have flagged this.

4. **Treat schema sanitization as a first-class concern.** The
   `_SanitizingMCPTool` shim is one of the smallest files in the repo and
   one of the most fragile — it's load-bearing, it's a workaround for a
   Gemini quirk, and if Gemini's validator changes the shim breaks
   silently. I'd add a unit test that asserts the post-`connect()`
   tool schemas have no `$schema`/`$ref`/`$defs` keys, so a regression
   surfaces immediately.

5. **Per-run directories from the very first commit.** I added them in
   week two, and I had to recreate observability for the first week's
   runs by hand. If I rebuilt this from scratch I'd write
   `attach_console_log_handler` + `write_run` before the first agent.

6. **Stand up CI on day one, even if it's only `pytest -q`.** I went
   nine days without CI. The morning's `render_feedback_widget`
   ImportError ran on Streamlit Cloud for ~4 hours before I noticed —
   the symptom was a hot-reload cache issue, but the root cause was
   that no test had ever imported `app.py`, so no signal existed
   anywhere. Adding the minimum CI on Wk 2 surfaced two latent bugs
   immediately (an undefined `DOMAIN_VERBS_EN` reference, two stale
   tests broken by an unrelated refactor). Each of those would have
   cost real debugging time when discovered in production. The cost
   of CI is one yaml file; the value is "regressions land in your CI
   feed, not your user's complaint".

7. **Verify spec claims against the data source before writing code
   to fix them.** Two features in `data_sources_analysis_2026-05-10`
   were specified based on misread data — one for a stock-split bug
   that doesn't exist (server returns adjusted prices), one for a
   filter that would have hidden real signal. Both took 5 minutes to
   verify with a single MCP tool call; both would have cost ~1 day
   of misdirected work each. **The verification step is part of the
   spec process, not a sanity check after.**

8. **Set GitHub auto-delete head branches on day one.** Solo work
   over a week accrued 23 stale remote branches, all squash-merged,
   none cleaned up. The cleanup was zero-risk (one diagnostic, one
   command) but felt big enough to delay. The setting is one
   checkbox; it would have prevented the entire pile.

---

## Lessons from the 2026-05-11/12 debug arc

Three days of intense work compressed three real production lessons
worth distilling.

### Diagnostic logging beats heuristic refinement

The Gemini quota-error bug had a wrong heuristic at its core
(`"429" in str(exc).lower() → fatal`), but I'd been blind to it for
weeks because **the actual exception was never logged**. Five
consecutive failures over 15 minutes left only "falling_back_to_
secondary" in the run logs — no `code`, no `status`, no `quotaId`,
no `message`. Every debugging hour was speculative until I added
`_log_genai_error()` and the very next failure surfaced the real
cause in plain text:

```
'message': 'Your project has exceeded its monthly spending cap'
```

The fix wasn't more careful classification — it was making the
error visible. **Classification was easy ONCE I could see what to
classify**. If I'd built the structured logger first and never
touched the heuristic, the user would have known to raise the spend
cap immediately. The heuristic refinement was secondary.

Generalisation: in any LLM/agent system, if an error path raises
without logging the triggering exception's full structure, that's a
production-priority defect. Substring-matching heuristics on
exception strings are the worst kind of false sense of safety —
they pass tests that use the SAME string but fail silently on every
real-world variant.

### Self-healing > manual recovery

The OAuth gist-pull is a one-shot per process: first call pulls
fresh tokens, every subsequent call uses local cache. When the
auto-relogin cron updates the gist mid-session, the running Cloud
container is blind to the update — requires manual reboot.

This worked OK during my single-user testing because I always
restarted Streamlit after pulling code. But in production it
manifests as **"the app worked yesterday, now it returns
HeadlessAuthError"** for no apparent reason. The auto-relogin cron
succeeded; the tokens are fresh in the gist; the running process is
just stale.

The fix is one if-statement: when local token refresh fails with
`invalid_grant`, re-pull from gist once before raising. ~30 min of
code. I deferred it for weeks because "the user can just reboot" —
but every single time it broke, the symptom looked like a different
bug ("did the cron fail?", "did the secret expire?", "is the gist
wrong?") and the diagnosis took an hour. Self-healing would have
saved cumulative hours over the course of the project.

Generalisation: **the cost of a manual recovery step is paid every
time it triggers, not once.** Self-healing pays its implementation
cost back after ~3 incidents.

### Stale processes are the modal LLM-app dev bug

Through the same week I hit "stale process running old code" twice
under different disguises:

1. **Streamlit local restart forgotten** after pushing the Gemini
   error fix — UI kept showing the old error message because
   `gemini_client.py` was cached in the running Python's
   `sys.modules`.
2. **Streamlit Cloud restart needed** after auto-relogin updated
   the gist — the running container was still using the
   first-boot's gist-pulled (now-stale) tokens.

Both are the same bug shape: Python module imports are global +
cached forever within a process, and Streamlit's auto-reload
mechanism doesn't propagate to deep import-graph changes. Anyone
running iterative agent development hits this weekly.

Mitigations I now reach for first:
- Always check `ps aux | grep streamlit` after a git pull
- Add a `make reload` target that kills and restarts cleanly
- Add a verify-import smoke test that asserts a sentinel string is
  in the loaded code (`assert "per-DAY" in inspect.getsource(...)`)
  before declaring the fix deployed

The 30 seconds spent verifying the import beats 30 minutes
debugging "why isn't the fix working".

---

## Open questions

These are real uncertainties, not rhetorical:

- **When does the AI-layer ceiling actually become the bottleneck?**
  Right now the synthesis is bounded by Flash Lite. But every time I've
  blamed the model, the actual fix has been in the prompt or the data
  flow. Is Pro-tier synthesis a meaningful upgrade, or does my prompt
  hygiene need to improve more before that becomes worth the
  complexity?

- **Is the static fan-out pattern good enough, or is the next big
  unlock dynamic re-planning?** Magentic-One-style dynamic planning is
  appealing on paper. In practice, predictable fan-out has been
  debuggable. I don't know yet whether the queries this system handles
  badly are queries that *would* be helped by re-planning, or queries
  that need better prompts.

- **Where's the line between AI scaffolding and AI logic?** The
  router, the workflow, the fallback wrapper — are these "infrastructure
  for AI" or "part of the AI"? My current taxonomy puts them in the
  AI/infra-overlap. The boundary is fuzzy in a way that probably
  matters for how I think about future work.

- **How many of these lessons are LLM-vendor-specific vs general?** A lot
  of the infra weight comes from Gemini-specific quirks (function-calling
  config, schema validation, Pro/Flash tier mismatches) and Inderes-MCP-
  specific quirks (`prompts/list` not implemented, JSON-Schema metadata
  in tool descriptions). On a different stack the infra mix would shift,
  but the *proportion* of infra-to-AI probably wouldn't.

---

If you're starting your own multi-agent build, I'd guess a quarter of
your time will be on the agents. Plan for the other three quarters.
