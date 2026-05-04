# vscode-microvm runtime is installed by the cookbook setup_command via the
# upstream code-server install script (https://github.com/coder/code-server,
# Apache-2.0). This Dockerfile is kept for the cookbook contract and for users
# who want to publish a private snapshot via `instavm snapshot build`. The
# `upload_and_run` deploy path does NOT actually build or run this image; it
# runs the start_command directly on the host microVM.
FROM debian:bookworm-slim

# code-server version — keep in sync with CS_VERSION in instavm.yaml setup_command.
ARG CS_VERSION=4.96.4

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL https://code-server.dev/install.sh | sh -s -- --version "${CS_VERSION}"

WORKDIR /workspace
EXPOSE 8080

CMD ["code-server", "--bind-addr", "0.0.0.0:8080", "--auth", "password", "--disable-telemetry", "--disable-update-check", "/workspace"]
