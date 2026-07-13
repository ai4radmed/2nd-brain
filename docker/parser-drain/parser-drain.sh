#!/usr/bin/env bash
# parser-drain — host-측 결정형 파싱 드레인 (watchdog 밖, concurrency=1, 멱등).
# sources/00_inbox 의 미파싱 바이너리를 2nd-brain-parser 컨테이너로 순차 파싱.
#   PDF      → docling.json + mineru.json + diff.json (듀얼+diff, Phase 2)
#   비-PDF   → docling.json (mineru=PDF 전용, diff 불가)
#   이미지   → ocr.json (parse-ocr; device-adaptive 로컬 OCR, docling/mineru N/A)
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

# ── HWP/HWPX: 호스트-측 추출(컨테이너 우회) → refined.md 직접 생산 ──
# 근거: 컨테이너 soffice+H2Orestart 경로는 headless user-프로필 미초기화로 실패 잦고
#       hwpx 표를 버린다. 호스트엔 검증된 우월 경로(OWPML 직독 + soffice→docx→pandoc)가 있다.
#       HWP 는 단일소스(mineru N/A·diff 불가)라 refine 이 no-op → 추출=refine 한 번에, refined.md 직접.
#       brainify `_refined()` 가 이 refined.md 를 소비(컨테이너 안 탐). 멱등: refined.md 있으면 skip.
HWP_REFINE="$REPO/docker/parser-drain/hwp_refine.py"
for f in "$INBOX"/**/*.hwp "$INBOX"/**/*.hwpx; do
  [[ "$f" == *_parse/* ]] && continue          # 파싱 산출물 내부 제외
  out="${f}_parse"
  [ -s "$out/refined.md" ] && continue           # 멱등
  log "parse(hwp,host): $f"
  if python3 "$HWP_REFINE" "$f" >>"$LOG" 2>&1; then
    log "ok(hwp,host): $f"; n=$((n+1))
  else
    log "FAIL hwp(host): $f"                       # hwp_refine 이 .parse-error 마커 기록
  fi
done

# ── PDF·docx·xlsx: 컨테이너(2nd-brain-parser) 경로 ──
for f in "$INBOX"/**/*.pdf "$INBOX"/**/*.docx "$INBOX"/**/*.xlsx; do
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

# ── 이미지: parse-ocr 단일 → ocr.json (전략 §이미지 OCR — device-adaptive) ──
# docling/mineru 대신 OCR. ⚠️ _parse/ 하위(mineru 가 추출한 figure 이미지)는 제외 —
# 안 그러면 추출 figure 를 재-OCR 하는 무한 증식. 멱등: ocr.json 있으면 skip.
for f in "$INBOX"/**/*.png "$INBOX"/**/*.jpg "$INBOX"/**/*.jpeg "$INBOX"/**/*.webp "$INBOX"/**/*.tiff; do
  [[ "$f" == *_parse/* ]] && continue       # 파싱 산출물 내부 이미지 제외
  out="${f}_parse"
  ext="${f##*.}"; ext="${ext,,}"
  cpath="${f/#$SB_DATA/$CMNT}"               # host→컨테이너 입력 경로
  [ -s "$out/ocr.json" ] && continue         # 멱등
  mkdir -p "$out"
  log "parse(ocr:$ext): $f"
  if run_to "$out/ocr.json" parse-ocr "$cpath"; then
    log "ok(ocr): $f"; n=$((n+1))
  else
    log "FAIL ocr: $f"; : >"$out/.parse-error"
  fi
done

# ── 오디오: 폰 ingress 복사 + 호스트-측 전사(faster-whisper) → refined.md 직접 ──
# 폰(SyncThing receive-only, 볼트 밖) → inbox 복사(ledger 멱등) → 로컬 GPU 전사.
# receive-only 폴더에서 move 금지(SyncThing 이 복원함) → copy + ledger(이름:크기).
# whisper venv 부재 머신(예: GPU 점유 노트북)은 루프째 skip — device-adaptive,
# 머신-specific 하드코딩 없음. 클라우드 STT 배제(이미지 OCR 과 동일 원칙).
AUDIO_VENV="${AUDIO_VENV:-$HOME/.venvs/whisper}"
AUDIO_INGRESS="${AUDIO_INGRESS:-$HOME/phone-ingress/voice}"
AUDIO_REFINE="$REPO/docker/parser-drain/audio_refine.py"
AUDIO_LEDGER="${AUDIO_LEDGER:-$HOME/.local/state/audio-ingress.ledger}"

if [ -x "$AUDIO_VENV/bin/python" ]; then
  # ① ingress → inbox 복사 (brainify 가 inbox 밖으로 옮겨도 ledger 가 재복사 방지)
  if [ -d "$AUDIO_INGRESS" ]; then
    touch "$AUDIO_LEDGER"
    for f in "$AUDIO_INGRESS"/**/*.m4a "$AUDIO_INGRESS"/**/*.mp3 \
             "$AUDIO_INGRESS"/**/*.wav "$AUDIO_INGRESS"/**/*.ogg \
             "$AUDIO_INGRESS"/**/*.opus "$AUDIO_INGRESS"/**/*.aac \
             "$AUDIO_INGRESS"/**/*.amr; do
      base="$(basename "$f")"; key="$base:$(stat -c%s "$f")"
      if ! grep -qxF "$key" "$AUDIO_LEDGER"; then
        dest="$INBOX/${base// /_}"                 # 공백→_ (파일명 규칙)
        if [ ! -e "$dest" ]; then cp "$f" "$dest"; fi
        echo "$key" >>"$AUDIO_LEDGER"
        log "ingress(audio): $base"
      fi
    done
  fi

  # ② inbox 전사 — 미처리분 모아 1회 호출(모델 1회 로드). 멱등: refined.md 있으면 skip.
  pending=()
  for f in "$INBOX"/**/*.m4a "$INBOX"/**/*.mp3 "$INBOX"/**/*.wav \
           "$INBOX"/**/*.ogg "$INBOX"/**/*.opus "$INBOX"/**/*.aac \
           "$INBOX"/**/*.amr; do
    [[ "$f" == *_parse/* ]] && continue
    [ -s "${f}_parse/refined.md" ] && continue
    pending+=("$f")
  done
  if [ "${#pending[@]}" -gt 0 ]; then
    log "parse(audio,host): ${#pending[@]} file(s)"
    if timeout $((ENGINE_TIMEOUT * ${#pending[@]})) \
         "$AUDIO_VENV/bin/python" "$AUDIO_REFINE" "${pending[@]}" >>"$LOG" 2>&1; then
      n=$((n + ${#pending[@]}))
      log "ok(audio): ${#pending[@]} file(s)"
    else
      log "WARN audio 일부/전부 실패 (개별 .parse-error 참조)"
    fi
  fi
fi

log "drain done ($n processed)"
