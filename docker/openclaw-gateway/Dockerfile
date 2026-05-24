# OpenClaw gateway — thin derivation of the OFFICIAL image.
#
# WHY official-base (2026-05-17 realignment): our prior self-built image
# (`npm install -g openclaw`) diverged structurally from OpenClaw's official
# Docker method — npm-global layout, no /app bundled extensions+skills, no
# OPENCLAW_PLUGIN_STAGE_DIR wiring. That divergence was the likely root cause
# of the cron skill-injection blocker (`/gws-assistant` not expanded →
# claude-cli "Unknown command" → orphaned runs). Aligning to the official
# image replaces that guesswork with the supported, source-built layout
# (/app/dist, /app/extensions, /app/skills, official docker-entrypoint.sh).
#
# We only ADD what the official image cannot carry for this deployment:
#   - claude CLI : OpenClaw's claude-cli/* legacy refs spawn `claude` as a
#                  subprocess (Pro/Max OAuth path). Pinned via CLAUDE_CODE_VERSION.
#   - uv + Chromium : the webmail-watch skill is a uv-run Playwright script.
# gog is NOT baked (RO bind-mounted, Option B — see compose.openclaw.yml).
#
# Pin 2026.4.21: 2026.4.24+ rewrites claude-cli/* → bills as third-party app
# (see docs/openclaw-setup.md). The ghcr <version> tag matches that pin.
ARG OPENCLAW_VERSION
FROM ghcr.io/openclaw/openclaw:${OPENCLAW_VERSION}

ARG CLAUDE_CODE_VERSION

# --- root layer: system deps + Chromium + uv ---------------------------------
USER root

# python3-venv/pip for the throwaway venv that drives `playwright install`;
# Chromium + its OS deps baked to a shared world-readable path so the
# uv-resolved Playwright (webmail-watch pins playwright>=1.45) finds them.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-venv python3-pip ripgrep less \
    && rm -rf /var/lib/apt/lists/*

ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
RUN python3 -m venv /opt/pw \
    && /opt/pw/bin/pip install --no-cache-dir "playwright>=1.45" \
    && /opt/pw/bin/playwright install --with-deps chromium \
    && chmod -R a+rX /opt/ms-playwright

# uv (single static binary) for `uv run` of the Python skills.
RUN curl -fsSL https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh \
    && uv --version

# --- node layer: claude CLI (installs into /home/node/.local) -----------------
# /home/node/.local is NOT bind-mounted at runtime, so this stays baked while
# ~/.claude (OAuth creds, bind-mounted) is provided by the host.
USER node
RUN curl -fsSL https://claude.ai/install.sh | bash -s ${CLAUDE_CODE_VERSION}
ENV PATH="/home/node/.local/bin:${PATH}"
# claude self-update off — version is the pinned rebuild only.
ENV DISABLE_AUTOUPDATER=1

# ENTRYPOINT (docker-entrypoint.sh) and CMD
# (node openclaw.mjs gateway --allow-unconfigured) are INHERITED from the
# official image on purpose — that is the alignment. Do not override.
