# InstaVM Cookbooks

A public catalog of apps and experiences you can deploy with `instavm cookbook deploy`.

Each cookbook lives at the repo root:

- `/<slug>/instavm.yaml`
- `/<slug>/Dockerfile`
- `/<slug>/...app files...`

## Local Validation

```bash
python3 scripts/validate_manifests.py
```

## Included Apps

- `hello-fastapi`: a simple FastAPI app with a hello page and health endpoint.
- `neon-city-webgl`: immersive fullscreen WebGL cityscape with procedural towers and a looping robot pedestrian.
- `claude-simple-chatapp`: browser chat for Claude with a React frontend and live conversation threads.
- `openai-agents-js-chat`: streaming browser chat with tool calls, reasoning, and support handoffs.
- `openai-agents-python-research`: research desk that turns a prompt into a concise briefing with supporting notes.
- `google-adk-web-chat`: travel-focused city guide chat for itineraries, neighborhoods, and timing advice.
- `dspy-hosted-chat`: structured DSPy chat that replies with a concise answer and a sharp follow-up question.

## Deploy Contract

`instavm.yaml` drives deploy behavior for both `instavm cookbook deploy` and the future `instavm deploy`.

Required top-level keys:

- `schema_version`
- `slug`
- `title`
- `version`
- `summary`
- `category`
- `runtime`
- `deploy`
- `vm`
- `app`
- `run`
- `secrets`
- `post_deploy_notes`

`deploy.kind` supports:

- `published_snapshot`
- `upload_and_run`

Runtime secrets are injected as environment variables at deploy time. They are not stored in this repo.

## Publishing

First-party cookbook images publish to Docker Hub, and the corresponding public system snapshots use deterministic names like `cookbook/<slug>:<version>`.
