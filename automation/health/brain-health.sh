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
SENT_MARK="${HEALTH_SENT_MARK:-$STATE/brain-health.sent}"   # 마지막으로 *보고에 성공한* 날짜
mkdir -p "$STATE"
log(){ echo "$(date -Is) $*" >>"$LOG"; }

# 머신별 설정(토큰·임계·유닛 목록)은 여기서 읽는다. git 미추적 — 머신마다 다르다.
# ★ 명령줄로 넘긴 HEALTH_REPORT 는 파일보다 우선한다(2026-08-05). 예전엔 파일이 덮어써서
#   `HEALTH_REPORT=off bash brain-health.sh` 로 테스트해도 **실제 텔레그램이 나갔다** —
#   실측으로 한 통 오발송하고 알았다. 파일은 상시 설정, 인라인 env 는 1회 실행용이 맞다.
_cli_report="${HEALTH_REPORT-}"
[ -f "$HOME/.config/2nd-brain/health.env" ] && . "$HOME/.config/2nd-brain/health.env"
[ -n "$_cli_report" ] && HEALTH_REPORT="$_cli_report"

# ── ⓪ 하루 1회 가드 — 원인 불문 중복 방어선 (2026-08-05) ──
#
# 2026-08-05 아침, 같은 보고가 **15통** 갔다. 원인은 WSL2 시계가 두 시각(4분 27초 차) 사이를
# 왕복해 OnCalendar 타이머가 06:40 을 반복해서 "아직 안 지났다"로 재계산한 것이었다.
# 그 시계 문제는 Windows 를 NTP 에 물려 고쳤지만, **이 가드는 원인을 묻지 않는다** —
# 타이머 오발화·수동 중복 실행·미래의 다른 사고 무엇이든 하루 한 통으로 막는다.
#
# ★ 마커는 "실행했다"가 아니라 **"보고 발송에 성공했다"** 를 기록한다. 발송이 실패한 날은
#   마커가 없어 다음 발화가 다시 시도한다 — 가드가 침묵을 굳혀 버리면 안 되기 때문이다.
# ★ Persistent=true 로 부팅 직후 밀린 아침이 발화하는 경로는 그대로 산다(날짜가 다르므로).
# 강제 실행: HEALTH_FORCE=1 systemctl --user start brain-health.service (또는 직접 실행)
TODAY="$(date +%F)"
if [ "${HEALTH_FORCE:-0}" != 1 ] && [ "$(cat "$SENT_MARK" 2>/dev/null)" = "$TODAY" ]; then
  log "이미 오늘($TODAY) 보고 완료 — skip (HEALTH_FORCE=1 로 강제 가능)"
  exit 0
fi

log "=== brain-health start ==="

# ── ① 진찰 — 실패해도 여기서 끊지 않는다 ──
python3 "$DIR/health-check.py" --summary "$SUMMARY" >>"$LOG" 2>&1
CHECK_RC=$?
log "check rc=$CHECK_RC (0=정상 1=문제 2=경고)"

# ── ② 보고 — 진찰이 실패했어도 반드시 보낸다 ──
# 마커는 **실제로 한 통 나갔을 때만**(rc=0) 남긴다. rc=2(정책·자격으로 미발송)에 마커를 찍으면
# HEALTH_REPORT=fail 모드에서 "아침엔 정상 → 마커 → 낮에 이상이 생겨도 가드에 막혀 침묵"이 된다.
python3 "$DIR/health-report.py" "$SUMMARY" >>"$LOG" 2>&1; REPORT_RC=$?
case "$REPORT_RC" in
  0) echo "$TODAY" >"$SENT_MARK"; log "report sent — 오늘($TODAY) 마커 기록" ;;
  2) log "report 미발송(정책·자격 미설정) — 마커 미기록(가드 걸지 않음)" ;;
  *) log "report FAILED (발송 실패 — 점검 결과는 $SUMMARY 에 남음. 마커 미기록 → 다음 발화가 재시도)" ;;
esac

# ── ③ 생존신호 — 전부 정상일 때만. 문제가 있으면 ping 을 끊어 밖에서도 알아채게 한다 ──
if [ -n "${HEALTH_PING_URL:-}" ] && [ "$CHECK_RC" = 0 ]; then
  curl -fsS --max-time 15 "$HEALTH_PING_URL" >/dev/null 2>>"$LOG" || log "ping failed (non-fatal)"
fi

log "=== brain-health done ==="

# 문제가 있었다면 유닛도 실패로 — systemctl --user --failed 에 남겨 두 번째 흔적을 만든다.
# (경고만 있는 경우는 성공으로 둔다. 경고까지 붉히면 붉은색이 의미를 잃는다.)
[ "$CHECK_RC" = 1 ] && exit 1
exit 0
