#!/bin/bash
# sync-claude-version.sh
#
# 호스트(WSL2 native)의 Claude Code 버전을 openclaw 이미지의 번들 claude
# 바이너리 핀(.env CLAUDE_CODE_VERSION)에 맞춰 재빌드한다. openclaw 의
# claude-cli/* legacy ref 경로가 컨테이너 안 `claude` 서브프로세스를 호출하므로
# 호스트 native claude 와 버전을 맞춘다. 호스트 = "버전 진실의 원천".
# (sb-claude 컨테이너는 폐기됨 — claude 는 호스트 native + openclaw 이미지 번들.)
#
# 사용:
#   make sync                       # 호스트 버전 → .env 갱신 + openclaw 이미지 재빌드
#   make sync && make restart-openclaw  # 재빌드 후 컨테이너 교체
#
# 동작:
#   1) `claude --version` 으로 호스트 버전 추출
#   2) .env 의 CLAUDE_CODE_VERSION 과 비교
#   3) 다르면 .env 갱신 + openclaw 이미지 재빌드
#   4) 같으면 no-op

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

if ! command -v claude >/dev/null 2>&1; then
    echo "ERROR: 'claude' not found in PATH on host." >&2
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: ${ENV_FILE} not found. Copy .env.example first." >&2
    exit 1
fi

HOST_VER=$(claude --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ -z "${HOST_VER:-}" ]; then
    echo "ERROR: failed to parse host claude version." >&2
    exit 1
fi

CURRENT=$(grep '^CLAUDE_CODE_VERSION=' "$ENV_FILE" | cut -d= -f2 || true)

echo "Host Claude Code: ${HOST_VER}"
echo "Container pin:    ${CURRENT:-(unset)}"

if [ "$HOST_VER" = "$CURRENT" ]; then
    echo "Already in sync. No rebuild needed."
    exit 0
fi

echo
echo "Updating ${ENV_FILE}: ${CURRENT:-(unset)} -> ${HOST_VER}"
sed -i "s/^CLAUDE_CODE_VERSION=.*/CLAUDE_CODE_VERSION=${HOST_VER}/" "$ENV_FILE"

echo
echo "Rebuilding openclaw image..."
cd "$REPO_ROOT"
GOG_OPENCLAW_KEYRING_PASSWORD="${GOG_OPENCLAW_KEYRING_PASSWORD:-_unused_at_build_}" \
    docker compose -f compose.openclaw.yml build

echo
echo "Done. Run 'make restart-openclaw' to swap the running container to the new image."
