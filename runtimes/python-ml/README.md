# runtimes/python-ml

Python data-science + ML runtime image. Sandboxed Python 3.12 with the standard scientific/ML stack — agents call into it for embeddings, model training, dataframe work, and other ML workloads.

## What's inside

| Category | Libraries |
|---|---|
| Numerics | numpy, scipy, sympy |
| Dataframes | pandas, polars, pyarrow, duckdb |
| Classical ML | scikit-learn, xgboost, lightgbm, statsmodels |
| Deep learning (CPU) | torch, torchvision |
| NLP & embeddings | transformers, sentence-transformers, tokenizers, safetensors, datasets |
| Vector stores | faiss-cpu, chromadb-client |
| Viz | matplotlib, seaborn, plotly |
| Graph | networkx |
| I/O & HTTP | requests, httpx, pydantic, tqdm |
| Interactive | jupyterlab, ipykernel, ipython |

See [`tools.json`](./tools.json) for the canonical list.

## Build

```bash
docker build -t python-ml/data:latest .
```

This is a fat image (~5 GB). Most of the weight is torch + transformers + the wheel build cache. ARM64 builds typically need a few extra minutes for native-extension wheels.

## Smoke test

```bash
docker run --rm python-ml/data:latest
```

Prints a JSON blob with the resolved versions of numpy/pandas/scipy/sklearn/torch/transformers/polars/duckdb. Use this as a healthcheck after rebuilds.

## Hardening (applied by the orchestrator at run time, not in the image)

- `--user 65534:nogroup` (non-root)
- `--cap-drop ALL`
- `--read-only` rootfs
- `--tmpfs /tmp:rw,size=2g --tmpfs /work:rw,size=4g`
- `--memory 8g --cpus 4` (defaults; per-job override allowed)
- Egress allowed (model/data downloads); no inbound port publish
- No host volume mounts by default

## Variants

- **`python-ml/data:latest`** *(this image)* — CPU-only torch. Runs anywhere Docker runs.
- **`python-ml/torch-cuda`** *(planned)* — CUDA torch for GPU workloads on the DGX Spark. Will require NVIDIA Container Toolkit + `--gpus all`.

## Differences from kali-factory

| | kali-factory | python-ml |
|---|---|---|
| Unit of work | shell binary invocation | Python code |
| Allowlist enforcement | shell allowlist + Pydantic schemas + nuclei template restriction | container boundary only |
| Network | optional egress, default off | egress on (datasets/models need it) |
| Image size | ~3 GB | ~5 GB |
| Re-validation in worker | yes (allowlist + image prefix) | image prefix only |

The `python_run` style of job is fundamentally arbitrary code execution. We don't try to enforce a Python-import allowlist — too brittle, easy to bypass with `__import__`. Instead, we trust the container as the boundary and document what's available.
