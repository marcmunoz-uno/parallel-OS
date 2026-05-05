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

## Status

Early design phase. Read the README, file an issue with feedback, watch the repo. v0.0.x will be working concept code. v0.1 will be the first runtime (Kali) end-to-end.

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
