# Python-ML runtime image for parallel-OS.
#
# Scope: data science + classical ML + CPU deep learning. Gives an AI agent
# a sandboxed Python interpreter with the standard data/ML stack.
#
# Security model differs from kali-factory: the unit of work here is Python
# code, not shell binaries, so an allowlist of binaries is informational —
# the *container* is the security boundary. Hardening:
#   - non-root (UID 65534), drop ALL caps, read-only rootfs (set at run time)
#   - tmpfs /work and tmpfs /tmp
#   - memory + CPU limits applied by the orchestrator at run time
#   - egress allowed (model/data downloads); no inbound ports
#   - no host volume mounts by default

FROM python:3.12-slim

LABEL parallel-os.runtime="python-ml"
LABEL parallel-os.image-version="python-ml-2026-q2"
LABEL parallel-os.scope="data-science-and-ml"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System libs that the scientific stack links against. build-essential lets
# wheels build for less-common architectures (ARM64) when needed; we strip
# it in the same layer to keep the image lean.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential gfortran \
        libopenblas-dev liblapack-dev \
        libomp-dev \
        git curl ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ─── Core scientific + ML stack ────────────────────────────────────────────
# Numerics, dataframes, classical ML, gradient boosting, stats, viz.
RUN pip install --upgrade pip wheel setuptools && \
    pip install \
        numpy \
        pandas polars pyarrow duckdb \
        scipy \
        scikit-learn \
        xgboost lightgbm \
        statsmodels \
        matplotlib seaborn plotly \
        sympy networkx \
        tqdm pydantic httpx requests \
        jupyterlab ipykernel ipython

# ─── Deep learning + embeddings ────────────────────────────────────────────
# Torch (CPU build) + the HuggingFace stack. A CUDA variant can ship as a
# sibling image (python-ml/torch-cuda) once GPU passthrough wiring lands.
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
        torch torchvision && \
    pip install \
        sentence-transformers \
        transformers \
        datasets \
        safetensors \
        tokenizers

# ─── Vector store clients (optional but high-value) ────────────────────────
RUN pip install \
        faiss-cpu \
        chromadb-client

# Tools manifest baked in
COPY tools.json /etc/parallel-os/tools.json

# Drop privileges
RUN useradd -r -u 65534 -g nogroup -s /usr/sbin/nologin -d /work agent || true
RUN mkdir -p /work && chown 65534:nogroup /work

USER 65534:nogroup
WORKDIR /work

# HF / Torch caches into /tmp (tmpfs) by default. Mount a host volume at
# /tmp/cache and re-export these to make caches persistent across runs.
ENV HOME=/tmp \
    HF_HOME=/tmp/huggingface_cache \
    TORCH_HOME=/tmp/torch_cache \
    XDG_CACHE_HOME=/tmp/cache

# Default: print a versions manifest so `docker run python-ml/data` doubles
# as a healthcheck. Real jobs override the cmd.
CMD ["python3", "-c", "import json, numpy, pandas, scipy, sklearn, torch, transformers, polars, duckdb; print(json.dumps({'python':'3.12', 'numpy':numpy.__version__, 'pandas':pandas.__version__, 'scipy':scipy.__version__, 'sklearn':sklearn.__version__, 'torch':torch.__version__, 'transformers':transformers.__version__, 'polars':polars.__version__, 'duckdb':duckdb.__version__}, indent=2))"]
