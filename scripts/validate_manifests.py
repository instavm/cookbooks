from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_TOP_LEVEL = {
    "schema_version",
    "slug",
    "title",
    "version",
    "summary",
    "category",
    "runtime",
    "deploy",
    "vm",
    "app",
    "run",
    "secrets",
    "post_deploy_notes",
}
DEVBOX_REQUIRED_TOP_LEVEL = {
    "schema_version",
    "kind",
    "slug",
    "name",
    "version",
    "description",
    "audience",
    "icon",
    "source_repo",
    "vm",
    "build",
    "runtime",
    "terminal",
    "egress",
}
SUPPORTED_SCHEMA_VERSIONS = {1, 2}
SUPPORTED_KINDS = {"service", "cron", "job", "devbox"}
SUPPORTED_DEVBOX_AUDIENCES = {"coding-agent", "chat-agent", "devbox"}
DEVBOX_RUNTIME_KINDS = {"stage_secret", "update", "command"}
ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


def require_mapping(value: object, field_name: str, errors: list[str], manifest_path: Path) -> dict:
    if not isinstance(value, dict):
        errors.append(f"{manifest_path}: {field_name} must be an object")
        return {}
    return value


def require_non_empty_string(value: object, field_name: str, errors: list[str], manifest_path: Path) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{manifest_path}: {field_name} must be a non-empty string")


def validate_env_name(value: object, field_name: str, errors: list[str], manifest_path: Path) -> None:
    if isinstance(value, str) and value.strip() and not ENV_NAME_RE.fullmatch(value):
        errors.append(f"{manifest_path}: {field_name} must match ^[A-Z][A-Z0-9_]{{0,63}}$")


def iter_manifest_paths() -> list[Path]:
    return sorted({*ROOT.glob("*/instavm.yaml"), *ROOT.glob("templates/*/instavm.yaml")})


def validate_devbox_manifest(payload: dict, errors: list[str], manifest_path: Path) -> None:
    audience = str(payload.get("audience") or "").strip()
    if audience not in SUPPORTED_DEVBOX_AUDIENCES:
        errors.append(f"{manifest_path}: audience must be coding-agent, chat-agent, or devbox")

    icon = payload.get("icon")
    require_non_empty_string(icon, "icon", errors, manifest_path)
    if isinstance(icon, str) and icon.strip() and not (manifest_path.parent / icon).exists():
        errors.append(f"{manifest_path}: icon file does not exist: {icon}")

    build = payload.get("build")
    if not isinstance(build, list):
        errors.append(f"{manifest_path}: build must be an array")
    else:
        for index, step in enumerate(build):
            if not isinstance(step, dict):
                errors.append(f"{manifest_path}: build[{index}] must be an object")
                continue
            require_non_empty_string(step.get("command"), f"build[{index}].command", errors, manifest_path)

    runtime = payload.get("runtime")
    if not isinstance(runtime, list):
        errors.append(f"{manifest_path}: runtime must be an array")
    else:
        for index, step in enumerate(runtime):
            if not isinstance(step, dict):
                errors.append(f"{manifest_path}: runtime[{index}] must be an object")
                continue
            step_kind = step.get("kind")
            if step_kind not in DEVBOX_RUNTIME_KINDS:
                errors.append(f"{manifest_path}: runtime[{index}].kind must be stage_secret, update, or command")
            if step_kind in ("update", "command"):
                require_non_empty_string(step.get("command"), f"runtime[{index}].command", errors, manifest_path)
            if step_kind == "stage_secret":
                secrets = step.get("secrets")
                if not isinstance(secrets, list):
                    errors.append(f"{manifest_path}: runtime[{index}].secrets must be an array")
                    continue
                for secret_index, secret in enumerate(secrets):
                    field_name = f"runtime[{index}].secrets[{secret_index}]"
                    if not isinstance(secret, dict):
                        errors.append(f"{manifest_path}: {field_name} must be an object")
                        continue
                    require_non_empty_string(secret.get("name"), f"{field_name}.name", errors, manifest_path)
                    require_non_empty_string(secret.get("env_name"), f"{field_name}.env_name", errors, manifest_path)
                    validate_env_name(secret.get("env_name"), f"{field_name}.env_name", errors, manifest_path)

    terminal = require_mapping(payload.get("terminal"), "terminal", errors, manifest_path)
    for field in ("tmux_session", "command"):
        require_non_empty_string(terminal.get(field), f"terminal.{field}", errors, manifest_path)

    if payload.get("app") is not None:
        app = require_mapping(payload.get("app"), "app", errors, manifest_path)
        port = app.get("port")
        if isinstance(port, bool) or not isinstance(port, int):
            errors.append(f"{manifest_path}: app.port must be an integer")
        if "health_path" in app:
            health_path = app.get("health_path")
            if not isinstance(health_path, str) or not health_path.strip() or not health_path.startswith("/"):
                errors.append(f"{manifest_path}: app.health_path must be a non-empty string starting with /")

    if "egress" in payload:
        egress = require_mapping(payload.get("egress"), "egress", errors, manifest_path)
        allow_domains = egress.get("allow_domains")
        if not isinstance(allow_domains, list):
            errors.append(f"{manifest_path}: egress.allow_domains must be an array")
        else:
            for domain_index, domain in enumerate(allow_domains):
                require_non_empty_string(domain, f"egress.allow_domains[{domain_index}]", errors, manifest_path)

    if "ttl" in payload:
        errors.append(f"{manifest_path}: ttl is not supported")


def main() -> int:
    errors: list[str] = []
    slugs: set[str] = set()

    for manifest_path in iter_manifest_paths():
        try:
            payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{manifest_path}: invalid YAML ({exc})")
            continue

        if not isinstance(payload, dict):
            errors.append(f"{manifest_path}: manifest must be an object")
            continue

        workload_kind = str(payload.get("kind") or "service").strip()
        required_top_level = DEVBOX_REQUIRED_TOP_LEVEL if workload_kind == "devbox" else REQUIRED_TOP_LEVEL

        missing = sorted(required_top_level - set(payload))
        if missing:
            errors.append(f"{manifest_path}: missing fields: {', '.join(missing)}")
            continue

        slug = str(payload.get("slug") or "").strip()
        if not slug:
            errors.append(f"{manifest_path}: slug must be set")
        elif slug != manifest_path.parent.name:
            errors.append(f"{manifest_path}: slug must match directory name {manifest_path.parent.name}")
        elif slug in slugs:
            errors.append(f"{manifest_path}: duplicate slug {slug}")
        else:
            slugs.add(slug)

        schema_version = payload.get("schema_version")
        if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            errors.append(f"{manifest_path}: schema_version must be 1 or 2")

        if workload_kind not in SUPPORTED_KINDS:
            errors.append(f"{manifest_path}: kind must be service, cron, job, or devbox")
        if schema_version == 1 and workload_kind != "service":
            errors.append(f"{manifest_path}: kind can only be service for schema_version 1")

        if workload_kind == "devbox":
            validate_devbox_manifest(payload, errors, manifest_path)
            continue

        deploy = payload.get("deploy")
        kind = deploy.get("kind") if isinstance(deploy, dict) else None
        if kind is None and isinstance(deploy, dict):
            kind = deploy.get("source")
        if kind not in {"published_snapshot", "upload_and_run"}:
            errors.append(f"{manifest_path}: deploy.kind must be published_snapshot or upload_and_run")

        app = require_mapping(payload.get("app"), "app", errors, manifest_path)
        healthcheck_path = app.get("healthcheck_path")
        if not isinstance(healthcheck_path, str) or not healthcheck_path.startswith("/"):
            errors.append(f"{manifest_path}: app.healthcheck_path must start with /")

        secrets = payload.get("secrets")
        if not isinstance(secrets, list):
            errors.append(f"{manifest_path}: secrets must be an array")
        else:
            for index, secret in enumerate(secrets):
                if not isinstance(secret, dict):
                    errors.append(f"{manifest_path}: secrets[{index}] must be an object")
                    continue
                for field in ("name", "prompt", "env_name"):
                    if not isinstance(secret.get(field), str) or not str(secret.get(field)).strip():
                        errors.append(f"{manifest_path}: secrets[{index}].{field} must be a non-empty string")

        if kind == "published_snapshot":
            for field in ("artifact", "build"):
                if field not in payload:
                    errors.append(f"{manifest_path}: {field} is required for published_snapshot")
            artifact = require_mapping(payload.get("artifact"), "artifact", errors, manifest_path)
            if artifact.get("snapshot_visibility") != "public_system":
                errors.append(f"{manifest_path}: artifact.snapshot_visibility must be public_system")
            build = require_mapping(payload.get("build"), "build", errors, manifest_path)
            context = build.get("context")
            dockerfile_name = build.get("dockerfile")
            if isinstance(context, str) and not (manifest_path.parent / context).exists():
                errors.append(f"{manifest_path}: build context does not exist: {context}")
            if isinstance(dockerfile_name, str) and not (manifest_path.parent / dockerfile_name).exists():
                errors.append(f"{manifest_path}: dockerfile does not exist: {dockerfile_name}")
        if kind == "upload_and_run" and "source" not in payload:
            errors.append(f"{manifest_path}: source is required for upload_and_run")
        if kind == "upload_and_run" and "source" in payload:
            source = require_mapping(payload.get("source"), "source", errors, manifest_path)
            include = source.get("include")
            if not isinstance(include, list) or not include:
                errors.append(f"{manifest_path}: source.include must be a non-empty array")
            setup_command = source.get("setup_command")
            if not isinstance(setup_command, str) or not setup_command.strip():
                errors.append(f"{manifest_path}: source.setup_command must be a non-empty string")

        dockerfile = manifest_path.parent / "Dockerfile"
        if kind == "published_snapshot" and not dockerfile.exists():
            errors.append(f"{manifest_path}: Dockerfile is required")

    if errors:
        for error in errors:
            sys.stderr.write(error + "\n")
        return 1

    sys.stdout.write("Manifest validation passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
