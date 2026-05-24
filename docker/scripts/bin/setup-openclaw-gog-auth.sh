#!/usr/bin/env bash
# setup-openclaw-gog-auth.sh — Phase 2 Step C bootstrap for the OpenClaw
# container's privilege-separated gog identity (Option B).
#
# Creates the `openclaw-container` OAuth client registration + a refresh
# token, in an ISOLATED config dir (~/.config/gogcli-openclaw-container/),
# encrypted with a dedicated keyring passphrase. Distinct from the host gog
# (~/.config/gogcli) AND from sb-claude's old gogcli-container. The OpenClaw
# container RO-mounts this dir; container compromise != host Google-API
# compromise.
#
# INTERACTIVE: `gog auth add` opens a browser OAuth consent. Run it yourself
# from the session prompt:   ! bash ~/projects/2nd-brain-docker/scripts/bin/setup-openclaw-gog-auth.sh
#
# Verified against gog v0.13.0 (the syntax in docs/gogcli-container-setup.md
# is stale: it is `auth credentials set <path> --client`, not `add
# --client-secret`).
set -euo pipefail

ACCOUNT="${1:-kimbi.kirams@gmail.com}"   # gog account — NOT benkorea.ai
CLIENT="openclaw-container"
GOGCLI_DIR="$HOME/.config/gogcli-openclaw-container"
ENV_FILE="$HOME/projects/2nd-brain-docker/.env"

echo "==> account : $ACCOUNT"
echo "==> client  : $CLIENT"
echo "==> config  : $GOGCLI_DIR"
echo

[ -f "$GOGCLI_DIR/client_secret.json" ] || { echo "ERROR: $GOGCLI_DIR/client_secret.json missing (Step B not done)"; exit 1; }

PASS="$(grep '^GOG_OPENCLAW_KEYRING_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)"
[ -n "$PASS" ] || { echo "ERROR: GOG_OPENCLAW_KEYRING_PASSWORD empty in $ENV_FILE"; exit 1; }

# gog reads $HOME/.config/gogcli/. Point a throwaway HOME at the isolated dir
# so this auth never touches the host's default gog config.
HOME_FAKE="$(mktemp -d)"
trap 'rm -rf "$HOME_FAKE"' EXIT
mkdir -p "$HOME_FAKE/.config"
ln -s "$GOGCLI_DIR" "$HOME_FAKE/.config/gogcli"

run() { HOME="$HOME_FAKE" GOG_KEYRING_PASSWORD="$PASS" gog "$@"; }

echo "==> [1/3] register client credentials"
run auth credentials set "$GOGCLI_DIR/client_secret.json" --client "$CLIENT"

echo "==> [2/3] OAuth — a browser will open. Sign in as: $ACCOUNT"
echo "          (consent to the requested scopes, then return here)"
run auth add "$ACCOUNT" --client "$CLIENT"

echo "==> [3/3] verify"
run auth list
echo
echo "keyring files:"; ls -la "$GOGCLI_DIR/keyring" 2>/dev/null || echo "(none — auth may have failed)"
echo
echo "DONE. Tell Claude to continue Phase 2 verification + Phase 3 cutover."
