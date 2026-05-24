# brain-pdf — Docling + MinerU dual PDF parser service.
# CPU-only inference (kimbi WSL2 14GB constraint, no GPU passthrough).
# Invoked ephemeral (`docker compose run --rm`) by default, optional daemon mode.

FROM python:3.12-slim

ARG UID=1000
ARG GID=1000

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
# --index-url cu126: WSL2 NVIDIA driver 560.94 supports up to CUDA 12.6.
#   Separate torch-then-deps install caused CUDA version drift (deps pulled cu130
#   from PyPI, overwriting prior cu126 install — 2026.05.13 first build).
# --extra-index-url pypi: non-torch packages (docling, mineru, transitive deps)
#   fall through to PyPI.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cu126 \
        --extra-index-url https://pypi.org/simple \
        torch -r /tmp/requirements.txt

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
