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

# ── 스캔 범위: sources 전체 (2026-08-05 확대) ──────────────────────────────
# 예전엔 00_inbox 만 봤다. 그래서 PARA 로 분류돼 인박스를 떠난 자료는 파싱된 적이 없으면
# 영원히 파싱되지 않았다 — refine 이 같은 이유로 72건을 놓치고 있던 것과 **똑같은 구조 결함**의
# 추출 단계 판이다(2026-08-05 규명). refine 쪽만 고치면 짝이 안 맞아 no-extract 백로그가 남는다.
#
# ★ 확대의 대가는 크다: 확대 시점 실측 미파싱 704건(인박스 밖 699 — jpg 286·pdf 182·png 131…).
#   PDF 는 듀얼엔진(mineru 느림)이고 이미지는 OCR ~35초라 전부 갈면 십수 시간이며, PDF 파싱은
#   이어서 refine 의 diverge(비전검증=토큰) 대기열로 흘러든다. 그래서 **한 런당 상한**을 둔다 —
#   드레인이 기계를 몇 시간씩 점유하지 않고 백로그를 며칠에 걸쳐 조금씩 소화하게.
# ★ 인박스 우선: 후보 목록을 00_inbox 먼저 내보낸다. 신규 유입이 백로그 뒤에 줄서지 않게.
SOURCES_ROOT="$SB_DATA/sources"
MAX_PER_RUN="${PARSER_DRAIN_MAX_PER_RUN:-5}"     # 0 = 무제한(백로그 몰아치기용 수동 실행)
bn=0                                             # 백로그(인박스 밖) 처리 수 — 캡은 이것만 센다

# ★ 캡은 **백로그에만** 건다. 인박스는 캡과 무관하게 끝까지 비운다 —
#   안 그러면 새로 들어온 자료가 수백 건 백로그 뒤에 줄서서 며칠씩 파싱을 못 받는다
#   (첫 실측: 캡 5 를 hwp 백로그가 다 먹어 pdf·이미지 루프가 통째로 밀렸다).
#   candidates() 가 인박스분을 먼저 내보내므로, 백로그 구간에 들어선 뒤의 break 는 안전하다.
is_inbox(){ case "$1" in "$INBOX"/*) return 0;; *) return 1;; esac; }
cap_reached(){ [ "$MAX_PER_RUN" -gt 0 ] && [ "$bn" -ge "$MAX_PER_RUN" ]; }
# 백로그 항목에서만 캡을 검사·중단. 인박스면 무조건 통과.
backlog_stop(){ is_inbox "$1" && return 1; cap_reached; }
count_one(){ n=$((n+1)); is_inbox "$1" || bn=$((bn+1)); }

# 후보 경로 나열. $@ = 확장자들. 인박스분을 먼저, 그다음 sources 전체(중복은 dedup).
# 파싱 산출물 내부(`*_parse/`)는 여기서 일괄 제외 — mineru 가 뽑아 둔 figure 이미지를 다시
# OCR 하는 무한 증식을 막는다(예전엔 이미지 루프에만 있던 가드를 전 루프로 올림).
candidates(){
  local ext f
  {
    for ext in "$@"; do for f in "$INBOX"/**/*."$ext"; do printf '%s\n' "$f"; done; done
    for ext in "$@"; do for f in "$SOURCES_ROOT"/**/*."$ext"; do printf '%s\n' "$f"; done; done
  } | grep -v '_parse/' | awk '!seen[$0]++'
}

# ── HWP/HWPX: 호스트-측 추출(컨테이너 우회) → refined.md 직접 생산 ──
# 근거: 컨테이너 soffice+H2Orestart 경로는 headless user-프로필 미초기화로 실패 잦고
#       hwpx 표를 버린다. 호스트엔 검증된 우월 경로(OWPML 직독 + soffice→docx→pandoc)가 있다.
#       HWP 는 단일소스(mineru N/A·diff 불가)라 refine 이 no-op → 추출=refine 한 번에, refined.md 직접.
#       brainify `_refined()` 가 이 refined.md 를 소비(컨테이너 안 탐). 멱등: refined.md 있으면 skip.
HWP_REFINE="$REPO/docker/parser-drain/hwp_refine.py"
while IFS= read -r f; do
  backlog_stop "$f" && { log "cap($MAX_PER_RUN) 도달 — hwp 백로그 중단"; break; }
  out="${f}_parse"
  [ -s "$out/refined.md" ] && continue           # 멱등
  log "parse(hwp,host): $f"
  if python3 "$HWP_REFINE" "$f" >>"$LOG" 2>&1; then
    log "ok(hwp,host): $f"; count_one "$f"
  else
    log "FAIL hwp(host): $f"                       # hwp_refine 이 .parse-error 마커 기록
  fi
done < <(candidates hwp hwpx)

# ── PDF·docx·xlsx: 컨테이너(2nd-brain-parser) 경로 ──
while IFS= read -r f; do
  backlog_stop "$f" && { log "cap($MAX_PER_RUN) 도달 — pdf/docx/xlsx 백로그 중단"; break; }
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
    log "ok(single non-PDF): $f"; count_one "$f"; continue
  fi

  # PDF: mineru (재사용) + diff
  if [ ! -s "$out/mineru.json" ]; then
    run_to "$out/mineru.json" parse-mineru "$cpath" || log "WARN mineru 실패(docling-only): $f"
  fi
  if [ -s "$out/mineru.json" ] && [ ! -s "$out/diff.json" ]; then
    if run_to "$out/diff.json" diff "$cout/docling.json" "$cout/mineru.json"; then
      v=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('verdict','?'))" "$out/diff.json" 2>/dev/null || echo '?')
      log "ok(dual,verdict=$v): $f"; count_one "$f"
    else
      log "WARN diff 실패(docling+mineru는 있음): $f"; count_one "$f"
    fi
  else
    log "ok(docling-only, mineru 없음): $f"; count_one "$f"
  fi
done < <(candidates pdf docx xlsx)

# ── 이미지: parse-ocr 단일 → ocr.json (전략 §이미지 OCR — device-adaptive) ──
# docling/mineru 대신 OCR. ⚠️ _parse/ 하위(mineru 가 추출한 figure 이미지)는 제외 —
# 안 그러면 추출 figure 를 재-OCR 하는 무한 증식. 멱등: ocr.json 있으면 skip.
while IFS= read -r f; do
  backlog_stop "$f" && { log "cap($MAX_PER_RUN) 도달 — 이미지 백로그 중단"; break; }
  out="${f}_parse"
  ext="${f##*.}"; ext="${ext,,}"
  cpath="${f/#$SB_DATA/$CMNT}"               # host→컨테이너 입력 경로
  [ -s "$out/ocr.json" ] && continue         # 멱등
  mkdir -p "$out"
  log "parse(ocr:$ext): $f"
  if run_to "$out/ocr.json" parse-ocr "$cpath"; then
    log "ok(ocr): $f"; count_one "$f"
  else
    log "FAIL ocr: $f"; : >"$out/.parse-error"
  fi
done < <(candidates png jpg jpeg webp tiff)

# ── 오디오: 폰 ingress 복사 + 호스트-측 전사(faster-whisper) → refined.md 직접 ──
# ⚠️ 이 루프만 **인박스 전용으로 남긴다**(위 확대에서 제외). 오디오는 선별 게이트가 걸린
# 자산이라(사적 녹음의 무인 PARA 편입 금지, 2026-07-13) 범위를 넓히면 그 게이트가 무의미해진다.
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
