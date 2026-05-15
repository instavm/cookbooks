from __future__ import annotations

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
SUPPORTED_SCHEMA_VERSIONS = {1, 2}
SUPPORTED_KINDS = {"service", "cron", "job"}


def require_mapping(value: object, field_name: str, errors: list[str], manifest_path: Path) -> dict:
    if not isinstance(value, dict):
        errors.append(f"{manifest_path}: {field_name} must be an object")
        return {}
    return value


def main() -> int:
    errors: list[str] = []
    slugs: set[str] = set()

    for manifest_path in sorted(ROOT.glob("*/instavm.yaml")):
        try:
            payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{manifest_path}: invalid YAML ({exc})")
            continue

        if not isinstance(payload, dict):
            errors.append(f"{manifest_path}: manifest must be an object")
            continue

        missing = sorted(REQUIRED_TOP_LEVEL - set(payload))
        if missing:
            errors.append(f"{manifest_path}: missing fields: {', '.join(missing)}")
            continue

        slug = str(payload.get("slug") or "").strip()
        if not slug:
            errors.append(f"{manifest_path}: slug must be set")
        elif slug in slugs:
            errors.append(f"{manifest_path}: duplicate slug {slug}")
        else:
            slugs.add(slug)

        schema_version = payload.get("schema_version")
        if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            errors.append(f"{manifest_path}: schema_version must be 1 or 2")

        workload_kind = str(payload.get("kind") or "service").strip()
        if workload_kind not in SUPPORTED_KINDS:
            errors.append(f"{manifest_path}: kind must be service, cron, or job")
        if schema_version == 1 and workload_kind != "service":
            errors.append(f"{manifest_path}: kind can only be service for schema_version 1")

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
