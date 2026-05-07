# Implementation notes — redesign handoff

This folder holds the **handoff bundle from Claude Design** (claude.ai/design)
exported on 2026-05-07. It is **not the production code**. The production
implementation lives in `ui/components.py`, `ui/app.py`, and `ui/theme.css` and
borrows from this bundle's design tokens, layout, and component shapes — but
re-implements them in Streamlit-compatible form rather than React.

## What's here

- `README.md` — original handoff README from Claude Design
- `chats/chat1.md` — full conversation transcript (824 lines) showing the
  iteration from current state → final design decisions
- `project/redesign/Agent Desk Redesign.html` — the bundled prototype
  (HTML + inline CSS)
- `project/redesign/{parts,artboards,app,design-canvas}.jsx` — React source
  the bundle is built from
- `project/screenshots/` — design-process screenshots
- `project/uploads/` — screenshots of the current Streamlit UI (user-uploaded
  during the design conversation; treat as input artifacts, not outputs)
- `project/Inderes Multiagent Deck v1-v4.html` — earlier deck designs (not
  related to this UI redesign; kept for archival)

## Design decisions captured here (final)

From `chats/chat1.md`, the user landed on these choices:

1. **Päättely block = Option B**: structured 4-slot grid (`disagree /
   resolution / uncertain / skipped`) driven by LEAD JSON output. Not
   prose. Not `<details>` HTML.
2. **Activity log = side panel on the right** (Claude.ai-style),
   **hidden by default**, opens via clicking the Aikajana strip OR a
   footnote marker in the answer.
3. **Footnote markers** (`¹²³`) inline in answer text, persona-colored.
   Click → opens activity panel scrolled to the relevant tool call.
4. **Live status persistence**: collapses to a single Aikajana strip
   (`AIKAJANA · 21.4s · 2 agenttia ▲ QUANT ■ RESEARCH`) above the answer.
5. **Conflict callout (🔀)**: only renders when LEAD couldn't resolve the
   conflict; otherwise resolved silently inside `Perustelut`.
6. **Aesthetic**: keep terminal-DNA, refine to Bloomberg/IDE level.
   Streamlit-feasibility is a hard constraint.

## Persona palette (NEW — different from current)

| Glyph | Domain | New color | Old color |
|---|---|---|---|
| ◆ | LEAD | `#f5b942` amber | amber (same) |
| ▲ | QUANT | `#5fd28a` green | slate-blue |
| ■ | RESEARCH | `#6aa9ff` blue | dark-green/olive |
| ● | SENTIMENT | `#ff7eb3` pink | teal |
| ✦ | PORTFOLIO | `#c294ff` violet | violet (close) |

## Ink + background scale

| Token | Value | Use |
|---|---|---|
| `--bg-0` | `#0a0b0d` | canvas / page |
| `--bg-1` | `#101216` | card |
| `--bg-2` | `#161a20` | nested card |
| `--bg-3` | `#1d2229` | hover |
| `--line` | `#232831` | borders |
| `--line-2` | `#2f3640` | hovered borders |
| `--ink-0` | `#e6e8eb` | primary text |
| `--ink-1` | `#b6bcc6` | body text |
| `--ink-2` | `#7a828d` | muted |
| `--ink-3` | `#4d5460` | very muted |

## Typography

- Mono primary: **JetBrains Mono** (300/400/500/600/700)
- Sans secondary: **Inter** (400/500/600/700)
- Body size: 13px

## Streamlit translation map

The redesign uses React + flexbox; we translate each piece to Streamlit:

| React element | Streamlit translation |
|---|---|
| `Topbar` | Inject HTML row at page top via `st.markdown(..., unsafe_allow_html=True)` |
| `Sidebar` | Native `st.sidebar` with overridden CSS |
| `Hero` + persona glyph row | Custom HTML block, persona dimming via CSS class |
| `QueryBubble` | Wraps `st.chat_message("user")` content |
| `LiveStatus` | Existing `status.write(...)` calls + new persistent strip |
| `TimelineStrip` | Custom HTML row, `st.button` for click → toggle activity panel |
| `Perustelut` | Existing `render_lead_answer` callout, refreshed CSS |
| `PaattelyB` | Custom HTML 2×2 grid; LEAD prompt emits JSON; UI parses + fills slots |
| `Sources` | Existing source list, refreshed numbering to `[N]` markers |
| `FollowUps` | Existing `render_followup_chips`, refreshed CSS |
| `ActivityPanel` | New: `st.columns([8, 4])` layout when `state.panel_open`; right column renders panel content |
| `AgentCard` | Existing per-subagent card, refreshed to match |
| `ConflictCallout` | New: renders conditionally when `conflicts.json` has unresolved disagreement |
| Footnote `¹²³` | Regex post-process the synthesis text; replace `^N` with `<a class="fn q">N</a>` styled span; `st.button` overlay for click handling |

## Read order for engineers re-implementing

1. `chats/chat1.md` — what the user actually wanted, in their own words
2. `project/redesign/parts.jsx` — reusable components, design tokens via CSS classes
3. `project/redesign/artboards.jsx` — each screen wired up
4. `project/redesign/Agent Desk Redesign.html` — full CSS reference
5. *Skip:* `design-canvas.jsx` (canvas chrome, irrelevant for production)
6. *Skip:* `Inderes Multiagent Deck v*.html` (separate work)
