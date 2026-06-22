#!/usr/bin/env bash
# parser-drain — host-측 결정형 파싱 드레인 (watchdog 밖, concurrency=1, 멱등).
# sources/00_inbox 의 미파싱 바이너리를 2nd-brain-parser 컨테이너로 순차 파싱.
#   PDF      → docling.json + mineru.json + diff.json (듀얼+diff, Phase 2)
#   비-PDF   → docling.json (mineru=PDF 전용, diff 불가)
# 검증·노트화(diverge 시 LLM 결정 = Phase 3)는 brainify(별도).
#
# 트리거: parser-drain.timer (host systemd-user). 게이트웨이는 파일만 드롭.
# 안정: systemd 단일인스턴스 + flock + 순차루프 = concurrency=1 (RAM 보호).
#      각 엔진 timeout 가드(MinerU CPU deadlock 등 hang 시 그 파일만 실패·계속).
set -euo pipefail

export SB_DATA="${SB_DATA:-$HOME/projects/2nd-brain-vault}"   # compose 마운트
REPO="${SECOND_BRAIN_REPO:-$HOME/projects/2nd-brain}"
INBOX="$SB_DATA/sources/00_inbox"
CMNT="/home/user/projects/2nd-brain-vault"                    # 컨테이너 내부 마운트 경로
PARSER_CLI="${PARSER_CLI:-brain-pdf}"                         # 컨테이너 내 CLI 명(이미지 0.2.0~ brain-pdf, 구명 2nd-brain-parser)
ENGINE_TIMEOUT="${ENGINE_TIMEOUT:-900}"                       # 엔진당 상한(초)
LOG="${PARSER_DRAIN_LOG:-$HOME/.local/state/parser-drain.log}"
mkdir -p "$(dirname "$LOG")"
log(){ echo "$(date -Is) $*" >>"$LOG"; }

# ── concurrency=1 ──
exec 9>"/run/user/$(id -u)/parser-drain.lock"
flock -n 9 || { log "already running, skip"; exit 0; }
[ -d "$INBOX" ] || { log "no inbox: $INBOX"; exit 0; }

# ── warm 데몬 1회 기동, 종료 시 teardown ──
cd "$REPO/docker"
mapfile -t CF < <(./scripts/detect-compose.sh)
COMPOSE=(docker compose ${CF[*]})
"${COMPOSE[@]}" up -d 2nd-brain-parser >>"$LOG" 2>&1
trap '"${COMPOSE[@]}" down >>"$LOG" 2>&1 || true' EXIT

# 엔진 1회 실행 → host 파일로 atomic 기록. $1=host출력, $2..=parser CLI 인자(컨테이너 경로)
run_to(){
  local out="$1"; shift
  local tmp="$out.tmp"
  if timeout "$ENGINE_TIMEOUT" docker exec 2nd-brain-parser "$PARSER_CLI" "$@" \
        >"$tmp" 2>>"$LOG" && [ -s "$tmp" ]; then
    mv -f "$tmp" "$out"; return 0
  fi
  rm -f "$tmp"; return 1
}

shopt -s nullglob globstar
n=0
for f in "$INBOX"/**/*.pdf "$INBOX"/**/*.hwp "$INBOX"/**/*.hwpx "$INBOX"/**/*.docx "$INBOX"/**/*.xlsx; do
  out="${f}_parse"
  ext="${f##*.}"; ext="${ext,,}"
  cpath="${f/#$SB_DATA/$CMNT}"          # host→컨테이너 입력 경로
  cout="${out/#$SB_DATA/$CMNT}"         # host→컨테이너 _parse 경로

  # 멱등: PDF=diff.json, 비-PDF=docling.json 있으면 완료로 보고 skip
  if [ "$ext" = pdf ]; then [ -s "$out/diff.json" ] && continue
  else [ -s "$out/docling.json" ] && continue; fi
  mkdir -p "$out"
  log "parse($ext): $f"

  # docling (전 포맷; 이미 있으면 재사용)
  if [ ! -s "$out/docling.json" ]; then
    run_to "$out/docling.json" parse-docling "$cpath" \
      || { log "FAIL docling: $f"; : >"$out/.parse-error"; continue; }
  fi

  if [ "$ext" != pdf ]; then
    log "ok(single non-PDF): $f"; n=$((n+1)); continue
  fi

  # PDF: mineru (재사용) + diff
  if [ ! -s "$out/mineru.json" ]; then
    run_to "$out/mineru.json" parse-mineru "$cpath" || log "WARN mineru 실패(docling-only): $f"
  fi
  if [ -s "$out/mineru.json" ] && [ ! -s "$out/diff.json" ]; then
    if run_to "$out/diff.json" diff "$cout/docling.json" "$cout/mineru.json"; then
      v=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('verdict','?'))" "$out/diff.json" 2>/dev/null || echo '?')
      log "ok(dual,verdict=$v): $f"; n=$((n+1))
    else
      log "WARN diff 실패(docling+mineru는 있음): $f"; n=$((n+1))
    fi
  else
    log "ok(docling-only, mineru 없음): $f"; n=$((n+1))
  fi
done
log "drain done ($n processed)"
