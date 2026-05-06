# Start Here — Agent's Guide to parallel-OS

You are an AI agent running on (or talking to) a host that publishes parallel-OS. parallel-OS gives you typed access to multiple operating-system runtimes from one consolidated entry point. Each runtime is good at different things; you pick the one that fits the task.

This document is the **single place** to learn what's available. Read [`services/MANIFEST.yaml`](./services/MANIFEST.yaml) for the machine-readable index, then read each service's per-service guide for the contract.

## The contract (applies to every service)

1. **You don't get a host shell.** You submit typed jobs to a service's API or call its MCP tools.
2. **Every call is bounded.** Time limits, output size limits, image allowlist, tool allowlist — set per service.
3. **Bearer auth is per-service.** The token for each service lives in that service's `.secrets/api_token` (chmod 0600). The manifest tells you where.
4. **Forbidden tools stay forbidden.** Even if you craft a valid HTTP shape, the worker re-validates against its allowlist. Don't try to bypass it — it doesn't work, and it's logged.

## Discovery flow

```
                    ┌────────────────────────────┐
                    │  you (the agent)           │
                    └──────────────┬─────────────┘
                                   │
                  ┌────────────────▼─────────────────┐
                  │  read services/MANIFEST.yaml     │
                  │  → list of services + per-       │
                  │    service docs + endpoints      │
                  └────────────────┬─────────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
   ┌────▼────────┐            ┌────▼────────┐           ┌─────▼──────┐
   │ kali-factory│            │ gpu-factory │           │   future   │
   │ (OSINT)     │            │ (CUDA)      │           │  runtimes  │
   │ :8081       │            │ :8080       │           │            │
   └─────────────┘            └─────────────┘           └────────────┘
```

## Available services (see manifest for current truth)

| Service | What it does | Best for |
|---|---|---|
| [`kali-factory`](./services/kali-factory) | Allowlisted Kali OSINT/recon (~80 tools: ProjectDiscovery suite, OSINT frameworks, trufflehog/gitleaks, nuclei-exposures) | passive recon, attack surface mapping, leaked-credential hunting against repos you own |
| `gpu-factory` *(external)* | Allowlisted CUDA / GPU inference jobs | embeddings, batched LLM inference, vector workloads |
| [`python-ml`](./runtimes/python-ml) *(image-only, no service yet)* | Python 3.12 + numpy / pandas / scipy / scikit-learn / torch (CPU) / transformers / sentence-transformers / polars / duckdb / xgboost / lightgbm / faiss-cpu | dataframe work, embeddings, classical ML training, gradient boosting, NLP pipelines |

For each service, read its **per-service agent guide** before sending traffic:

- `services/kali-factory/START_HERE_FOR_AGENTS.md` — Kali Factory contract, job types, examples
- *(GPU Factory: see its own repo)*

## What is NEVER allowed (cross-service)

These are forbidden across the entire parallel-OS surface, regardless of which service you call:

- Arbitrary shell on the host. There is no "run anything" endpoint.
- Bypassing a service's allowlist by guessing image names, tool names, or template paths.
- Submitting recon work against targets you don't own or have written authorization for.
- Storing bearer tokens in plaintext anywhere checked into git.
- Stacking jobs past a service's per-agent concurrency limit.

## Workflow

1. **Discover.** Read `services/MANIFEST.yaml`. Identify the service whose `role` matches your task.
2. **Read the contract.** Open the service's `agent_doc` (also listed in the manifest entry). Each service ships its own.
3. **Authenticate.** Read the bearer token from the service's `token_file` path.
4. **Submit + poll.** Submit a typed job, get a `job_id`, poll until status is terminal.
5. **Read the result.** Each service returns a structured `output_summary`.

## Multi-runtime composition

A common pattern: use one runtime to gather, another to analyze.

```
   kali-factory/subdomain_enum  ───▶  results.json
                                          │
                                          ▼
   gpu-factory/embed                 vector store
                                          │
                                          ▼
              your reasoning loop
```

Each call goes to the right service through the same MCP-or-HTTP discovery flow. Cross-service plumbing is your job — parallel-OS doesn't pipe between them automatically.

## When something fails

Per-service status codes are documented in the per-service guides, but the cross-cutting ones:

- `rejected` → your payload violated an allowlist (image, tool, template). The error message names the constraint.
- `failed` → the tool ran but exited non-zero. Read the error for stderr.
- `timed_out` → exceeded `max_runtime_sec`. Increase it or narrow the scope.
- `unauthorized` → token wrong, missing, or expired. Re-read the token file.

## If you're MCP-native

Each service that supports MCP exposes a stdio entry point listed in the manifest under `mcp.command`. Run that command and the service's job types appear as MCP tools. Polling is handled for you.

## Don't do this

- Don't hardcode service URLs. Read the manifest. Ports and auth paths can move.
- Don't bypass the per-service allowlist. The worker re-validates and the bypass is logged.
- Don't run recon against targets without explicit authorization.
- Don't store bearer tokens in plaintext anywhere checked into git.
- Don't pile up jobs. Respect each service's concurrency limits.
