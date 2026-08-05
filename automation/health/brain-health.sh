#!/usr/bin/env bash
# brain-health — 2nd-brain 아침 헬스체크·보고 (호스트 systemd 타이머로 매일 1회).
#
#   ① 진찰: health-check.py --summary  → JSON 결과 기록 (부작용 0, 읽기·상태조회만)
#   ② 보고: health-report.py           → 텔레그램 아침 보고 (정상이어도 매일 한 통 = 하트비트)
#   ③ 생존신호: HEALTH_PING_URL 이 있으면 GET (dead man's switch — 아래 참조)
#
# ★ 순서가 핵심이다. 진찰이 실패했다고 여기서 스크립트를 끊으면 **"이상 감지" 보고 자체가
#   발송되지 못한다.** 그래서 실패를 일단 삼키고 → 보고를 먼저 보내고 → 마지막에 다시
#   exit 로 표면화한다(radsafety-pwa health.yml 의 continue-on-error 와 같은 트릭).
#
# ★ 감시자는 감시 대상 밖에 산다. 이 스크립트는 **호스트**에서 돌고 컨테이너를 들여다본다.
#   OpenClaw 안에서 OpenClaw 를 감시하면 게이트웨이가 죽는 순간 보고도 같이 죽는다.
#   같은 이유로 텔레그램 발송도 게이트웨이를 경유하지 않고 봇 API 를 직접 친다.
#
# ★ dead man's switch (3층) — 이 스크립트가 아예 못 돌면(PC 종료·정전·WSL2 VM 종료)
#   텔레그램도 안 오는데, "안 오는 게 정상인지 죽은 건지" 구별이 안 된다. HEALTH_PING_URL
#   (healthchecks.io 등)을 설정하면 밖에 있는 서비스가 ping 두절을 대신 알려준다.
#   설정 전에는 이 단계가 조용히 생략된다.
#
# on/off 는 env 파일 한 줄로 (코드 변경·재설치 불필요):
#   HEALTH_REPORT=all   기본 — 정상/이상 매일 보고
#   HEALTH_REPORT=fail  이상일 때만 보고(정상은 침묵)
#   HEALTH_REPORT=off   보고 끔(점검·로그는 유지)
#
# 즉시 1회 실행:  systemctl --user start brain-health.service
# 문안만 보기:    HEALTH_REPORT=off ... 대신  python3 health-check.py --summary /tmp/h.json;
#                 HEALTH_TG_TOKEN= python3 health-report.py /tmp/h.json
set -uo pipefail   # -e 는 쓰지 않는다 — 점검 실패로 보고가 건너뛰어지면 안 된다.

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="${HEALTH_STATE_DIR:-$HOME/.local/state}"
SUMMARY="${HEALTH_SUMMARY:-$STATE/brain-health.json}"
LOG="${HEALTH_LOG:-$STATE/brain-health.log}"
mkdir -p "$STATE"
log(){ echo "$(date -Is) $*" >>"$LOG"; }

# 머신별 설정(토큰·임계·유닛 목록)은 여기서 읽는다. git 미추적 — 머신마다 다르다.
[ -f "$HOME/.config/2nd-brain/health.env" ] && . "$HOME/.config/2nd-brain/health.env"

log "=== brain-health start ==="

# ── ① 진찰 — 실패해도 여기서 끊지 않는다 ──
python3 "$DIR/health-check.py" --summary "$SUMMARY" >>"$LOG" 2>&1
CHECK_RC=$?
log "check rc=$CHECK_RC (0=정상 1=문제 2=경고)"

# ── ② 보고 — 진찰이 실패했어도 반드시 보낸다 ──
python3 "$DIR/health-report.py" "$SUMMARY" >>"$LOG" 2>&1 \
  || log "report FAILED (보고 발송 실패 — 점검 결과는 $SUMMARY 에 남음)"

# ── ③ 생존신호 — 전부 정상일 때만. 문제가 있으면 ping 을 끊어 밖에서도 알아채게 한다 ──
if [ -n "${HEALTH_PING_URL:-}" ] && [ "$CHECK_RC" = 0 ]; then
  curl -fsS --max-time 15 "$HEALTH_PING_URL" >/dev/null 2>>"$LOG" || log "ping failed (non-fatal)"
fi

log "=== brain-health done ==="

# 문제가 있었다면 유닛도 실패로 — systemctl --user --failed 에 남겨 두 번째 흔적을 만든다.
# (경고만 있는 경우는 성공으로 둔다. 경고까지 붉히면 붉은색이 의미를 잃는다.)
[ "$CHECK_RC" = 1 ] && exit 1
exit 0
