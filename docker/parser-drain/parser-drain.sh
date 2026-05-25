#!/usr/bin/env bash
# parser-drain — host-측 결정형 파싱 드레인 (watchdog 밖, concurrency=1, 멱등).
# sources/00_inbox 의 미파싱 바이너리(PDF·HWP·docx·xlsx)를 2nd-brain-parser
# 컨테이너로 순차 파싱해 <원본>_parse/docling.json 생성. 검증·노트화는 brainify(별도).
#
# 트리거: parser-drain.timer (host systemd-user). 게이트웨이는 파일만 드롭.
# 안정: systemd 단일인스턴스 + flock + 순차루프 = concurrency=1 (RAM 보호).
set -euo pipefail

export SB_DATA="${SB_DATA:-$HOME/projects/2nd-brain-vault}"   # compose 가 마운트에 사용
REPO="${SECOND_BRAIN_REPO:-$HOME/projects/2nd-brain}"
INBOX="$SB_DATA/sources/00_inbox"
CMNT="/home/user/projects/2nd-brain-vault"                    # 컨테이너 내부 마운트 경로
LOG="${PARSER_DRAIN_LOG:-$HOME/.local/state/parser-drain.log}"
mkdir -p "$(dirname "$LOG")"
log(){ echo "$(date -Is) $*" >>"$LOG"; }

# ── concurrency=1: 이미 실행 중이면 조용히 종료 ──
exec 9>"/run/user/$(id -u)/parser-drain.lock"
flock -n 9 || { log "already running, skip"; exit 0; }

[ -d "$INBOX" ] || { log "no inbox: $INBOX"; exit 0; }

# ── warm 데몬 1회 기동 (모델 init amortize), 종료 시 teardown ──
cd "$REPO/docker"
mapfile -t CF < <(./scripts/detect-compose.sh)            # "-f .../compose..yml" 토큰
COMPOSE=(docker compose ${CF[*]})
"${COMPOSE[@]}" up -d 2nd-brain-parser >>"$LOG" 2>&1
trap '"${COMPOSE[@]}" down >>"$LOG" 2>&1 || true' EXIT

shopt -s nullglob globstar
n=0
for f in "$INBOX"/**/*.pdf "$INBOX"/**/*.hwp "$INBOX"/**/*.hwpx "$INBOX"/**/*.docx "$INBOX"/**/*.xlsx; do
  out="${f}_parse"
  [ -s "$out/docling.json" ] && continue                  # 멱등: 완료분(비어있지 않음)만 skip
  mkdir -p "$out"
  cpath="${f/#$SB_DATA/$CMNT}"                             # host→컨테이너 경로 변환
  tmp="$out/.docling.json.tmp"
  log "parse: $f"
  if docker exec 2nd-brain-parser 2nd-brain-parser parse-docling "$cpath" \
        >"$tmp" 2>>"$LOG" && [ -s "$tmp" ]; then
    mv -f "$tmp" "$out/docling.json"; n=$((n+1)); log "ok: $f"   # atomic: 성공 시에만 확정
  else
    rm -f "$tmp"; : >"$out/.parse-error"; log "FAIL: $f"         # 중단 시 final 없음 → 재실행이 재파싱
  fi
done
log "drain done ($n parsed)"
