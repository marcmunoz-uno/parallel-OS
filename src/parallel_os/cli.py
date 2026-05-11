"""Command-line interface for parallel-OS operators (routing dry-run, mesh validation)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from parallel_os import __version__
from parallel_os.mesh import load_mesh, load_mesh_document, select_runtimes
from parallel_os.services import load as load_manifest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_mesh_path(mesh: str | None) -> Path:
    """Resolve mesh file: explicit path, then cwd/services/, then repo services/."""
    if mesh:
        path = Path(mesh).expanduser()
        if path.is_file():
            return path.resolve()
        raise FileNotFoundError(f"mesh file not found: {path}")

    cwd_yaml = Path.cwd() / "services" / "RUNTIME_MESH.yaml"
    if cwd_yaml.is_file():
        return cwd_yaml.resolve()

    root = _repo_root()
    for name in ("RUNTIME_MESH.yaml", "RUNTIME_MESH.template.yaml"):
        candidate = root / "services" / name
        if candidate.is_file():
            return candidate.resolve()

    raise FileNotFoundError(
        "No mesh file found. Copy services/RUNTIME_MESH.template.yaml to "
        "services/RUNTIME_MESH.yaml or pass --mesh PATH."
    )


def _mesh_schema_path() -> Path:
    return _repo_root() / "services" / "schemas" / "runtime-mesh.schema.json"


def cmd_route(args: argparse.Namespace) -> int:
    caps_raw = args.caps.strip()
    if not caps_raw:
        print("error: --caps must list at least one capability", file=sys.stderr)
        return 2

    caps = [c.strip() for c in caps_raw.split(",") if c.strip()]
    if not caps:
        print("error: --caps must list at least one non-empty capability", file=sys.stderr)
        return 2

    mesh_path = resolve_mesh_path(args.mesh)
    mesh = load_mesh(mesh_path)
    selections = select_runtimes(
        mesh,
        required_capabilities=caps,
        max_results=args.max,
    )

    if args.json:
        payload = [
            {
                "service": s.service,
                "runtime": s.runtime,
                "score": s.score,
                "matched_capabilities": s.matched_capabilities,
                "preferred": s.preferred,
                "trust_tier": s.trust_tier,
            }
            for s in selections
        ]
        print(json.dumps({"mesh": str(mesh_path), "caps": caps, "selections": payload}, indent=2))
        return 0

    print(f"mesh: {mesh_path}")
    print(f"required capabilities: {', '.join(caps)}")
    if not selections:
        print("selections: (none — no enabled runtime matched min overlap)")
        return 1

    print("selections:")
    for sel in selections:
        matched = ", ".join(sel.matched_capabilities)
        print(
            f"  - {sel.service}  runtime={sel.runtime!r}  score={sel.score}  "
            f"matched=[{matched}]  preferred={sel.preferred}  trust={sel.trust_tier}"
        )
    return 0


def _validate_schema(doc: dict[str, Any]) -> list[str]:
    schema_path = _mesh_schema_path()
    if not schema_path.is_file():
        return [f"schema file missing (expected {schema_path})"]

    schema = json.loads(schema_path.read_text())
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    return [f"{'/'.join(str(p) for p in err.path)}: {err.message}" for err in errors]


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        mesh_path = resolve_mesh_path(args.mesh)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    issues: list[str] = []

    try:
        doc = load_mesh_document(mesh_path)
    except Exception as exc:
        print(f"error: could not read mesh: {exc}", file=sys.stderr)
        return 1

    issues.extend(_validate_schema(doc))

    try:
        mesh = load_mesh(mesh_path)
    except Exception as exc:
        issues.append(f"structural load failed: {exc}")
        _print_validation_issues(mesh_path, issues)
        return 1

    services_seen: dict[str, int] = {}
    for i, rt in enumerate(mesh.runtimes):
        services_seen[rt.service] = services_seen.get(rt.service, 0) + 1
        if rt.enabled and not rt.capability_tags:
            issues.append(
                f"runtimes[{i}] service={rt.service!r}: enabled but capability_tags is empty"
            )

    dupes = [svc for svc, count in services_seen.items() if count > 1]
    if dupes:
        issues.append(f"duplicate service entries: {', '.join(sorted(dupes))}")

    enabled = mesh.enabled_runtimes()
    if not enabled:
        issues.append("no enabled runtimes — routing will always return empty")

    if args.with_manifest:
        manifest_path = args.manifest or (_repo_root() / "services" / "MANIFEST.yaml")
        manifest_path = Path(manifest_path).expanduser().resolve()
        if not manifest_path.is_file():
            issues.append(f"manifest not found: {manifest_path}")
        else:
            mf = load_manifest(manifest_path)
            manifest_names = {svc.name for svc in mf.services}
            for rt in enabled:
                if rt.service not in manifest_names:
                    issues.append(
                        f"enabled mesh service {rt.service!r} has no matching entry in manifest"
                    )

    if issues:
        _print_validation_issues(mesh_path, issues)
        return 1

    print(f"OK {mesh_path}")
    print(f"  version: {mesh.version}")
    print(f"  runtimes: {len(mesh.runtimes)} ({len(enabled)} enabled)")
    if enabled:
        print("  enabled services:", ", ".join(rt.service for rt in enabled))
    return 0


def _print_validation_issues(mesh_path: Path, issues: list[str]) -> None:
    print(f"validation issues for {mesh_path}:", file=sys.stderr)
    for line in issues:
        print(f"  - {line}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parallel-os",
        description="parallel-OS operator CLI — mesh routing dry-run and validation.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_route = sub.add_parser("route", help="Dry-run capability-based runtime routing.")
    p_route.add_argument(
        "--mesh",
        metavar="PATH",
        default=None,
        help="Mesh YAML (default: services/RUNTIME_MESH.yaml or template in repo)",
    )
    p_route.add_argument(
        "--caps",
        required=True,
        metavar="CAP[,CAP...]",
        help="Comma-separated capability tags (e.g. recon,gpu)",
    )
    p_route.add_argument(
        "--max",
        type=int,
        default=None,
        metavar="N",
        help="Max selections to return (default: mesh routing_defaults.max_fanout)",
    )
    p_route.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON",
    )
    p_route.set_defaults(func=cmd_route)

    p_val = sub.add_parser(
        "validate",
        help="Validate mesh file against JSON Schema and repo consistency checks.",
    )
    p_val.add_argument(
        "--mesh",
        metavar="PATH",
        default=None,
        help="Mesh YAML (default: services/RUNTIME_MESH.yaml or template)",
    )
    p_val.add_argument(
        "--with-manifest",
        action="store_true",
        help="Require each enabled mesh service to exist in services/MANIFEST.yaml",
    )
    p_val.add_argument(
        "--manifest",
        metavar="PATH",
        default=None,
        help="Manifest path when using --with-manifest (default: repo services/MANIFEST.yaml)",
    )
    p_val.set_defaults(func=cmd_validate)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    code = args.func(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()

