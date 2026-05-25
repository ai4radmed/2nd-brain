#!/usr/bin/env bash
# headed-browser 사이드카 entrypoint — 가상 디스플레이(Xvfb) 위에서 headed 브라우저 스킬 구동.
# MailPlug 같은 anti-headless SPA 는 headless 면 백지 → headed(실제/가상 디스플레이)로만 렌더됨.
# xvfb-run 래퍼는 정리 단계에서 행(hang)하므로 Xvfb 를 직접 기동·종료한다(실측 2026-05-25).
set -euo pipefail

XVFB_DISPLAY="${DISPLAY:-:99}"
Xvfb "${XVFB_DISPLAY}" -screen 0 1280x1024x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!
trap 'kill "${XVFB_PID}" 2>/dev/null || true' EXIT

# Xvfb 소켓이 뜰 때까지 대기 (최대 ~6s)
for _ in $(seq 1 20); do
  [ -e "/tmp/.X11-unix/X${XVFB_DISPLAY#:}" ] && break
  sleep 0.3
done

exec "$@"
