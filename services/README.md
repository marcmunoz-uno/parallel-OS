# services/

Concrete runtime implementations live here. Each service is a real, runnable control plane that exposes one OS / one tool surface to AI agents through a typed API + MCP adapter.

The directory `runtimes/` (sibling at repo root) holds **runtime image definitions** — Dockerfiles + tool manifests describing the userland *inside* a container. The directory `services/` holds **the service that wraps that runtime** — control plane, auth, queue, audit, MCP server.

## Why split it this way

A "runtime" answers: *what tools exist inside the container?*
A "service" answers: *how does an agent reach those tools safely?*

A runtime image (e.g. `runtimes/kali/Dockerfile`) can be consumed by more than one service shape (a long-lived service like Kali Factory; an ephemeral spawn-per-call orchestrator; a remote SaaS broker). Keeping them separate means we can swap one without rewriting the other.

## Current services

| Service | Role | Runtime image | Default port | Status |
|---|---|---|---|---|
| [`kali-factory/`](./kali-factory) | OSINT / recon | `kali-factory/recon:latest` | `127.0.0.1:8081` | pre-alpha (vendored as submodule) |
| `gpu-factory` *(external repo)* | CUDA / inference | n/a (host CUDA) | `127.0.0.1:8080` | running on DGX Spark |

See [`MANIFEST.yaml`](./MANIFEST.yaml) for the machine-readable index. Agents should read the manifest, not hardcode service URLs.

## Adding a new service

1. Create or pick the runtime image under `../runtimes/<os>/`.
2. Add the service code as a sibling repo. Either:
   - Vendor it as a git submodule under `services/<name>/` (preferred — keeps it browsable), or
   - Reference it externally with `submodule_path: null` in the manifest.
3. Add an entry in `MANIFEST.yaml` describing host/port/auth/jobs.
4. Make sure each service ships its own `START_HERE_FOR_AGENTS.md` so the agent contract is colocated with the code.

## Updating a vendored service

```bash
git submodule update --remote services/kali-factory
git add services/kali-factory
git commit -m "bump kali-factory to <sha>"
```
