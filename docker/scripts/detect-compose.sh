#!/bin/bash
# detect-compose.sh — Output the docker-compose -f chain appropriate for this machine.
#
# Auto-detects NVIDIA stack:
#   - nvidia-smi available + GPU visible + docker nvidia runtime registered
#       → includes compose.brain-pdf.gpu.yml (GPU passthrough via --gpus all)
#   - anything else
#       → base only (CPU inference; cu126 PyTorch wheel still imports cleanly,
#         torch.cuda.is_available() returns False, libraries fall back to CPU)
#
# Override via environment:
#   BRAIN_PDF_FORCE_VARIANT=gpu   force GPU overlay (debug / detection misfire)
#   BRAIN_PDF_FORCE_VARIANT=cpu   skip GPU overlay even if NVIDIA present
#   BRAIN_PDF_FORCE_VARIANT=auto  default — run detection (same as unset)
#
# Output is one line, space-separated `-f` chain. Use via:
#   docker compose $(./scripts/detect-compose.sh) <subcmd>
#
# Or in Makefile:
#   COMPOSE := $(shell ./scripts/detect-compose.sh)

set -e

# brain-pdf is standalone: compose.brain-pdf.yml is self-contained (defines
# its own service + volume, no dependency on a base compose.yml). The old
# sb-claude base compose.yml was removed when the Claude Code container was
# decommissioned (Claude Code is host-native; OpenClaw is its own standalone
# compose.openclaw.yml).
FILES="-f compose.brain-pdf.yml"

case "${BRAIN_PDF_FORCE_VARIANT:-auto}" in
    gpu)
        FILES="$FILES -f compose.brain-pdf.gpu.yml"
        ;;
    cpu)
        : # base only
        ;;
    auto|"")
        if command -v nvidia-smi >/dev/null 2>&1 \
           && nvidia-smi -L >/dev/null 2>&1 \
           && docker info 2>/dev/null | grep -q -i 'nvidia'; then
            FILES="$FILES -f compose.brain-pdf.gpu.yml"
        fi
        ;;
    *)
        echo "detect-compose.sh: unknown BRAIN_PDF_FORCE_VARIANT='${BRAIN_PDF_FORCE_VARIANT}' (expected: gpu, cpu, auto)" >&2
        exit 2
        ;;
esac

echo "$FILES"
