#!/usr/bin/env bash
# brain-drain — host-측 refine·brainify 자동 드레인 (parser-drain 의 형제, claude -p 헤드리스).
#
#   Phase R (refine): refine.py scan →
#       action=promote → refine.py promote        (결정형, claude 0)
#       action=refine  → claude -p "/refine --headless <dir>"   (diverge 만, vision, 1건씩)
#   Phase B (brainify): brainify.py scan →
#       미brainify 항목 → claude -p "/brainify --headless <item>"  (판단+commit, 1건씩)
#
# 트리거: brain-drain.timer (host systemd-user, OnUnitInactiveSec=10min).
# parser-drain 와 분리(file-state 로만 연결: refined.md / dedup 마커). 서로 호출 안 함.
# 안전: 별도 flock(concurrency=1) + per-item 실패격리 + 항목당·드레인당 비용상한.
# 정책: automate-first/weekly-audit — 헤드리스는 묻지 않고 낙관배치+플래그(주간 감사가 교정).
set -euo pipefail

export SB_DATA="${SB_DATA:-$HOME/projects/2nd-brain-vault}"   # 정본 vault (= REFINE_VAULT/BRAINIFY_VAULT)
export REFINE_VAULT="$SB_DATA"
export BRAINIFY_VAULT="$SB_DATA"
REFINE_PY="${REFINE_PY:-$HOME/.claude/skills/refine/refine.py}"
BRAINIFY_PY="${BRAINIFY_PY:-$HOME/.claude/skills/brainify/brainify.py}"
CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.local/bin/claude}"
MODEL="${BRAIN_DRAIN_MODEL:-claude-opus-4-7}"
CLAUDE_TIMEOUT="${CLAUDE_TIMEOUT:-600}"          # claude 호출당 상한(초)
CAP_REFINE="${CAP_REFINE:-2.50}"                 # diverge refine 항목당 $ 상한 (2026-07-03: 0.50→1.50→2.50. 대용량 다페이지 한글PDF 비전검증이 $0.9 안팎+스파이크로 $1.5 초과 abort→재시도마다 ~$1.5 헛번. cap 올려 1회 완주가 더 쌈)
CAP_BRAINIFY="${CAP_BRAINIFY:-1.50}"             # brainify 항목당 토큰-환산 상한 (2026-07-03: 0.75→1.50. refine 과 동일 — 큰 문서 brainify 가 $0.75 코앞이라 순간초과 abort→재시도-번. 값은 토큰×정가 환산, 실결제 아님)
CAP_GLOBAL="${CAP_GLOBAL:-50.00}"                # 드레인 1회 누적 토큰-환산 상한 (2026-07-03: 5→50. MAX 요금제는 건당결제 아닌 사용량한도라 달러-스로틀 무의미 → 백필 가속. 한 런이 ~50건 소진 후 2분 뒤 재발화=거의 연속. 실결제 아님)
LOG="${BRAIN_DRAIN_LOG:-$HOME/.local/state/brain-drain.log}"
mkdir -p "$(dirname "$LOG")"
log(){ echo "$(date -Is) $*" >>"$LOG"; }

# ── Telegram 활동 보고 (옵션2: 처리한 항목이 있을 때만 발송, 빈 실행은 침묵) ──
# 봇 토큰 = host-local openclaw.json(미동기 secret) 재사용. chat = Dr. Ben. 둘 다 env 오버라이드.
# 문안 생성·발송 자체는 drain-report.py 가 진다(아래 보고 블록). 여기서는 자격만 정한다.
TG_CHAT="${BRAIN_DRAIN_TG_CHAT:-8669227844}"
OPENCLAW_JSON="${OPENCLAW_JSON:-$HOME/.openclaw/openclaw.json}"

HEADLESS_DIRECTIVE='무인 cron 드레인에서 헤드리스로 실행 중. 사용자가 없으니 절대 질문하지 말 것.
automate-first/weekly-audit 정책: 모호하면 묻지 말고 낙관 배치 후 플래그(para_review: pending /
parse_confidence|refine_confidence: low). 이미 처리된 항목(already_brainified / refined.md 존재)은 skip.
반드시 helper(refine.py/brainify.py)로 commit 하거나, 사유를 남기고 skip 하며 끝낼 것.'

# ── concurrency=1 (parser-drain 와 별도 락) ──
exec 9>"/run/user/$(id -u)/brain-drain.lock"
flock -n 9 || { log "already running, skip"; exit 0; }
command -v "$CLAUDE_BIN" >/dev/null 2>&1 || { log "no claude: $CLAUDE_BIN"; exit 0; }

SPENT="0"
REFINED_N=0; BRAINIFIED_N=0; RENOTED_N=0; FAIL_N=0; BUDGET_HIT=0   # 활동 카운터(끝에서 Telegram 보고 판단)
budget_left(){ python3 -c "import sys;print(1 if float('$SPENT')<float('$CAP_GLOBAL') else 0)"; }

# claude -p 1회. $1=슬래시 프롬프트, $2=항목 $ 상한. 반환 0=ok,1=실패,2=예산소진
claude_run(){
  local prompt="$1" cap="$2" tmp rc
  if [ "$(budget_left)" != 1 ]; then
    log "BUDGET exhausted (\$$SPENT/\$$CAP_GLOBAL) — skip: $prompt"; return 2
  fi
  tmp="$(mktemp)"
  if ( cd "$SB_DATA" && timeout "$CLAUDE_TIMEOUT" "$CLAUDE_BIN" -p "$prompt" \
        --model "$MODEL" --permission-mode bypassPermissions \
        --output-format json --max-budget-usd "$cap" \
        --append-system-prompt "$HEADLESS_DIRECTIVE" ) >"$tmp" 2>>"$LOG"; then
    rc=0
  else
    rc=$?; log "claude FAIL/timeout (rc=$rc): $prompt"
    # 실패 원인 진단용 — 출력 꼬리 보존(그동안 버려져서 rc=1 원인 추적 불가였음. 2026-07-16)
    log "claude FAIL output tail: $(tail -c 2000 "$tmp" 2>/dev/null | tr '\n' ' ')"
    rm -f "$tmp"; return 1
  fi
  # total_cost_usd 누적 + is_error 점검
  read -r err cost turns < <(python3 - "$tmp" <<'PY'
import json,sys
try:
    d=json.load(open(sys.argv[1]))
    print(int(bool(d.get("is_error"))), d.get("total_cost_usd",0), d.get("num_turns",0))
except Exception:
    print(1,0,0)
PY
)
  if [ "$err" = 1 ]; then
    SPENT="$(python3 -c "print(round(float('$SPENT')+float('$cost'),6))")"
    log "claude is_error (\$$cost, ${turns}t, run=\$$SPENT): $prompt"
    log "claude is_error output tail: $(tail -c 2000 "$tmp" 2>/dev/null | tr '\n' ' ')"
    rm -f "$tmp"; return 1
  fi
  rm -f "$tmp"
  SPENT="$(python3 -c "print(round(float('$SPENT')+float('$cost'),6))")"
  log "claude ok (\$$cost, ${turns}t, run=\$$SPENT): $prompt"; return 0
}

# ── Phase R: refine ──
# 스캔 범위 = sources 전체(2026-08-05). 예전엔 기본값(00_inbox)만 봐서, PARA 로 분류돼 인박스를
# 떠난 자료의 _parse 는 영원히 refine 되지 않았다 — 실측 결과 그렇게 묶인 게 72건이었는데
# 드레인은 매번 "refine 0건"을 보고했다. refined.md 가 없으면 brainify 가 stub(parse_confidence:low)을
# 쓰므로, 그 침묵이 곧 파싱오류 플래그의 공급원이었다.
# 정렬상 sources/00_inbox 가 먼저 나오므로 신규 유입이 여전히 우선 처리된다.
log "=== brain-drain start ==="
refine_json="$(python3 "$REFINE_PY" scan --root "$SB_DATA/sources" 2>>"$LOG" || echo '{}')"
while IFS=$'\t' read -r action pdir; do
  [ -z "$action" ] && continue
  case "$action" in
    promote)
      if python3 "$REFINE_PY" promote "$pdir" >>"$LOG" 2>&1; then log "promote ok: $pdir"; REFINED_N=$((REFINED_N+1))
      else log "promote FAIL: $pdir"; FAIL_N=$((FAIL_N+1)); fi ;;
    refine)
      claude_run "/refine --headless \"$pdir\"" "$CAP_REFINE" && rc=0 || rc=$?
      # 사후 커밋 검증(2026-07-16): 작업을 끝내고 종료만 비정상인 false-fail 억제 —
      # refined.md 가 생겼으면 완료로 재집계 (실사례: 커밋 후 rc=1 로 죽어 '⚠ 실패' 오보고)
      if [ "${rc:-1}" = 1 ] && { [ -f "$pdir/refined.md" ] || [ -f "$SB_DATA/$pdir/refined.md" ]; }; then
        log "post-check: refined.md 존재 — 완료(비정상 종료)로 재집계: $pdir"; rc=0
      fi
      case "${rc:-1}" in 0) REFINED_N=$((REFINED_N+1));; 2) BUDGET_HIT=1;; *) FAIL_N=$((FAIL_N+1));; esac ;;
  esac
done < <(python3 - <<PY
import json
d=json.loads('''$refine_json''' or '{}')
for it in d.get("items",[]):
    a=it.get("action","")
    if a in ("promote","refine"):
        print(f"{a}\t{it['parse_dir']}")
PY
)

# ── Phase B: brainify ──
# 오디오(폰 음성녹음)는 제외 — 선별 게이트(2026-07-13): 전사(parser-drain)까지만 자동,
# PARA 편입은 Dr. Ben 지시의 대화형 /brainify 전용(사적 녹음이 무인 편입되는 것 방지).
# 해당 항목은 00_inbox 에 남는 게 정상. 권위: brainify SKILL §오디오 + workflows/mobile-voice-capture.md
brainify_json="$(python3 "$BRAINIFY_PY" scan 2>>"$LOG" || echo '{}')"
while IFS= read -r item; do
  [ -z "$item" ] && continue
  claude_run "/brainify --headless \"$item\"" "$CAP_BRAINIFY" && rc=0 || rc=$?
  # 사후 커밋 검증(2026-07-16): false-fail '⚠ 실패' 텔레그램 오보고 억제.
  # ① 인박스에서 사라짐(이동 커밋) ② 남아 있어도 scan 이 already_brainified 판정(노트 커밋)
  # — 어느 쪽이든 작업은 끝났고 종료만 비정상이었던 것 → 완료로 재집계.
  if [ "${rc:-1}" = 1 ]; then
    case "$item" in /*) probe="$item";; *) probe="$SB_DATA/sources/00_inbox/$item";; esac
    if [ ! -e "$probe" ]; then
      log "post-check: 인박스에서 이동됨(커밋) — 완료(비정상 종료)로 재집계: $item"; rc=0
    elif python3 "$BRAINIFY_PY" scan 2>/dev/null | ITEM="$item" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
hit = next((it for it in d.get("items", []) if it.get("item") == os.environ["ITEM"]), None)
sys.exit(0 if hit and hit.get("already_brainified") else 1)
'; then
      log "post-check: already_brainified 판정(노트 커밋) — 완료(비정상 종료)로 재집계: $item"; rc=0
    fi
  fi
  case "${rc:-1}" in 0) BRAINIFIED_N=$((BRAINIFIED_N+1));; 2) BUDGET_HIT=1;; *) FAIL_N=$((FAIL_N+1));; esac
done < <(python3 - <<PY
import json
AUDIO = (".m4a", ".mp3", ".wav", ".ogg", ".opus", ".aac", ".amr")
d=json.loads('''$brainify_json''' or '{}')
for it in d.get("items",[]):
    if it.get("already_brainified"):
        continue
    if it["item"].lower().endswith(AUDIO):
        continue                      # 선별 게이트 — 대화형 brainify 전용
    print(it["item"])
PY
)

# ── Phase C: renote — 뒤늦게 도착한 풀텍스트로 stub 노트 재작성 (2026-08-05 신설) ──
# parse_confidence:low 는 "노트를 쓸 때 refined.md 가 없었다"는 뜻인데, Phase R 이 나중에 그걸
# 만들어도 노트는 저절로 안 고쳐진다(Phase B 의 scan 은 인박스 미처리 항목만 본다). 그 틈에서
# 파싱은 끝났는데 플래그만 남아 매일 '파싱오류'로 보고되던 게 이 Phase 의 존재 이유다.
# ready(_parse 전부에 refined.md 존재)만 집는다 — 아직 refine 대기인 건 다음 틱이 채운다.
while IFS= read -r note; do
  [ -z "$note" ] && continue
  [ "$(budget_left)" = 1 ] || { BUDGET_HIT=1; log "budget hit — renote 중단"; break; }
  claude_run "/brainify --headless --renote \"$note\"" "$CAP_BRAINIFY" && rc=0 || rc=$?
  # 사후 검증: renote-write 가 남기는 renoted: 마커가 생겼으면 완료(종료만 비정상인 false-fail 억제).
  if [ "${rc:-1}" = 1 ] && grep -q "^renoted:" "$SB_DATA/$note" 2>/dev/null; then
    log "post-check: renoted 마커 존재 — 완료(비정상 종료)로 재집계: $note"; rc=0
  fi
  case "${rc:-1}" in 0) RENOTED_N=$((RENOTED_N+1));; 2) BUDGET_HIT=1;; *) FAIL_N=$((FAIL_N+1));; esac
done < <(python3 "$BRAINIFY_PY" renote-scan 2>>"$LOG" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for it in d.get("items", []):
    if it.get("ready"):
        print(it["note"])
')

log "=== brain-drain done (run=\$$SPENT) ==="

# ── 활동 보고 (Telegram) — 처리한 항목이 있을 때만. 빈 실행(inbox 0)은 침묵 → 스팸 없음 ──
# 문안 생성·발송은 drain-report.py 가 전담한다(2026-08-05). 이 보고와 아침 brain-health 보고가
# 같은 방에 섞여 오므로 문법을 통일했다 — 번호식·무이모지·줄끝 [o]/[!]/[x]. 규약 원본은
# automation/health/health-report.py 의 docstring.
ACTIVITY=$((REFINED_N + BRAINIFIED_N + RENOTED_N + FAIL_N))
if [ "$ACTIVITY" -gt 0 ]; then
  BRAINIFY_PY="$BRAINIFY_PY" \
  BRAIN_DRAIN_TG_TOKEN="${BRAIN_DRAIN_TG_TOKEN:-}" BRAIN_DRAIN_TG_CHAT="$TG_CHAT" \
  OPENCLAW_JSON="$OPENCLAW_JSON" \
  python3 "$(dirname "${BASH_SOURCE[0]}")/drain-report.py" \
    --refine "$REFINED_N" --brainify "$BRAINIFIED_N" --renote "$RENOTED_N" \
    --fail "$FAIL_N" --budget "$BUDGET_HIT" \
    >>"$LOG" 2>&1 || log "tg: report failed (non-fatal — 드레인 결과는 유효)"
  log "tg: report sent (refine=$REFINED_N brainify=$BRAINIFIED_N renote=$RENOTED_N fail=$FAIL_N budget=$BUDGET_HIT)"
fi
