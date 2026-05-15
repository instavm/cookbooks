# Deep Research (OpenAI Agents + Exa)

A vault-backed deep-research app for InstaVM cookbooks. It runs a FastAPI UI that streams OpenAI Agents SDK progress events while Exa searches and reads source pages.

## Deploy

```bash
instavm deploy .
```

The cookbook requires an InstaVM org vault with bindings for:

- `api.openai.com` using credential `OPENAI_KEY`
- `api.exa.ai` using credential `EXA_KEY`

The app only sees placeholder strings. The platform egress proxy substitutes the real values on outbound HTTPS requests.

## Runtime

- `GET /health` returns model, upstream hosts, and vault mode.
- `GET /` serves the research UI.
- `POST /api/report` streams Server-Sent Events for phases, tool calls, and the final report.

The UI escapes all streamed text before rendering it and uses security headers to reduce browser-side risk.
