#!/bin/bash
# detect-compose.sh — Output the docker-compose -f chain appropriate for this machine.
#
# Auto-detects NVIDIA stack:
#   - nvidia-smi available + GPU visible + docker nvidia runtime registered
#       → includes 2nd-brain-parser/compose.2nd-brain-parser.gpu.yml (GPU passthrough)
#   - anything else
#       → base only (CPU inference; cu126 PyTorch wheel still imports cleanly,
#         torch.cuda.is_available() returns False, libraries fall back to CPU)
#
# Override via environment:
#   PARSER_FORCE_VARIANT=gpu   force GPU overlay (debug / detection misfire)
#   PARSER_FORCE_VARIANT=cpu   skip GPU overlay even if NVIDIA present
#   PARSER_FORCE_VARIANT=auto  default — run detection (same as unset)
#
# Output is one line, space-separated `-f` chain. Use via:
#   docker compose $(./scripts/detect-compose.sh) <subcmd>

set -e

# 2nd-brain-parser is standalone: compose.2nd-brain-parser.yml is self-contained
# (defines its own service + volume). Images are ghcr-pulled (no build).
FILES="-f 2nd-brain-parser/compose.2nd-brain-parser.yml"

case "${PARSER_FORCE_VARIANT:-auto}" in
    gpu)
        FILES="$FILES -f 2nd-brain-parser/compose.2nd-brain-parser.gpu.yml"
        ;;
    cpu)
        : # base only
        ;;
    auto|"")
        if command -v nvidia-smi >/dev/null 2>&1 \
           && nvidia-smi -L >/dev/null 2>&1 \
           && docker info 2>/dev/null | grep -q -i 'nvidia'; then
            FILES="$FILES -f 2nd-brain-parser/compose.2nd-brain-parser.gpu.yml"
        fi
        ;;
    *)
        echo "detect-compose.sh: unknown PARSER_FORCE_VARIANT='${PARSER_FORCE_VARIANT}' (expected: gpu, cpu, auto)" >&2
        exit 2
        ;;
esac

echo "$FILES"
