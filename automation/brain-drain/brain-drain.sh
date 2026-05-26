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
CAP_REFINE="${CAP_REFINE:-0.50}"                 # diverge refine 항목당 $ 상한
CAP_BRAINIFY="${CAP_BRAINIFY:-0.75}"             # brainify 항목당 $ 상한
CAP_GLOBAL="${CAP_GLOBAL:-5.00}"                 # 드레인 1회 누적 $ 상한
LOG="${BRAIN_DRAIN_LOG:-$HOME/.local/state/brain-drain.log}"
mkdir -p "$(dirname "$LOG")"
log(){ echo "$(date -Is) $*" >>"$LOG"; }

HEADLESS_DIRECTIVE='무인 cron 드레인에서 헤드리스로 실행 중. 사용자가 없으니 절대 질문하지 말 것.
automate-first/weekly-audit 정책: 모호하면 묻지 말고 낙관 배치 후 플래그(para_review: pending /
parse_confidence|refine_confidence: low). 이미 처리된 항목(already_brainified / refined.md 존재)은 skip.
반드시 helper(refine.py/brainify.py)로 commit 하거나, 사유를 남기고 skip 하며 끝낼 것.'

# ── concurrency=1 (parser-drain 와 별도 락) ──
exec 9>"/run/user/$(id -u)/brain-drain.lock"
flock -n 9 || { log "already running, skip"; exit 0; }
command -v "$CLAUDE_BIN" >/dev/null 2>&1 || { log "no claude: $CLAUDE_BIN"; exit 0; }

SPENT="0"
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
    rc=$?; log "claude FAIL/timeout (rc=$rc): $prompt"; rm -f "$tmp"; return 1
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
  rm -f "$tmp"
  SPENT="$(python3 -c "print(round(float('$SPENT')+float('$cost'),6))")"
  if [ "$err" = 1 ]; then log "claude is_error (\$$cost, ${turns}t, run=\$$SPENT): $prompt"; return 1; fi
  log "claude ok (\$$cost, ${turns}t, run=\$$SPENT): $prompt"; return 0
}

# ── Phase R: refine ──
log "=== brain-drain start ==="
refine_json="$(python3 "$REFINE_PY" scan 2>>"$LOG" || echo '{}')"
while IFS=$'\t' read -r action pdir; do
  [ -z "$action" ] && continue
  case "$action" in
    promote)
      if python3 "$REFINE_PY" promote "$pdir" >>"$LOG" 2>&1; then log "promote ok: $pdir"
      else log "promote FAIL: $pdir"; fi ;;
    refine)
      claude_run "/refine --headless \"$pdir\"" "$CAP_REFINE" || true ;;
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
brainify_json="$(python3 "$BRAINIFY_PY" scan 2>>"$LOG" || echo '{}')"
while IFS= read -r item; do
  [ -z "$item" ] && continue
  claude_run "/brainify --headless \"$item\"" "$CAP_BRAINIFY" || true
done < <(python3 - <<PY
import json
d=json.loads('''$brainify_json''' or '{}')
for it in d.get("items",[]):
    if not it.get("already_brainified"):
        print(it["item"])
PY
)

log "=== brain-drain done (run=\$$SPENT) ==="
