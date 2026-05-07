# parallel-OS

**Multi-OS execution framework for AI agents.** An agent spawns on a host machine and gains access to the userland of any operating system it needs — Kali for OSINT tooling, Arch for AUR packages, Alpine for minimal services, NixOS for reproducibility, Ubuntu for general Linux. Each runtime is wrapped as an MCP server exposing its native tools through a structured interface.

```
                          ┌─────────────────────────┐
                          │   AI agent (any model)  │
                          └────────────┬────────────┘
                                       │ MCP
        ┌──────────────────────────────┼──────────────────────────────┐
        │                              │                              │
   ┌────▼─────┐                  ┌─────▼─────┐                 ┌──────▼──────┐
   │  Kali    │                  │  Ubuntu   │                 │   NixOS     │
   │  runtime │                  │  runtime  │                 │   runtime   │
   │  (docker)│                  │  (docker) │                 │   (docker)  │
   └──────────┘                  └───────────┘                 └─────────────┘
   amass, mitmproxy,             apt, gcc, build              nix-build,
   whatweb, nuclei,              tooling, debugging           reproducible
   linkfinder, ...               ...                          environments
```

## The problem

A single AI agent today is locked to whatever operating system it was deployed on. If an agent running on macOS needs `nmap` with current detection signatures, it has to either:
- Settle for a stale Homebrew port, or
- SSH to a remote box and lose tool composition, or
- Use whatever MCP servers happen to expose what it needs

This is a structural limitation. Different operating systems are good at different things. A reconnaissance task wants Kali. A reproducible build wants NixOS. A penetration test of a Windows network wants Windows. An ML pipeline wants Ubuntu with CUDA. The agent shouldn't care; it should ask for what it needs.

## The thesis

Wrap each operating system's userland in an MCP server. Containerize it. Let agents spawn the runtimes they need on demand, call tools through MCP, and tear down when done.

Agents become **OS-polyglot** — they pick the right tool surface for the job rather than working around their host's limitations.

## What this isn't

- **Not a VM orchestrator** — Docker only, for spawn-time and resource efficiency. Kernel-shared isolation is acceptable for trusted-agent workloads. If you need stronger isolation, swap the backend.
- **Not a security tool** — though Kali is one of the supported runtimes, the framework itself is OS-agnostic. Use cases include build farms, ML pipelines, multi-distro testing, and agent-driven recon.
- **Not RPC-over-HTTP** — agents talk to runtimes via MCP, the same protocol they use for any other tool. No new protocol to learn.

## Architecture (one-page version)

1. **Host orchestrator** runs on a fat box (DGX Spark, EC2, bare metal). Manages container lifecycle, resource quotas, network bridges.
2. **Runtime images** are Docker images per OS, each pre-installed with an MCP server exposing that OS's tools. Built once, cached locally.
3. **Per-runtime MCP server** translates MCP tool calls into shell commands inside the container. Allowlists per runtime constrain what tools an agent can invoke.
4. **Agent SDK** lets agents request a runtime (`Runtime.spawn("kali")`), receive a connection, and call tools through it.
5. **Policy layer** enforces what runtimes/tools are available, time-limits per call, audit logging.

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the full design.

## Why a DGX Spark is the natural host

- ARM Linux, fat compute, integrated 200 GbE — ideal for hosting many concurrent agent runtimes
- Plenty of memory bandwidth for container churn
- Single physical box → reduces network hops between agent and runtime
- Plays nicely with NVIDIA Container Toolkit if any runtime needs GPU access

But the host is interchangeable. Anything running Docker + Python 3.11+ works.

## Included services

parallel-OS is the **parent package** that consolidates concrete runtime services. Each service is a real, runnable control plane wrapping one OS / one tool surface. They are vendored as git submodules under `services/` so an AI agent can browse the entire surface from a single repo.

| Service / runtime | Role | Default port | Status |
|---|---|---|---|
| [`services/kali-factory/`](./services/kali-factory) | OSINT / recon (Kali Linux userland, allowlisted) | `127.0.0.1:8081` | pre-alpha |
| `gpu-factory` *(external)* | CUDA / GPU inference on the DGX Spark | `127.0.0.1:8080` | running |
| [`runtimes/python-ml/`](./runtimes/python-ml) | Python 3.12 + numpy / pandas / scipy / scikit-learn / torch / transformers / polars / duckdb | *image-only* | image ready, service wrapper planned |

The machine-readable index is [`services/MANIFEST.yaml`](./services/MANIFEST.yaml). Agents should read the manifest, not hardcode service URLs. See [`START_HERE_FOR_AGENTS.md`](./START_HERE_FOR_AGENTS.md) for the consolidated agent contract.

```python
import parallel_os

m = parallel_os.load()                   # parses services/MANIFEST.yaml
kali = m.get("kali-factory")
print(kali.api.base_url)                 # http://127.0.0.1:8081
print(kali.jobs)                         # ['kali_probe', 'subdomain_enum', ...]
token = kali.read_token()                # reads .secrets/api_token (chmod 0600)
```

## Abstraction model and methodology (explicit contract)

This section defines exactly how `parallel-OS` is intended to work across all runtimes, including external services such as `gpu-factory`.

### 1) Core abstraction

`parallel-OS` is a **runtime control plane**, not a single runtime implementation.

- A **runtime** is an MCP-addressable tool surface backed by one OS userland (containerized or external service).
- A **service** is the concrete control API that owns job execution for that runtime.
- The **manifest** is the source of truth that maps service IDs to endpoints, capabilities, auth material, and job names.
- The **SDK** is a thin resolver that loads manifest entries and gives agents stable handles (`m.get("kali-factory")`).

In short: `parallel-OS` standardizes discovery, policy, and invocation; each runtime service standardizes execution for its OS/tool domain.

### 2) Methodology (build and operate)

Every runtime or service should follow the same lifecycle:

1. **Declare** capability in `services/MANIFEST.yaml` (id, API base URL, token file, jobs, status).
2. **Constrain** execution via typed jobs and allowlists (no generic arbitrary command endpoint).
3. **Expose** the same capability over MCP for MCP-capable agents.
4. **Enforce** host policy (auth, TTL, quotas, concurrency, network boundaries, auditability).
5. **Observe** with health checks and structured job status transitions.

This keeps all runtimes consistent while still allowing OS-specific internals.

### 3) Architecture contract between parent and services

`parallel-OS` is responsible for:

- service discovery and capability indexing
- manifest parsing and typed accessors
- local secret/token file resolution
- agent entrypoint documentation and stable service IDs

Each concrete service (for example `kali-factory` or external `gpu-factory`) is responsible for:

- validating job schemas
- executing jobs safely in its own domain
- enforcing image/tool allowlists
- returning structured outputs and failures

This separation is intentional: the parent package is the orchestration contract, services are the execution engines.

### 4) GPU/CUDA service fit (why `gpu-factory` aligns)

`gpu-factory` follows the same abstraction:

- typed jobs (`gpu_probe`, `run_container`, `python_probe`)
- API token auth
- Docker-first execution with optional GPU
- local MCP server adapter for tool parity

That makes it a first-class `parallel-OS` service even when hosted externally, and keeps DGX Spark integration consistent with other runtimes.

### 5) Design rules for new runtimes

Any new runtime should satisfy all of the following before being listed as "running":

- **Deterministic contract**: jobs are explicit and versioned
- **Safety-first execution**: allowlist + typed args + bounded runtime
- **Agent portability**: callable via API and MCP
- **Manifest compatibility**: zero hardcoded URLs in agent logic
- **Host viability**: verified on target host class (for example DGX Spark, EC2, bare metal)

## Status

Early design phase. v0.0.1 was the architecture skeleton. v0.0.2 wires Kali Factory in as the first concrete service via submodule + manifest. v0.1 will be the first runtime end-to-end with the SDK fully functional.

## Roadmap

| Milestone | Status |
|---|---|
| Repo skeleton, architecture doc | ⏳ in progress |
| `Runtime.spawn()` working with one runtime (Ubuntu) | planned |
| Kali runtime with allowlisted toolset | planned |
| Multi-runtime concurrent spawn from one agent | planned |
| Resource scheduler (cgroups, mem limits, ttl) | planned |
| Per-tool MCP wrappers (vs raw shell) | planned |
| Audit log + policy enforcement | planned |
| GPU-passthrough runtimes (CUDA/ROCm) | future |
| Non-Linux runtimes (Windows, macOS-via-Lima) | future |

## License

Apache 2.0 (see `LICENSE`).
