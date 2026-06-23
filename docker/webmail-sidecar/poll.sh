#!/usr/bin/env bash
# webmail-watch 사이드카 호스트 래퍼 — systemd ExecStart 진입점.
#
# 역할:
#  1) openclaw.json 에서 Telegram 봇토큰을 읽어 컨테이너에 **env 로만** 주입(파일 미마운트, 최소권한 유지).
#     → run.py 의 notify_telegram() 이 반송 감지 시 Dr. Ben 텔레그램으로 직접 알림.
#  2) run.py 가 반송(failure notice)을 감지하면 `BOUNCE_HALT` 를 출력 → 이 래퍼가 사이드카 타이머를
#     자동 disable(= 작동 멈춤). Dr. Ben 이 수동 처리(받은편지함 failure notice 확인 + ‘Gmail’ 보관함
#     미배달 원본 처리 + failure notice 삭제) 후 `/cron on` 또는 타이머 재가동으로 재개.
#
# 근거: 552(Gmail 콘텐츠 보안 거부)는 SMTP 수신단 필터라 전달방식으론 우회 불가 → 반송분만 사람이 처리.
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
OPENCLAW_JSON="${HOME}/.openclaw/openclaw.json"
TIMER="openclaw-webmail-sidecar.timer"
export TELEGRAM_CHAT_ID="${WEBMAIL_TELEGRAM_CHAT_ID:-8669227844}"   # Dr. Ben Telegram chat

# 봇토큰 (cmdline 미노출 — env 로만)
export TELEGRAM_BOT_TOKEN=""
if [ -r "$OPENCLAW_JSON" ]; then
  TELEGRAM_BOT_TOKEN="$(python3 -c "import json; print(json.load(open('${OPENCLAW_JSON}')).get('channels',{}).get('telegram',{}).get('botToken','') or '')" 2>/dev/null || true)"
  export TELEGRAM_BOT_TOKEN
fi

# 일회성 폴 (compose 기본 CMD = python run.py kirams). -e VAR(값 생략) = 현재 셸 env 에서 전달 → cmdline 노출 X.
OUT="$(cd "$DIR" && docker compose -f compose.yml run --rm \
        -e TELEGRAM_BOT_TOKEN -e TELEGRAM_CHAT_ID \
        webmail-sidecar 2>&1)"
RC=$?
printf '%s\n' "$OUT"

# 반송 감지 → 작동 멈춤 (타이머 정지). 알림은 run.py 가 이미 텔레그램으로 보냄.
if printf '%s' "$OUT" | grep -q "BOUNCE_HALT"; then
  echo "[poll.sh] BOUNCE_HALT 감지 → ${TIMER} 정지(작동 멈춤). Dr. Ben 수동 처리 후 재개."
  systemctl --user disable --now "$TIMER" 2>&1 || true
fi
exit "$RC"
