"""Runtime mesh specification and routing helpers.

This module lets one agent reason about multiple runtime services without
hardcoding specific OS selections in code. Operators define runtime entries in a
YAML file; the selector picks the best runtime(s) for required capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from typing import Any

import yaml

_ENV_REF = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}")


def _expand_env(value: Any) -> Any:
    """Resolve `${VAR}` and `${VAR:-default}` references inside values."""
    if isinstance(value, str):
        def repl(match: re.Match[str]) -> str:
            var, default = match.group(1), match.group(2)
            return os.environ.get(var, default if default is not None else "")

        return _ENV_REF.sub(repl, value)
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    return value


@dataclass
class RuntimeProfile:
    """Operator-declared runtime/service profile in the mesh."""

    service: str
    runtime: str
    enabled: bool
    capability_tags: set[str] = field(default_factory=set)
    trust_tier: str = "trusted"
    max_parallel_jobs: int = 1
    preferred: bool = False
    notes: str = ""


@dataclass
class RoutingDefaults:
    """Default routing behavior for the mesh."""

    max_fanout: int = 2
    min_capability_overlap: int = 1


@dataclass
class RuntimeMesh:
    """Top-level runtime mesh specification."""

    version: int
    defaults: RoutingDefaults
    runtimes: list[RuntimeProfile]

    def get(self, service: str) -> RuntimeProfile:
        for runtime in self.runtimes:
            if runtime.service == service:
                return runtime
        raise KeyError(f"no runtime profile for service {service!r}")

    def enabled_runtimes(self) -> list[RuntimeProfile]:
        return [runtime for runtime in self.runtimes if runtime.enabled]


@dataclass
class RuntimeSelection:
    """A scored candidate from routing decisions."""

    service: str
    runtime: str
    score: int
    matched_capabilities: list[str]
    preferred: bool
    trust_tier: str


def _coerce_defaults(raw: dict[str, Any] | None) -> RoutingDefaults:
    if raw is None:
        return RoutingDefaults()
    return RoutingDefaults(
        max_fanout=int(raw.get("max_fanout", 2)),
        min_capability_overlap=int(raw.get("min_capability_overlap", 1)),
    )


def _coerce_runtime(raw: dict[str, Any]) -> RuntimeProfile:
    return RuntimeProfile(
        service=raw["service"],
        runtime=raw["runtime"],
        enabled=bool(raw.get("enabled", True)),
        capability_tags=set(raw.get("capability_tags", [])),
        trust_tier=str(raw.get("trust_tier", "trusted")),
        max_parallel_jobs=int(raw.get("max_parallel_jobs", 1)),
        preferred=bool(raw.get("preferred", False)),
        notes=str(raw.get("notes", "")).strip(),
    )


def load_mesh_document(mesh_path: str | Path) -> dict[str, Any]:
    """Load mesh YAML and expand `${VAR}` / `${VAR:-default}` references."""
    raw = yaml.safe_load(Path(mesh_path).read_text())
    if not isinstance(raw, dict):
        raise ValueError("mesh file must parse to a mapping at the top level")
    expanded = _expand_env(raw)
    if not isinstance(expanded, dict):
        raise ValueError("mesh file must expand to a mapping at the top level")
    return expanded


def load_mesh(mesh_path: str | Path) -> RuntimeMesh:
    """Load a runtime mesh spec from YAML."""
    raw = load_mesh_document(mesh_path)
    return RuntimeMesh(
        version=int(raw.get("version", 1)),
        defaults=_coerce_defaults(raw.get("routing_defaults")),
        runtimes=[_coerce_runtime(r) for r in raw.get("runtimes", [])],
    )


def select_runtimes(
    mesh: RuntimeMesh,
    *,
    required_capabilities: list[str],
    max_results: int | None = None,
) -> list[RuntimeSelection]:
    """Select the best runtime profiles for a task.

    Scores are intentionally simple and explainable:
      - +10 points per capability match
      - +2 points if marked preferred
      - +1 point if trust tier is "trusted"
    """
    if not required_capabilities:
        raise ValueError("required_capabilities must contain at least one capability")

    required = set(required_capabilities)
    candidates: list[RuntimeSelection] = []
    min_overlap = mesh.defaults.min_capability_overlap

    for runtime in mesh.enabled_runtimes():
        matched = sorted(required.intersection(runtime.capability_tags))
        overlap = len(matched)
        if overlap < min_overlap:
            continue

        score = overlap * 10
        if runtime.preferred:
            score += 2
        if runtime.trust_tier == "trusted":
            score += 1

        candidates.append(
            RuntimeSelection(
                service=runtime.service,
                runtime=runtime.runtime,
                score=score,
                matched_capabilities=matched,
                preferred=runtime.preferred,
                trust_tier=runtime.trust_tier,
            )
        )

    candidates.sort(
        key=lambda item: (item.score, len(item.matched_capabilities), item.service),
        reverse=True,
    )
    limit = max_results if max_results is not None else mesh.defaults.max_fanout
    return candidates[:limit]
