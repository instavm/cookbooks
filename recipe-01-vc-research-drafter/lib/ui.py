"""InstaVM cookbook UI — warm editorial shell, not generic AI dashboard slop."""

from __future__ import annotations

import html
import re
from typing import Iterable

# Fraunces + IBM Plex — matches InstaVM cookbook catalog tone
FONTS = (
    "https://fonts.googleapis.com/css2?"
    "family=Fraunces:opsz,wght@9..144,500;9..144,700&"
    "family=IBM+Plex+Mono:wght@400;500&"
    "family=IBM+Plex+Sans:wght@400;500;600&display=swap"
)

BASE_CSS = """
:root {
  --paper: #f6f2ea;
  --ink: #14110e;
  --muted: #5c564e;
  --line: #d9d0c4;
  --accent: #b84318;
  --accent-soft: #f0ddd4;
  --mono-bg: #ebe4d8;
  --ok: #1f6b4a;
}
* { box-sizing: border-box; }
html { font-size: 16px; }
body {
  margin: 0;
  min-height: 100vh;
  font-family: "IBM Plex Sans", system-ui, sans-serif;
  background-color: var(--paper);
  background-image:
    linear-gradient(rgba(20, 17, 14, 0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(20, 17, 14, 0.025) 1px, transparent 1px);
  background-size: 22px 22px;
  color: var(--ink);
  line-height: 1.55;
}
a { color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 2px; }
a:hover { text-decoration: none; }
.wrap { max-width: 52rem; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }
.kicker {
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 0.75rem;
}
h1 {
  font-family: Fraunces, Georgia, serif;
  font-weight: 500;
  font-size: clamp(1.85rem, 4vw, 2.5rem);
  line-height: 1.15;
  letter-spacing: -0.02em;
  margin: 0 0 0.5rem;
}
.lede { color: var(--muted); font-size: 1.05rem; max-width: 38rem; margin: 0 0 2rem; }
.card {
  border: 1px solid var(--line);
  background: #fffcf7;
  border-radius: 2px;
  padding: 1.25rem 1.35rem;
  margin-bottom: 1rem;
}
.card h2 {
  font-family: Fraunces, Georgia, serif;
  font-size: 1.1rem;
  font-weight: 500;
  margin: 0 0 0.75rem;
}
.endpoint {
  display: grid;
  grid-template-columns: 5.5rem 1fr;
  gap: 0.35rem 1rem;
  padding: 0.55rem 0;
  border-top: 1px solid var(--line);
  font-size: 0.92rem;
}
.endpoint:first-of-type { border-top: 0; padding-top: 0; }
.method {
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--accent);
}
.path { font-family: "IBM Plex Mono", monospace; font-size: 0.82rem; word-break: break-all; }
.desc { color: var(--muted); grid-column: 2; font-size: 0.88rem; }
.pill {
  display: inline-block;
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.68rem;
  padding: 0.2rem 0.45rem;
  border: 1px solid var(--line);
  border-radius: 2px;
  color: var(--muted);
  margin: 0 0.35rem 0.35rem 0;
  background: rgba(255, 252, 247, 0.6);
}
footer {
  margin-top: 2.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--line);
  font-size: 0.8rem;
  color: var(--muted);
}
footer code { font-family: "IBM Plex Mono", monospace; font-size: 0.78rem; }
@media (max-width: 520px) {
  .endpoint { grid-template-columns: 1fr; }
  .desc { grid-column: 1; }
}
"""

OPS_CSS = """
:root {
  --paper: #0e1117;
  --ink: #e6edf3;
  --muted: #8b949e;
  --line: #30363d;
  --accent: #3fb950;
  --accent-soft: #1a2e1f;
}
body { background: var(--paper); color: var(--ink); }
.card { background: #161b22; border-color: var(--line); }
.kicker { color: var(--muted); }
.lede { color: var(--muted); }
.method { color: var(--accent); }
.pill { border-color: var(--line); color: var(--muted); }
.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
  gap: 0.75rem;
  margin: 1.5rem 0;
}
.metric {
  border: 1px solid var(--line);
  background: #161b22;
  padding: 1rem 1.1rem;
  border-radius: 2px;
}
.metric .label {
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}
.metric .value {
  font-family: Fraunces, Georgia, serif;
  font-size: 1.65rem;
  margin-top: 0.35rem;
  color: var(--accent);
}
.metric .value.warn { color: #d29922; }
"""


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def _page(title: str, body: str, *, extra_css: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(title)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="{FONTS}" rel="stylesheet" />
  <style>{BASE_CSS}{extra_css}</style>
</head>
<body>
{body}
</body>
</html>"""


def landing_page(
    *,
    title: str,
    slug: str,
    tagline: str,
    endpoints: Iterable[tuple[str, str, str]],
    pills: Iterable[str] | None = None,
) -> str:
    pill_html = "".join(f'<span class="pill">{_esc(p)}</span>' for p in (pills or ()))
    recipe_no = ""
    if slug.startswith("recipe-"):
        recipe_no = slug.split("-", 2)[1]
    kicker = f"InstaVM Cookbook · #{recipe_no}" if recipe_no.isdigit() else "InstaVM Cookbook"
    rows = ""
    for method, path, desc in endpoints:
        rows += (
            f'<div class="endpoint"><span class="method">{_esc(method)}</span>'
            f'<span class="path">{_esc(path)}</span>'
            f'<span class="desc">{_esc(desc)}</span></div>'
        )
    body = f"""
<div class="wrap">
  <div class="kicker">{_esc(kicker)}</div>
  {pill_html}
  <h1>{_esc(title)}</h1>
  <p class="lede">{_esc(tagline)}</p>
  <div class="card">
    <h2>Endpoints</h2>
    {rows}
  </div>
  <footer>Deploy with <code>instavm deploy .</code> · <code>{_esc(slug)}</code></footer>
</div>"""
    return _page(title, body)


def editorial_preview(
    *,
    title: str,
    meta: str = "",
    body_html: str,
    eyebrow: str = "Preview",
) -> str:
    extra = """
.article { max-width: 40rem; }
.article h1 {
  font-family: Fraunces, Georgia, serif;
  font-size: clamp(1.6rem, 3vw, 2.1rem);
  margin: 0 0 0.75rem;
}
.meta { color: var(--muted); font-size: 0.9rem; margin-bottom: 1.5rem; }
.prose {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 1.05rem;
  line-height: 1.7;
}
.prose pre {
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.82rem;
  background: var(--mono-bg);
  border: 1px solid var(--line);
  padding: 1rem;
  overflow-x: auto;
  white-space: pre-wrap;
  border-radius: 2px;
}
.columns { display: grid; gap: 1.25rem; }
@media (min-width: 720px) { .columns.two { grid-template-columns: 1fr 1fr; } }
"""
    body = f"""
<div class="wrap article">
  <div class="kicker">{_esc(eyebrow)}</div>
  <h1>{_esc(title)}</h1>
  <p class="meta">{_esc(meta)}</p>
  <div class="prose">{body_html}</div>
</div>"""
    return _page(title, body, extra_css=extra)


def distribution_preview(*, title: str, source_url: str, linkedin: str, x_thread: str) -> str:
    body_html = f"""
<p>Source: <a href="{_esc(source_url)}">{_esc(source_url)}</a></p>
<div class="columns two">
  <div><h2 style="font-family:Fraunces,serif;font-size:1.1rem;">LinkedIn</h2><pre>{_esc(linkedin)}</pre></div>
  <div><h2 style="font-family:Fraunces,serif;font-size:1.1rem;">X thread</h2><pre>{_esc(x_thread)}</pre></div>
</div>"""
    return editorial_preview(
        title=title,
        meta="Distribution variants — review before publishing.",
        body_html=body_html,
        eyebrow="Distribution preview",
    )


def ops_dashboard(*, title: str, subtitle: str, metrics: Iterable[tuple[str, str, bool]], slug: str) -> str:
    cards = ""
    for label, value, warn in metrics:
        cls = "value warn" if warn else "value"
        cards += f'<div class="metric"><div class="label">{_esc(label)}</div><div class="{cls}">{_esc(value)}</div></div>'
    body = f"""
<div class="wrap">
  <div class="kicker">Live metrics</div>
  <h1>{_esc(title)}</h1>
  <p class="lede">{_esc(subtitle)}</p>
  <div class="metric-grid">{cards}</div>
  <footer><code>{_esc(slug)}</code> · Stripe test-mode or mock fallback</footer>
</div>"""
    return _page(title, body, extra_css=OPS_CSS)


def replay_gallery(*, title: str, meta: str, frame_names: Iterable[str]) -> str:
    items = "".join(
        f'<figure><img src="/frames/{_esc(name)}" alt="{_esc(name)}" loading="lazy" />'
        f'<figcaption>{_esc(name)}</figcaption></figure>'
        for name in frame_names
    )
    extra = """
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
  gap: 0.85rem;
}
figure {
  margin: 0;
  border: 1px solid var(--line);
  background: #fffcf7;
  padding: 0.45rem;
  border-radius: 2px;
}
img {
  width: 100%;
  height: auto;
  display: block;
  border: 1px solid var(--line);
  background: #111;
}
figcaption {
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.72rem;
  color: var(--muted);
  margin-top: 0.4rem;
}
"""
    body = f"""
<div class="wrap">
  <div class="kicker">Screen replay</div>
  <h1>{_esc(title)}</h1>
  <p class="lede">{_esc(meta)}</p>
  <div class="grid">{items}</div>
</div>"""
    return _page(title, body, extra_css=extra)


def markdown_to_html(text: str) -> str:
    """Minimal safe markdown-ish transform for blog previews."""
    safe = _esc(text)
    safe = re.sub(r"^# (.+)$", r"<h2>\1</h2>", safe, flags=re.M)
    safe = re.sub(r"^## (.+)$", r"<h3>\1</h3>", safe, flags=re.M)
    safe = safe.replace("\n\n", "</p><p>").replace("\n", "<br>\n")
    return f"<p>{safe}</p>"
