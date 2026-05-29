# brain-pdf — Docling + MinerU dual PDF parser service.
# Runs CPU or GPU (the cu* torch build is CPU-capable; GPU used when the compose
# gpu overlay passes the device through). Invoked ephemeral (`docker compose
# run --rm`) by default, optional daemon mode.

FROM python:3.12-slim

ARG UID=1000
ARG GID=1000

# torch CUDA build — kept as build args (not hardcoded inline) so a GPU
# generation change is a one-line --build-arg, not an edit. cu128 ships Blackwell
# sm_120 kernels (RTX 50xx) AND stays backward-compatible to sm_80/sm_86/sm_89
# (Ampere/Ada) — single image covers both kimbi (5080) and the laptop GPU.
# TORCH_VERSION is PINNED with the +${TORCH_CUDA} local specifier on purpose:
# without it pip sees a HIGHER plain version on PyPI (e.g. 2.12.0+cu130) and
# silently picks that — cu130 needs a CUDA 13 driver and dies "driver too old"
# on our 12.9 host (drift hit twice: 2026.05.13 cu130, 2026.05.29 cu130 again).
# Bump only to a version that EXISTS on the cu128 index (pip index versions torch
# --index-url https://download.pytorch.org/whl/cu128).
ARG TORCH_CUDA=cu128
ARG TORCH_VERSION=2.11.0

# System deps:
#   libgomp1, libgl1, libglib2.0-0 — PyTorch / image libs runtime
#   poppler-utils                  — PDF utilities (pdftotext fallback)
#   ca-certificates, curl           — TLS + first-run model downloads
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 libgl1 libglib2.0-0 \
        poppler-utils \
        ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Match host UID/GID so vault files written by the container are owned correctly.
RUN groupadd -g "$GID" user \
    && useradd -u "$UID" -g "$GID" -m -s /bin/bash user

# PyTorch + parser libraries — single pip install for consistent resolution.
# --index-url ${TORCH_CUDA}: pin the torch CUDA build (see TORCH_CUDA arg above).
#   Host driver 576.88 / CUDA 12.9 fully supports cu128; the old cu126 build
#   lacked Blackwell sm_120 kernels and died with cudaErrorNoKernelImageForDevice
#   on the RTX 5080 (2026.05.29).
#   Separate torch-then-deps install caused CUDA version drift (deps pulled cu130
#   from PyPI, overwriting prior install — 2026.05.13 first build). Keep single.
# --extra-index-url pypi: non-torch packages (docling, mineru, transitive deps)
#   fall through to PyPI.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/${TORCH_CUDA} \
        --extra-index-url https://pypi.org/simple \
        "torch==${TORCH_VERSION}+${TORCH_CUDA}" -r /tmp/requirements.txt

# Pre-download RapidOCR models at build time (as root) so the image is offline-ready
# and avoids runtime PermissionError — RapidOCR insists on writing models into its
# own package directory (/usr/local/lib/.../rapidocr/models/) which is root-owned,
# and ephemeral `--rm` runs would re-download every invocation otherwise.
RUN python3 -c "from rapidocr import RapidOCR; RapidOCR()" 2>&1 | tail -5

# CLI entrypoint installed system-wide.
COPY entrypoint.py /usr/local/bin/brain-pdf
RUN chmod +x /usr/local/bin/brain-pdf

USER user
RUN mkdir -p /home/user/.cache/huggingface /home/user/work
WORKDIR /home/user/work

# Default command for daemon mode. Override with `docker compose run` for ephemeral.
CMD ["sleep", "infinity"]
