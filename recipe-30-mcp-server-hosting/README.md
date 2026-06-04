# Recipe 30 — MCP Server Hosting

Minimal **SSE + JSON-RPC MCP stub** at `/mcp` for InstaVM-hosted multi-tenant MCP servers.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness |
| GET | `/mcp` | Server metadata |
| GET | `/mcp/sse` | SSE transport handshake |
| POST | `/mcp/message` | JSON-RPC (`initialize`, `tools/list`, `tools/call`) |

## Vault placeholder (production)

Per-tenant OAuth tokens belong in the **InstaVM secret store**, not in the VM environment:

```bash
# Example — proxy injects Authorization on outbound CRM calls
instavm secrets set TENANT_A_CRM_TOKEN "Bearer …"
instavm vault setup .
```

The MCP process calls `https://api.example.com` without setting `Authorization`; InstaVM's egress proxy attaches the tenant token at request time. See cookbook recipe 30 for full FastMCP + share URL provisioning.

## Local test

```bash
cd recipe-30-mcp-server-hosting
pip install -r requirements.txt
pytest -q
```
