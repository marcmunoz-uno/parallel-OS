# Architecture

## Goals

1. **Agent picks the OS, not the deployer.** An agent at runtime decides which OS surface it needs — the host doesn't have to know in advance.
2. **MCP is the only protocol.** Agents don't learn a new RPC system; tools surface as MCP tools the same way Claude/Cursor agents already use them.
3. **Spawn-on-demand.** Containers come up in seconds, not minutes. Idle resources are reclaimed.
4. **Allowlist-first.** Each runtime has an explicit tool allowlist. No tool is callable unless it's declared.
5. **Pluggable backend.** Docker first; podman, Firecracker microVMs, gVisor, or remote SSH targets later.

## Explicit system abstraction

`parallel-OS` defines a strict two-layer model:

1. **Parent orchestration layer (`parallel-OS`)**
   - Owns service discovery, manifest parsing, policy wiring, and agent-facing contracts.
   - Does not directly implement domain-specific execution logic (OSINT, CUDA orchestration, etc.).
2. **Runtime service layer (kali-factory, gpu-factory, future runtimes)**
   - Owns actual job execution, safety gates, and domain-specific controls.
   - Must expose typed jobs and structured responses.

This boundary is non-negotiable and is what allows one agent workflow to compose multiple runtimes without runtime-specific hardcoding.

## Methodology: contract-first runtime integration

When introducing or updating a runtime service, the workflow is:

1. **Define contract**
   - Enumerate typed jobs (name, input schema, output schema, limits).
   - Define auth mechanism and token-file behavior.
   - Define MCP exposure strategy (tool names and mappings).
2. **Implement safe executor**
   - Build allowlisted execution paths only.
   - Reject unknown job types and malformed arguments.
   - Enforce timeouts/concurrency/resource bounds.
3. **Register in manifest**
   - Add canonical service ID and endpoint.
   - Declare supported jobs and capability metadata.
   - Add status and operational notes.
4. **Validate on target host class**
   - Run health checks and smoke jobs.
   - Verify architecture compatibility (for example ARM64 on DGX Spark).
   - Verify policy behavior under failure and load.
5. **Document agent usage**
   - Update `START_HERE_FOR_AGENTS.md` with invocation patterns.
   - Ensure agents can discover and use the runtime only from manifest data.

This methodology keeps service additions repeatable and auditable.

## Canonical control flow

The expected request lifecycle is:

1. Agent loads manifest via `parallel_os.load()`.
2. Agent resolves service by ID (`m.get("kali-factory")`, `m.get("gpu-factory")`).
3. Agent reads auth token from declared token file.
4. Agent submits typed job through service API or MCP adapter.
5. Service validates input and policy, then executes allowlisted action.
6. Service returns structured result, and logs execution metadata.

If any step is not deterministic or typed, the integration is considered incomplete.

## Components

### 1. Host orchestrator
Runs as a long-lived service on the host. Responsibilities:
- Pull / build runtime images
- Spawn containers with correct mounts, network, resource limits
- Track active runtimes, route agent connections to them
- Garbage-collect idle containers (TTL-based)
- Emit audit logs

```python
# src/parallel_os/orchestrator/runtime.py
class Runtime:
    name: str           # "kali", "ubuntu", ...
    image: str          # docker image ref
    mcp_port: int       # internal MCP server port
    container_id: str   # docker container id
    expires_at: float   # epoch seconds for GC
```

### 2. Per-runtime MCP server
Inside each container, a small Python/Go process speaks MCP over stdio (or TCP/JSON-RPC for remote orchestration). It exposes:

- **`shell.run(cmd, args, stdin?, timeout?)`** — generic shell exec, gated by allowlist
- **`fs.read(path)`** / **`fs.write(path, content)`** / **`fs.list(path)`** — filesystem ops
- **`pkg.install(name)`** — package manager wrapper (apt/apk/pacman/nix)
- **`tool.<name>.<verb>(args)`** — first-class wrappers for declared tools

The MCP server reads `/etc/parallel-os/tools.json` at boot to know what's allowed.

### 3. Tool registry (per runtime)
A declarative manifest in each runtime image describing the available tools, their allowed argument shapes, and runtime limits.

```json
// runtimes/kali/tools.json
{
  "runtime": "kali",
  "image_version": "kali-rolling-2026-q2",
  "shell_allowlist": [
    "amass", "whatweb", "gobuster", "wfuzz",
    "linkfinder", "trufflehog", "spiderfoot",
    "mitmproxy", "mitmdump", "burpsuite-cli"
  ],
  "shell_blocklist": [
    "msfconsole", "sqlmap", "hashcat", "john",
    "aircrack-ng", "exploitdb"
  ],
  "tools": {
    "amass.enum": {
      "binary": "amass",
      "args_template": ["enum", "-d", "{domain}", "-o", "{output_path}"],
      "max_runtime_sec": 600,
      "max_concurrent": 3
    },
    "nuclei.expose_only": {
      "binary": "nuclei",
      "args_template": ["-u", "{url}", "-t", "exposures/", "-json"],
      "blocked_template_dirs": ["cves/", "vulnerabilities/", "default-logins/"],
      "max_runtime_sec": 300
    }
  }
}
```

### 4. Agent SDK
The agent's perspective. A small client library that talks to the host orchestrator over Unix socket or TCP, gets a connection to a freshly-spawned runtime, and exposes its tools as MCP calls.

```python
# pseudo-code; real impl in src/parallel_os/sdk/
from parallel_os import Runtime

# Spawn a Kali runtime, use it, tear down
async with Runtime.spawn("kali", ttl_sec=600) as kali:
    result = await kali.tool.amass.enum(domain="example.com")
    subdomains = result.subdomains

# Multi-runtime in parallel
async with Runtime.swarm(["kali", "ubuntu", "arch"]) as swarm:
    results = await asyncio.gather(
        swarm.kali.tool.whatweb.fingerprint(url="..."),
        swarm.ubuntu.shell.run("apt-cache search nginx"),
        swarm.arch.pkg.install("aur-helper"),
    )
```

### 5. Policy layer
The orchestrator enforces:
- **Runtime allowlist per agent** — not every agent can spawn every runtime
- **Tool allowlist within a runtime** — even if Kali ships nuclei, an OSINT-only agent can't run it with CVE templates
- **Resource quotas** — max RAM, max CPUs, max disk, max concurrent runtimes per agent
- **Network policy** — by default, runtimes have no public internet egress; opt-in per runtime/tool
- **Time-to-live** — runtimes auto-expire and get reaped

Policies are loaded from a YAML file at orchestrator startup.

```yaml
# config/policy.example.yaml
agents:
  recon-agent:
    runtimes: [kali, ubuntu]
    runtime_allowlists:
      kali: [amass, whatweb, gobuster, mitmproxy, linkfinder]
    network: egress-allowed
    max_concurrent_runtimes: 5
    runtime_ttl_sec: 1800

  build-agent:
    runtimes: [ubuntu, arch, alpine, nixos]
    runtime_allowlists:
      "*": "*"   # all tools in any allowed runtime
    network: localhost-only
    max_concurrent_runtimes: 10
    runtime_ttl_sec: 3600
```

## Data flow

```
agent ─── MCP call ──▶ host orchestrator ─── docker exec ──▶ runtime container
   │                          │                                    │
   │                          │                              MCP server
   │                          │                              inside container
   │                          │                                    │
   │                          │  ◀────── result via MCP ──────────  │
   │                          │
   │  ◀───── result ──────────│
```

The host orchestrator is the only thing the agent talks to directly. It multiplexes MCP requests to whichever runtime container is hosting the call.

## Security model

**Threat: agent escape from runtime container.** Mitigations:
- Rootless containers via `--user 65534:65534` and userns remap
- Strict seccomp profile (default Docker baseline + extra denies for `mount`, `ptrace`, `kexec`)
- No `--privileged`, ever
- Read-only root filesystem; tmpfs for `/tmp`
- Drop all caps; add only what the runtime needs

**Threat: tool misuse within runtime.** Mitigations:
- Allowlist enforced at MCP layer before shell exec
- Argument templates with strict typing — no string interpolation of user input into shell
- Per-tool runtime caps and concurrency limits
- Blocklisted binary list (e.g. `msfconsole` removed from PATH at image build)

**Threat: network abuse.** Mitigations:
- Default: runtime has no public internet (NetworkPolicy `none`)
- Opt-in egress per runtime, configured in policy YAML
- Per-runtime egress allowlist (only specific domains/IPs reachable)
- All egress logged

**Threat: data exfiltration via mounted volumes.** Mitigations:
- No host volume mounts by default
- Workdir is a per-runtime tmpfs that's destroyed on container exit
- Output retrieval is explicit: agent calls `fs.read(path)` to extract results, not `cp` from outside

**Threat: agent compromise leading to runtime abuse.** Mitigations:
- Per-agent policy file determines what runtimes/tools are reachable
- All MCP calls audit-logged with agent identity, runtime, tool, args, timestamp
- Optional: human-in-the-loop approval for high-risk runtime spawns

## Why Docker, not VMs

- **Spawn time**: Docker container in 1-3s, VM in 30-90s. For agent workflows that spin up runtimes on demand, this matters.
- **Resource overhead**: Containers share kernel, ~50 MB per idle. VMs need full kernel + drivers, hundreds of MB minimum.
- **Image management**: OCI registry is universal. Building/distributing runtime images is a solved problem.

The tradeoff is **shared kernel = weaker isolation**. We accept this for trusted-agent workloads. If your threat model assumes a hostile agent, swap the orchestrator backend for Firecracker microVMs or gVisor sandboxing — the agent SDK doesn't change.

## Why this isn't just SSH

Several reasons:
1. **Spawn-on-demand**: SSH expects a long-lived target. parallel-OS expects ephemeral runtimes.
2. **Tool composition**: SSH gives you a shell; you compose tools yourself. parallel-OS gives you typed MCP tools that can be chained by the agent's normal tool-call machinery.
3. **Policy enforcement at the protocol layer**: SSH lets you run anything you have permission for. parallel-OS lets you run only what's in the allowlist for your runtime.
4. **Multi-OS in one session**: SSH is per-target. parallel-OS lets a single agent hold concurrent connections to a Kali runtime, an Ubuntu runtime, and an Arch runtime, and orchestrate work across them.

## Open design questions

These need answers before v0.1:

1. **MCP transport for in-container servers**: stdio is simplest but requires `docker exec`. TCP/Unix-socket is more flexible but needs a side-channel for setup.
2. **State persistence between calls within one runtime session**: if `tool.A` writes a file, can `tool.B` read it? (Yes by default — same container session — but how is that surfaced in the SDK?)
3. **Cross-runtime data flow**: agent runs `whatweb` in Kali, wants to feed results to `nginx-conf-gen` in Ubuntu. How does data move between containers?
4. **GPU passthrough**: when a runtime needs CUDA (e.g., a vision model running inside the container), how does the orchestrator allocate the GPU?
5. **Image distribution**: build images locally vs. pull from a registry. Versioning. Security signing.
6. **Multi-host orchestration**: one host today, fleet later. K8s? Nomad? Custom?

## Non-goals (for now)

- Not building a multi-tenant SaaS — single-host, single-operator first
- Not implementing anti-fingerprinting / agent-stealth features — that's out of scope
- Not solving cluster federation — one DGX Spark is enough for the foreseeable future
- Not abstracting away OS differences — the value is *exposing* OS differences cleanly, not hiding them
