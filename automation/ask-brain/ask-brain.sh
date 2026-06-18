#!/usr/bin/env bash
# ask-brain runner (host) — 공유 큐의 질문 job 을 집어 vault 를 검색·추론(claude -p, READ ONLY)하고
# 결과를 OpenClaw 게이트웨이 경유로 텔레그램에 회신한다. brain-drain 의 형제(타이머가 아니라 요청-구동 path 유닛).
#
# 보안 경계: vault 는 컨테이너에 마운트하지 않는다. 호스트의 이 러너만 vault 를 읽고, "답만" 텔레그램으로 건너간다.
# read-only 강제: --allowedTools 로 읽기 도구만 화이트리스트(Edit/Write 불가). ⚠ 정확한 flag 표기는 claude 버전에 따라
# 검증 필요(아래 TODO). 프롬프트에도 READ ONLY 를 명시해 이중 방어.
set -uo pipefail

VAULT="${ASK_BRAIN_VAULT:-$HOME/projects/2nd-brain-vault}"
QDIR="${ASK_BRAIN_QDIR:-$HOME/.openclaw/workspace/ask-brain-queue/jobs}"
DONE="${ASK_BRAIN_DONE:-$HOME/.openclaw/workspace/ask-brain-queue/done}"
CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.local/bin/claude}"
# sonnet = vault RAG 의 sweet spot(추론·인용 우수, opus 대비 명목단가 ~1/5 + Max 사용량도 덜 먹음).
MODEL="${ASK_BRAIN_MODEL:-claude-sonnet-4-6}"
CLAUDE_TIMEOUT="${CLAUDE_TIMEOUT:-300}"          # 질문당 상한(초)
# 예산 캡 제거(2026-06-18): Dr. Ben 은 Max/OAuth 구독이라 토큰당 과금 없음 → --max-budget-usd 안전브레이크 불필요.
# 폭주 방지는 timeout(CLAUDE_TIMEOUT, 질문당 300초)이 담당. 다시 걸려면 claude 호출에 --max-budget-usd 추가.
DEFAULT_TARGET="${ASK_BRAIN_TARGET:-}"           # 회신 대상 기본값(단일 사용자 MVP — service Environment 로 주입)
LOG="${ASK_BRAIN_LOG:-$HOME/.local/state/ask-brain.log}"

mkdir -p "$(dirname "$LOG")" "$QDIR" "$DONE"
log(){ echo "$(date -Is) $*" >>"$LOG"; }

# concurrency=1
exec 9>"/run/user/$(id -u)/ask-brain.lock"
flock -n 9 || { log "already running, skip"; exit 0; }
command -v "$CLAUDE_BIN" >/dev/null 2>&1 || { log "no claude: $CLAUDE_BIN"; exit 0; }

GW="$(docker ps --filter name=openclaw-gateway --format '{{.Names}}' | head -1)"
# 컨테이너 안 CLI 는 게이트웨이에 이미 인증됨 → message send 는 토큰 불필요(--token 옵션 없음, 2026-06-18 실측).

# 게이트웨이 경유 텔레그램 송신. $1=target $2=message
# ★ 재시도 없음(단발). 게이트웨이가 바쁘면 message send 가 'gateway timeout after 10000ms' 로 non-zero 를
#   내지만 메시지는 *이미 전달*됐을 수 있다 → 재시도하면 중복(2026-06-18 4중복 사고). 그래서 timeout 은
#   '모호=전달됐을 수도' 로 보고 재시도 안 한다. 성공 판정은 exit code 가 아니라 --json 의 ok:true 로.
# target 은 bare·telegram: 프리픽스 둘 다 허용.
send_tg(){
  local target="$1" msg="$2" out
  [ -n "$GW" ] || { log "no gateway — cannot send"; return 1; }
  msg="${msg:0:3500}"   # 텔레그램 길이 안전 컷
  out="$(docker exec "$GW" node /app/dist/index.js message send \
           --channel telegram --target "$target" --message "$msg" --json 2>>"$LOG")"
  if printf '%s' "$out" | grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
    log "sent ok: $(printf '%s' "$out" | grep -o '\"messageId\"[^,}]*' | head -1)"
    return 0
  fi
  # 모호한 실패(timeout 등): 재전송 시 중복되므로 재시도 금지. 전달됐을 수도 있음.
  log "send unconfirmed (NOT retrying to avoid duplicates): ${out:0:120}"
  return 1
}

ROLE='너는 2nd-brain vault(현재 작업 디렉터리)의 사서다. 사용자 질문에 vault 근거로 답하라.
READ ONLY — 절대 파일을 수정/생성/이동하지 말 것. knowledge/(노트)와 sources/ 를 grep·read 로 탐색하고,
동반 노트(허브)와 [[wikilink]] 를 따라가 근거를 모은 뒤 한국어 높임말로 간결히 답하라.
답 끝에 근거가 된 노트 경로 또는 [[wikilink]] 를 2~5개 인용하라.
vault 에 근거가 없으면 추측하지 말고 "vault 에서 찾지 못했습니다" 라고 솔직히 답하라.
무인 실행이라 사용자가 없다 — 절대 되묻지 말고 최선의 답을 완결하라.'

shopt -s nullglob
processed=0
for job in "$QDIR"/*.json; do
  Q="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('question',''))" "$job" 2>/dev/null || true)"
  T="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('reply_target') or '')" "$job" 2>/dev/null || true)"
  [ -n "$T" ] || T="$DEFAULT_TARGET"
  if [ -z "$Q" ]; then log "empty/invalid job, skip: $job"; mv "$job" "$DONE/" 2>/dev/null || true; continue; fi
  log "ask: $Q (target=${T:-<none>})"

  tmp="$(mktemp)"
  if ( cd "$VAULT" && timeout "$CLAUDE_TIMEOUT" "$CLAUDE_BIN" -p "$ROLE

질문: $Q" \
        --model "$MODEL" \
        --allowedTools 'Read Grep Glob Bash(grep:*) Bash(rg:*) Bash(find:*) Bash(ls:*) Bash(cat:*) Bash(head:*) Bash(tail:*)' \
        --output-format json ) >"$tmp" 2>>"$LOG"; then
    ANS="$(python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(d.get('result','') if not d.get('is_error') else '')" "$tmp" 2>/dev/null || true)"
  else
    log "claude FAIL/timeout for: $Q"; ANS=""
  fi
  rm -f "$tmp"
  [ -n "$ANS" ] || ANS="죄송합니다 — 질문 처리에 실패했습니다(호스트 로그 확인)."

  if [ -n "$T" ]; then
    send_tg "$T" "$ANS" && log "sent ok (target=$T)" || log "send FAIL (target=$T)"
  else
    log "no reply target — answer logged only: ${ANS:0:200}"
  fi
  mv "$job" "$DONE/" 2>/dev/null || rm -f "$job"
  processed=$((processed+1))
done
log "done — processed=$processed"
