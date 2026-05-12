# Deploying to Streamlit Cloud

Step-by-step guide for hosting the Streamlit app publicly on
[Streamlit Community Cloud](https://share.streamlit.io) with a shared password
and a daily query cap.

This is **single-user, public-app, password-gated** deployment (Path C in the
project's planning notes). The deployed app uses your Inderes Premium token and
your Gemini API key — visitors authenticate by knowing the shared password.

> **Why not multi-user?** Per-user OAuth would need Inderes to register the
> deployed URL as an approved redirect URI in their Keycloak. That's a
> coordination conversation that's outside the scope of a personal project.

## Prerequisites

- The repo is pushed to GitHub (public or private both work).
- You've successfully run the agent **locally** at least once, so
  `~/.inderes_agent/tokens.json` exists.
- You have a Google AI Studio API key with billing enabled.
- You have a Streamlit Community Cloud account (free, sign in with GitHub).

## 1. Set up a Gemini budget cap

Worst case, your password leaks. To cap the damage:

1. Go to [Google Cloud Console → Billing → Budgets & alerts](https://console.cloud.google.com/billing/budgets).
2. Create a budget on the project linked to your Gemini API key.
3. Set the cap to something you're comfortable with — e.g. `$20/month`.
4. Enable email alerts at 50%, 90%, 100%.

The Gemini API will start refusing requests when the budget is exceeded, so
runaway costs are bounded.

## 2. Capture your OAuth tokens

```bash
# from a fresh local clone with venv active
python -m inderes_agent "What's Konecranes' P/E?"
# (browser opens, you log in to Inderes, query completes)

cat ~/.inderes_agent/tokens.json
```

Copy the JSON output. It will look like:

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzUxMiIs...",
  "expires_at": 1748600000.123,
  "token_endpoint": "https://sso.inderes.fi/auth/realms/Inderes/protocol/openid-connect/token",
  "client_id": "inderes-mcp"
}
```

The `refresh_token` lasts roughly 30 days. After that, repeat this step and
update the secret (see §6 below).

## 3. Push the code

```bash
git push origin main
```

Make sure `requirements.txt` is in the root (the cloud-deploy PR adds it).
Streamlit Cloud will auto-detect it.

## 4. Create the Streamlit Cloud app

1. Go to [share.streamlit.io](https://share.streamlit.io).
2. **New app** → connect to your GitHub.
3. Select:
   - **Repository:** `<your-username>/<your-repo>`
   - **Branch:** `main`
   - **Main file path:** `ui/app.py`
4. **Advanced settings:**
   - Python version: `3.13` — **important**. Streamlit Cloud defaults to 3.14,
     which `agent-framework-gemini` (still in alpha) doesn't support yet.
     The repo also ships a `runtime.txt` pinning Python 3.13, so this should
     be enforced automatically.
   - Sharing: **Public** (this is Path C)
5. Click **Deploy**.

The first build takes 5–10 minutes — Streamlit installs every dependency.
You'll see the build log streaming. The app will fail on first deploy
because secrets aren't set yet — that's fine, we configure them next.

## 5. Configure secrets

In the deployed app's settings (gear icon → "Secrets"), paste the following
TOML:

```toml
# Required
GEMINI_API_KEY = "AIza..."

INDERES_OAUTH_TOKENS_JSON = """
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzUxMiIs...",
  "expires_at": 1748600000.123,
  "token_endpoint": "https://sso.inderes.fi/auth/realms/Inderes/protocol/openid-connect/token",
  "client_id": "inderes-mcp"
}
"""

# Path C: gate access with a shared password.
# Optional — if you don't set APP_PASSWORD, the app is open to anyone with
# the URL. Skip the password if you've set a Gemini budget cap and don't
# have auto-recharge enabled in Google AI Studio (worst case is bounded
# by what you've prepaid).
APP_PASSWORD = "<a strong 12+ character password>"

# Optional cap to limit damage if password leaks
DAILY_QUERY_CAP = "50"

# Cloud filesystem is ephemeral. Use /tmp for caches.
INDERES_AGENT_CACHE = "/tmp/inderes_agent"

# Tells the agent to refuse falling back to the interactive OAuth flow if the
# token can't be refreshed — surfaces a clear error instead of hanging.
STREAMLIT_RUNTIME_ENV = "cloud"
```

Save. Streamlit will restart the app automatically.

## 6. Test the deployment

1. Open the app's public URL.
2. Enter your `APP_PASSWORD`.
3. Run a simple query: `Mikä on Konecranesin P/E?`.
4. Expected:
   - First query: ~10–20 s (cold start), then ~5–15 s for subsequent queries.
   - Sidebar shows "Daily quota: 1 / 50 queries today".
   - Subagent trace expander works.

If you see `OAuth flow requires opening a browser…`, your refresh token has
expired or the secret is malformed. Repeat §2 (capture tokens locally) and
update the `INDERES_OAUTH_TOKENS_JSON` secret.

## 6.5. Optional: durable token storage via GitHub Gist

Without this, you'll hit the operational gotcha at the bottom of this doc:
Streamlit Cloud restarts the container periodically, the in-container
`tokens.json` is wiped, the app bootstraps the original (now-rotated)
refresh token from the secret, Inderes' Keycloak rejects it as
`invalid_grant`, and the app dies until you paste fresh tokens.

The fix is to mirror `tokens.json` to a private GitHub gist on every
refresh. The container reads from the gist on startup (always gets the
freshest tokens) and writes back on every refresh (preserves the new
rotated token across restarts).

### Setup (one-time, ~3 minutes)

1. **Create a private gist** at https://gist.github.com/ with one file
   named exactly `tokens.json`. Paste the same JSON you put in
   `INDERES_OAUTH_TOKENS_JSON` as the initial content. Click "Create
   secret gist". Copy the gist ID from the URL — it's the hex string
   after your username, e.g. `https://gist.github.com/you/abc123def456…`
   → ID is `abc123def456…`.

2. **Create a fine-grained PAT** at https://github.com/settings/tokens?type=beta
   - Repository access: doesn't matter (gists aren't repos)
   - Account permissions → **Gists: Read and write**
   - Expiration: 90+ days (you'll need to rotate when this expires too,
     but ~3× less often than refresh tokens)
   - Click Generate, copy the token starting with `github_pat_`.

3. **Add two more secrets** to your Streamlit Cloud app
   (`Settings → Secrets`):

   ```toml
   INDERES_TOKENS_GIST_ID = "abc123def456..."
   INDERES_TOKENS_GH_TOKEN = "github_pat_..."
   ```

4. **Reboot the app**. It'll read from the gist instead of the static
   env-var, and start writing back to the gist on every token refresh.

That's it. The `INDERES_OAUTH_TOKENS_JSON` secret stays as a fallback
for the first cold start before gist content is verified.

## 6.6. Optional: auto-relogin via headless Playwright (recommended)

The gist mirror in §6.5 only solves the refresh-token-rotation race;
it does **not** solve the upstream `SSO Session Max` cap. Inderes'
Keycloak instance enforces a hard ceiling on every session
(empirically ~10 hours) — beyond which the refresh-token chain is
permanently dead and no amount of cron refreshing recovers. Manual
re-auth via browser is the only path back.

The auto-relogin sidecar
([`inderes-mcp-auto-relogin`](https://github.com/5qtb5t9v5k-rgb/inderes-mcp-auto-relogin),
private repo) automates this: GitHub Actions cron runs Playwright
headless Chromium twice per day (02:00 + 17:00 UTC, deliberately
outside Helsinki working hours), performs a full Keycloak login with
your username + password, captures the OAuth callback URL via
`page.on("request", listener)`, exchanges the auth code for fresh
tokens, and pushes them to the same gist this app reads from.

Setup is a one-time fork-and-configure of that sidecar repo. See its
README for the workflow secrets list (`INDERES_USERNAME` +
`INDERES_PASSWORD` + the same `INDERES_TOKENS_GIST_ID` +
`INDERES_TOKENS_GH_TOKEN` you set in §6.5). The whole thing takes
~15 minutes to wire up.

**Operational note:** the running Streamlit Cloud container pulls
from the gist exactly once per process boot. Auto-relogin pushing
fresh tokens to gist mid-session does NOT propagate to a running
container — you'll need to **manually reboot the app** from
`share.streamlit.io → Manage app → Reboot app` to pick up the new
tokens. Self-healing gist re-pull on `invalid_grant` is BACKLOG'd in
the main repo's §4 tech-debt section.

## 6.7. Optional: Yahoo Finance MCP for international coverage

This app uses two MCPs side-by-side when configured:

- **Inderes MCP** — Finnish-equity primary source (covered in §6
  above).
- **Yahoo Finance MCP** ([`yahoo-finance-mcp`](https://github.com/5qtb5t9v5k-rgb/yahoo-finance-mcp),
  MIT-public sidecar) — international ticker coverage + Q-fresh
  BVPS + live price + OHLCV history + news + institutional holders.

To enable Yahoo for Cloud:

1. Deploy the sidecar somewhere reachable from Streamlit Cloud's
   network (typically Fly.io or Modal — see the sidecar repo's
   README for the Fly.io recipe; ~15 min, $0 idle on Fly's
   auto-stop machines).
2. Add to Streamlit Cloud secrets:

   ```toml
   YAHOO_MCP_URL = "https://yahoo-mcp-jr.fly.dev/mcp"
   ```

3. Reboot the app. Agents pick up Yahoo tools automatically per the
   partitioning in `src/inderes_agent/mcp/yahoo_client.py`.

If `YAHOO_MCP_URL` is unset, the agents silently skip Yahoo and
operate Inderes-only — no errors, no degradation. The toggle is
strictly additive. **For local dev** point at `http://localhost:8000/mcp`
after running `make serve` in the yahoo-finance-mcp repo.

## 7. Day-to-day operations

| Frequency | Task |
|---|---|
| **Never** (with gist setup + auto-relogin sidecar) | Token refresh + re-auth both happen automatically. Manual intervention needed only if the auto-relogin cron breaks (check its GitHub Actions tab weekly). |
| **Once a month** (without gist setup) | Capture fresh tokens locally (refresh tokens last ~30 days), update `INDERES_OAUTH_TOKENS_JSON` secret. The app will auto-restart on secret change. |
| **Every 10h** (without auto-relogin) | Inderes Keycloak SSO Session Max hits, manual re-auth via `bash scripts/relogin.sh` locally → push tokens to gist. The auto-relogin sidecar (§6.6) automates this. |
| **As needed** | Rotate `APP_PASSWORD` if it's been shared too widely. |
| **Weekly** | Glance at the Google AI Studio dashboard for the past week's spend, sanity-check it. **Check the project's monthly spend cap** at https://ai.studio/spend — a cap hit looks identical to a daily quota error in the API response. |
| **As needed** | Check the recent runs in the sidebar — if you see queries you didn't expect, the password may have leaked. |

## 8. Sharing the URL

The deployed app's URL is something like
`https://your-repo-name.streamlit.app`. Share it with the password — recipients
just open the URL and type the password.

A useful safety net is to make the password **time-bound**: tell people you'll
rotate it on the 1st of each month. Easy to enforce, easy to reset.

## Operational gotchas

- **Container restarts.** Streamlit Cloud restarts containers periodically
  (resource limits, redeploys). On restart, the in-container token cache
  resets to whatever's in `INDERES_OAUTH_TOKENS_JSON`. If a refresh happened
  and the new token wasn't yet saved to a persistent store, the next run
  will refresh again from the original — and Keycloak will reject it as
  `invalid_grant` because rotated refresh tokens are single-use. Use the
  gist setup in §6.5 to make this a non-issue.
- **Daily query cap resets** when the container restarts (counter is in
  `/tmp`). Worst case, an attacker triggers restarts to reset the cap. In
  practice, Streamlit Cloud doesn't expose a public restart trigger, so this
  is mostly theoretical.
- **Logs.** Streamlit Cloud retains stdout/stderr for the running container.
  Use them for debugging; they don't persist `~/.inderes_agent/runs/` across
  restarts.

## Reverting to local-only

If you want to take the public app down:

1. In Streamlit Cloud → app settings → **Delete app**.
2. The repo continues to work for local development with no changes — the
   cloud-specific code paths are dormant when env vars aren't set.
