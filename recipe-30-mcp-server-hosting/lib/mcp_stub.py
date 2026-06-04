from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter()

TOOLS = [
    {
        "name": "ping",
        "description": "Health check tool for MCP clients.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "echo",
        "description": "Echo a message (vault-injected CRM token not required).",
        "inputSchema": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    },
]


@router.get("")
def mcp_info() -> JSONResponse:
    return JSONResponse(
        {
            "name": "recipe-30-mcp-stub",
            "version": "0.1.0",
            "transports": ["sse"],
            "sse": "/mcp/sse",
            "message": "/mcp/message",
        }
    )


@router.get("/sse")
async def mcp_sse() -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        yield "event: endpoint\ndata: /mcp/message\n\n"
        init = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        yield f"event: message\ndata: {json.dumps(init)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/message")
async def mcp_message(request: Request) -> JSONResponse:
    body = await request.json()
    method = body.get("method", "")
    req_id = body.get("id")

    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "recipe-30-mcp-stub", "version": "0.1.0"},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = body.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "ping":
            result = {"content": [{"type": "text", "text": "pong"}]}
        elif name == "echo":
            result = {"content": [{"type": "text", "text": str(args.get("message", ""))}]}
        else:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Unknown tool"}},
                status_code=400,
            )
    else:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unsupported: {method}"}},
            status_code=400,
        )

    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": result})
