"""Minimal landing page for the orchestrator service."""

from __future__ import annotations


def landing_page(*, webhook_path: str, worker_count: int) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Claude Managed Agents — InstaVM Sandbox</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; max-width: 720px;
            margin: 3rem auto; padding: 0 1.25rem; color: #111; line-height: 1.6; }}
    code {{ background: #f4f4f5; padding: .15rem .4rem; border-radius: .35rem; }}
    .pill {{ display: inline-block; background: #eef2ff; color: #3730a3;
             padding: .2rem .6rem; border-radius: 999px; font-size: .8rem; }}
    h1 {{ margin-bottom: .25rem; }}
    .muted {{ color: #6b7280; }}
  </style>
</head>
<body>
  <span class="pill">InstaVM · Claude Managed Agents</span>
  <h1>Self-hosted sandbox orchestrator</h1>
  <p class="muted">Anthropic runs the agent loop. Tool calls execute inside
  per-session InstaVM microVMs. Provider credentials are injected at the egress
  boundary from the org vault — the worker never sees a naked API key.</p>
  <ul>
    <li>Webhook endpoint: <code>{webhook_path}</code> (subscribe to
        <code>session.status_run_started</code>)</li>
    <li>Health: <code>/health</code></li>
    <li>Active workers: <code>{worker_count}</code> — see <code>/workers</code></li>
  </ul>
</body>
</html>"""
