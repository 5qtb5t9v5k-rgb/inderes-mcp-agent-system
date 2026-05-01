"""Diagnostic: probe each layer separately so we know where it hangs.

Run:  python scripts/diag.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()


def step(label: str) -> float:
    print(f"  ▸ {label}…", flush=True)
    return time.time()


def done(t0: float) -> None:
    print(f"    ✓ {time.time()-t0:.2f}s", flush=True)


async def probe_gemini():
    print("\n[1] Gemini API direct call (no MAF, no MCP):")
    t = step("import google.genai")
    from google import genai
    done(t)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("    ✗ GEMINI_API_KEY missing — set it in .env")
        return False

    t = step(f"client = genai.Client(api_key=...)")
    client = genai.Client(api_key=api_key)
    done(t)

    primary = os.environ.get("PRIMARY_MODEL", "gemini-3.1-flash-lite-preview")
    fallback = os.environ.get("FALLBACK_MODEL", "gemini-2.5-flash")

    for m in [primary, fallback]:
        t = step(f"models.generate_content model={m!r} prompt='hi'")
        try:
            r = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=m,
                    contents="say 'ok' in one word",
                ),
                timeout=20,
            )
            done(t)
            print(f"    response: {r.text.strip()[:60]!r}")
        except asyncio.TimeoutError:
            print(f"    ✗ TIMEOUT after 20s — model {m} did not respond")
            return False
        except Exception as exc:
            print(f"    ✗ ERROR: {type(exc).__name__}: {str(exc)[:200]}")
            if m == primary:
                print(f"    (will still try fallback)")
                continue
            return False
    return True


async def probe_mcp_oauth():
    print("\n[2] OAuth discovery (no browser yet):")
    t = step("GET https://mcp.inderes.com/.well-known/oauth-protected-resource")
    from inderes_agent.mcp.oauth import _discover, _load_tokens
    try:
        d = _discover("https://mcp.inderes.com")
        done(t)
        print(f"    auth:  {d.authorization_endpoint}")
        print(f"    token: {d.token_endpoint}")
    except Exception as exc:
        print(f"    ✗ ERROR: {exc}")
        return False

    cached = _load_tokens()
    if cached and cached.is_fresh:
        print(f"    cached token present, expires in "
              f"{int(cached.expires_at - time.time())}s — OAuth flow will be skipped")
    else:
        print("    no cached token — first MCP call will open browser")
    return True


async def main():
    print("=" * 60)
    print("inderes-research-agent — diagnostic")
    print("=" * 60)

    if not await probe_gemini():
        print("\n→ Stop. Gemini path is broken; fix that first.")
        sys.exit(1)

    if not await probe_mcp_oauth():
        print("\n→ Stop. MCP discovery is broken; fix that first.")
        sys.exit(1)

    print("\n✓ Both layers reachable. Try a real query now:")
    print("  python -m inderes_agent \"What's Konecranes' P/E?\"\n")


if __name__ == "__main__":
    asyncio.run(main())
