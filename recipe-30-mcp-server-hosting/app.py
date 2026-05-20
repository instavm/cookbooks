from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from lib.mcp_stub import router as mcp_router
from lib.ui import landing_page

app = FastAPI(title="MCP Server Hosting")
app.include_router(mcp_router, prefix="/mcp", tags=["mcp"])


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-30-mcp-server-hosting",
        "mcp": "/mcp",
    }


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="MCP Server Hosting",
            slug="recipe-30-mcp-server-hosting",
            tagline="Production MCP server stub with SSE transport.",
            endpoints=[
        ("GET", "/mcp/sse", "MCP SSE stream."),
        ("GET", "/health", "Health check.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

