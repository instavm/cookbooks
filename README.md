# InstaVM Cookbooks

Public starter apps for `instavm cookbook deploy`.

Each cookbook lives at the repo root:

- `/<slug>/instavm.yaml`
- `/<slug>/Dockerfile`
- `/<slug>/...app files...`

## Local Validation

```bash
python3 scripts/validate_manifests.py
```

## Included Starters

- `hello-fastapi`: zero-key FastAPI smoke test for VM create, service start, and public share verification.
- `claude-simple-chatapp`: React + Express chat UI adapted from the Claude Agent SDK demos repo.
- `openai-agents-js-chat`: Next.js streaming chat UI adapted from the OpenAI Agents JS AI SDK UI example.
- `openai-agents-python-research`: FastAPI research memo app inspired by the OpenAI Agents Python research examples.
- `google-adk-web-chat`: browser-first Google ADK starter derived from the minimal ADK example shape.
- `dspy-hosted-chat`: DSPy chat starter using a hosted OpenAI-compatible endpoint instead of local CPU-only inference.

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

Runtime secrets are injected as environment variables only. They are not stored in the cookbook repo.

## Publishing

First-party cookbook images publish to Docker Hub, and the corresponding public system snapshots use deterministic names like `cookbook/<slug>:<version>`.
