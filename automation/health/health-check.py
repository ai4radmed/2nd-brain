#!/usr/bin/env python3
"""
2nd-brain 헬스체크 — 진찰(점검)만 하고 결과를 JSON 으로 남긴다. 발송은 health-report.py 몫.

    python3 health-check.py [--summary <path>] [--json]

설계 원칙 (radsafety-pwa 의 아침 헬스체크에서 가져옴):
  · 결과는 두 벌 — 콘솔(사람용)과 JSON(기계용). 콘솔 문구를 바꿔도 보고가 안 깨진다.
  · 점검은 부작용 0 — 읽기·상태조회만. 쓰기·발송·재시작 없음.
  · 개별 점검의 예외는 그 항목의 fail 로 갇힌다. 하나가 깨져도 나머지 점검은 계속된다.
  · 감시자는 감시 대상 밖에 산다 — 이 스크립트는 **호스트**에서 돌고 컨테이너를 들여다본다.
    (컨테이너 안에서 컨테이너를 감시하면 컨테이너가 죽을 때 보고도 같이 죽는다.)

머신 종속 값은 전부 env 로 뺀다 — 같은 파일이 kimbi·ai4lt·홈서버에서 그대로 돌아야 한다.

exit code: 0=전부 정상, 1=fail 있음, 2=warn 만 있음.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()

# ── 환경 (머신 종속 값은 여기서만) ──────────────────────────────────────────────
VAULT = Path(os.environ.get("SB_DATA", HOME / "projects/2nd-brain-vault"))
INBOX = VAULT / "sources/00_inbox"
OPENCLAW_HOME = Path(os.environ.get("OPENCLAW_HOME", HOME / ".openclaw"))
OPENCLAW_DOCKER = Path(os.environ.get("OPENCLAW_DOCKER", HOME / "projects/openclaw-docker"))
# ask-brain 큐의 done/ — 러너가 미전송분에 *.unsent 표식을 남기는 곳(ask-brain.sh 와 같은 기본값).
ASK_BRAIN_DONE = Path(os.environ.get("ASK_BRAIN_DONE",
                                     OPENCLAW_HOME / "workspace/ask-brain-queue/done"))
CONTAINER = os.environ.get("HEALTH_CONTAINER", "2nd-brain-openclaw-gateway")
GOG_ACCOUNT = os.environ.get("GOG_ACCOUNT", "kimbi.kirams@gmail.com")

# 켜져 있어야 할 호스트 자동화 유닛. 머신마다 다르므로 env 로 덮어쓴다(공백 구분).
TIMERS = os.environ.get(
    "HEALTH_TIMERS",
    "brain-drain.timer parser-drain.timer openclaw-webmail-sidecar.timer ask-brain.path",
).split()
# 마지막 실행 결과를 볼 서비스.
SERVICES = os.environ.get("HEALTH_SERVICES", "brain-drain.service parser-drain.service").split()

INBOX_WARN = int(os.environ.get("HEALTH_INBOX_WARN", "20"))       # 인박스 적체 경고 임계
VAULT_STALE_DAYS = int(os.environ.get("HEALTH_VAULT_STALE_DAYS", "7"))
DISK_WARN_PCT = int(os.environ.get("HEALTH_DISK_WARN_PCT", "10"))  # 여유 %
REFRESH_WARN_DAYS = int(os.environ.get("HEALTH_REFRESH_WARN_DAYS", "7"))
# 라이브 인증 검증(실제 1턴 호출). doctor·auth status 는 라이브 검증을 하지 않으므로
# "설정은 멀쩡한데 실제로는 401" 을 잡으려면 이것뿐이다. 토큰 소모는 무시할 수준.
CLAUDE_LIVE = os.environ.get("HEALTH_CLAUDE_LIVE", "1") not in ("0", "false", "no")

TIMEOUT = int(os.environ.get("HEALTH_TIMEOUT", "30"))


# ── 유틸 ────────────────────────────────────────────────────────────────────────
def run(cmd: list[str] | str, timeout: int | None = None) -> tuple[int, str]:
    """명령 1회. (rc, stdout+stderr). 예외는 rc=-1 로 눌러 담는다."""
    try:
        p = subprocess.run(
            cmd,
            shell=isinstance(cmd, str),
            capture_output=True,
            text=True,
            timeout=timeout or TIMEOUT,
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except Exception as e:  # 실행 자체 실패(바이너리 없음 등)
        return -1, str(e)


class Section:
    """점검 영역 하나. add() 로 항목을 쌓는다."""

    def __init__(self, key: str, name: str):
        self.key, self.name, self.items = key, name, []

    def add(self, status: str, label: str, detail: str = "") -> None:
        self.items.append({"status": status, "label": label, "detail": detail})

    def probe(self, label: str, fn, warn_only: bool = False):
        """fn() -> (status, detail) | (bool, detail). 예외는 그 항목의 fail 로 가둔다."""
        try:
            st, detail = fn()
            if isinstance(st, bool):
                st = "ok" if st else ("warn" if warn_only else "fail")
        except Exception as e:
            st, detail = ("warn" if warn_only else "fail"), f"점검 예외: {e}"
        self.add(st, label, detail)


def days_left(epoch_ms: int) -> float:
    return (epoch_ms / 1000 - time.time()) / 86400


# ── 점검 1. 게이트웨이 (OpenClaw 컨테이너) ──────────────────────────────────────
def check_gateway() -> Section:
    s = Section("gateway", "OpenClaw 게이트웨이")

    if not shutil.which("docker"):
        s.add("fail", "docker 사용 가능", "docker 명령을 찾을 수 없음")
        return s

    rc, out = run(
        ["docker", "inspect", CONTAINER, "--format",
         "{{.State.Running}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}nohealth{{end}}|{{.Config.Image}}"]
    )
    if rc != 0:
        s.add("fail", f"컨테이너 존재 ({CONTAINER})", out.strip()[:160])
        return s

    running, health, image = (out.strip().split("|") + ["", "", ""])[:3]
    s.add("ok" if running == "true" else "fail", f"컨테이너 실행중 ({CONTAINER})",
          "" if running == "true" else "중지됨")
    if health == "nohealth":
        s.add("warn", "컨테이너 healthcheck", "이미지에 healthcheck 없음")
    else:
        s.add("ok" if health == "healthy" else "fail", "컨테이너 healthcheck", health)

    # 이미지 핀 — .env 가 선언한 버전과 실제 구동 이미지가 같은가.
    def _pin():
        env = (OPENCLAW_DOCKER / ".env").read_text(encoding="utf-8", errors="ignore")
        want = next((l.split("=", 1)[1].strip() for l in env.splitlines()
                     if l.startswith("OPENCLAW_IMAGE=")), "")
        if not want:
            return "warn", ".env 에 OPENCLAW_IMAGE 없음"
        return (image == want), f"구동 {image} / 선언 {want}"

    s.probe("이미지 버전 핀 일치", _pin)

    # dual-pin — 클론 HEAD 와 이미지 revision 이 갈리면 setup.sh 가 옵션 오류로 깨진다.
    def _dual():
        rc1, rev = run(["docker", "image", "inspect", image, "--format",
                        '{{index .Config.Labels "org.opencontainers.image.revision"}}'])
        rc2, head = run(["git", "-C", str(OPENCLAW_DOCKER), "rev-parse", "HEAD"])
        if rc1 != 0 or rc2 != 0:
            return "warn", "revision/HEAD 조회 실패"
        rev, head = rev.strip(), head.strip()
        return (rev == head), f"image {rev[:8]} / clone {head[:8]}"

    s.probe("클론·이미지 dual-pin 일치", _dual, warn_only=True)
    return s


# ── 점검 2. 인증 ────────────────────────────────────────────────────────────────
def check_auth() -> Section:
    s = Section("auth", "인증")
    creds = OPENCLAW_HOME / ".claude/.credentials.json"

    def _load():
        return json.loads(creds.read_text(encoding="utf-8")).get("claudeAiOauth", {})

    s.probe("컨테이너 Claude 자격 파일 존재", lambda: (creds.is_file(), str(creds)))

    if creds.is_file():
        # refreshToken 이 비면 만료 후 자가갱신이 불가능하다 — 이 상태는 조용히 있다가
        # 어느 날 cron 만 401 로 죽고 doctor·auth status 는 통과한다(실측 함정).
        s.probe("refresh token 보유", lambda: (bool(_load().get("refreshToken")),
                                               "" if _load().get("refreshToken") else "EMPTY — 만료 시 자가갱신 불가"))

        def _refresh_exp():
            # 만료일 필드가 **없는** 자격 포맷이 있다 — 컨테이너 claude 2.1.181 이 그렇다(호스트
            # 2.1.222 는 기록한다). 없는 키를 0 으로 읽으면 1970년이 되어 자격 상태와 무관하게
            # 매일 [x] 가 뜬다(2026-08-05 실측: 그날 08:30 자가갱신에 성공한 파일이 "만료됨"으로
            # 보고됨). 붉은 항목 하나가 상시 켜져 있으면 [x] 표식 자체가 신뢰를 잃으므로,
            # **모르는 것은 모른다고** 보고한다. 진짜 판정은 refresh token 보유(위) + 파일 갱신
            # 흔적(아래 age) + 라이브 호출(2-9) 세 신호가 함께 진다.
            exp = _load().get("refreshTokenExpiresAt")
            if not exp:
                age_h = (time.time() - creds.stat().st_mtime) / 3600
                return "warn", f"만료일 정보 없음 (자격 파일 {age_h:.1f}시간 전 갱신)"
            d = days_left(exp)
            if d <= 0:
                return "fail", "만료됨 — claude auth login 필요"
            return ("warn" if d < REFRESH_WARN_DAYS else "ok"), f"{d:.0f}일 남음"

        s.probe("refresh token 유효기간", _refresh_exp)

        def _access_exp():
            d = days_left(_load().get("expiresAt", 0))
            # access token 은 짧게 살고 자동 갱신된다 — 만료 자체는 정상이므로 경고까지만.
            return ("ok" if d > 0 else "warn"), (f"{d * 24:.1f}시간 남음" if d > 0 else "만료(자동 갱신 대상)")

        s.probe("access token 신선도", _access_exp, warn_only=True)

    # 라이브 검증 — 설정이 아니라 실제 호출이 통하는지. 컨테이너 lineage 로 확인한다.
    if CLAUDE_LIVE:
        def _live():
            # sh -c 를 쓴다. -lc(로그인 셸)는 /etc/profile 이 PATH 를 덮어써
            # 마운트된 claude(/home/node/.openclaw/bin)를 못 찾고 127 로 죽는다 — 인증 실패로 오진된다.
            rc, out = run(["docker", "exec", CONTAINER, "sh", "-c",
                           'claude -p "ping" --max-turns 1 >/dev/null 2>&1 && echo LIVE_OK || echo LIVE_FAIL'],
                          timeout=90)
            if rc != 0:
                return "fail", f"실행 불가: {out.strip()[:120]}"
            return ("LIVE_OK" in out), ("" if "LIVE_OK" in out else "호출 실패 — 토큰 만료·권한 의심")

        s.probe("Claude 라이브 호출 (실제 1턴)", _live)

    def _gog():
        rc, out = run(["gog", "auth", "list"])
        if rc != 0:
            return "fail", out.strip()[:140]
        return (GOG_ACCOUNT in out), (f"{GOG_ACCOUNT} 없음" if GOG_ACCOUNT not in out else "")

    s.probe(f"gog 계정 인증 ({GOG_ACCOUNT})", _gog)

    def _keyring():
        env = OPENCLAW_DOCKER / ".env"
        if not env.is_file():
            return "warn", f"{env} 없음"
        has = any(l.startswith("GOG_KEYRING_PASSWORD=") and l.split("=", 1)[1].strip()
                  for l in env.read_text(encoding="utf-8", errors="ignore").splitlines())
        return has, "" if has else "미설정 — 비대화식 gog 호출이 조용히 실패"

    s.probe("gog keyring 비밀번호 주입", _keyring)
    return s


# ── 점검 3. 자동 발화 (게이트웨이 cron) ─────────────────────────────────────────
def check_cron() -> Section:
    s = Section("cron", "자동 발화 (cron)")
    rc, out = run(["docker", "exec", CONTAINER, "openclaw", "cron", "list", "--all", "--json"], timeout=60)
    if rc != 0:
        s.add("fail", "cron 목록 조회", out.strip()[:160])
        return s

    try:
        data = json.loads(out[out.index("["):out.rindex("]") + 1]) if "[" in out else json.loads(out)
        jobs = data if isinstance(data, list) else data.get("jobs", [])
    except Exception as e:
        s.add("fail", "cron 목록 파싱", str(e)[:140])
        return s

    if not jobs:
        s.add("warn", "cron 잡 등록", "0건 — 자동 발화가 없음")
        return s

    now_ms = time.time() * 1000
    stuck = []
    for j in jobs:
        name = j.get("name", "(무명)")
        enabled = j.get("enabled", True)
        status = (j.get("lastRun") or {}).get("status") or j.get("status") or "unknown"
        if not enabled:
            s.add("warn", f"cron: {name}", "비활성(enabled=false)")
            continue
        if status == "ok":
            s.add("ok", f"cron: {name}", "")
        elif status in ("running", "unknown"):
            s.add("warn", f"cron: {name}", f"마지막 상태 {status}")
        else:
            s.add("fail", f"cron: {name}", f"마지막 상태 {status}")

        # Next 가 과거면 게이트웨이 비정상 종료로 run 이 running 에 박힌 것 — 틱이 영영 스킵된다.
        nxt = j.get("nextRunAt") or j.get("next") or 0
        if isinstance(nxt, str):
            try:
                nxt = datetime.fromisoformat(nxt.replace("Z", "+00:00")).timestamp() * 1000
            except Exception:
                nxt = 0
        if enabled and nxt and nxt < now_ms - 3600_000:
            stuck.append(name)

    s.add("fail" if stuck else "ok", "cron 스케줄 진행중 (stuck 아님)",
          f"다음 실행이 과거: {', '.join(stuck)} — disable→enable 토글로 복구" if stuck else "")
    return s


# ── 점검 4. 캡처 배선 ───────────────────────────────────────────────────────────
def check_wiring() -> Section:
    s = Section("wiring", "캡처 배선")

    rc, mounts = run(["docker", "inspect", CONTAINER, "--format",
                      "{{range .Mounts}}{{.Source}}:{{.Destination}}:{{if .RW}}rw{{else}}ro{{end}} {{end}}"])
    mounts = mounts.strip() if rc == 0 else ""

    def _inbox_mount():
        hit = [m for m in mounts.split() if m.endswith(":/inbox:rw")]
        if not hit:
            return False, "/inbox rw 마운트 없음 — 캡처가 vault 밖으로 샌다"
        src = hit[0].split(":")[0]
        return (Path(src).resolve() == INBOX.resolve()), f"{src}"

    s.probe("인박스 rw 마운트 (/inbox → vault)", _inbox_mount)

    def _router():
        rc2, out = run(["docker", "exec", CONTAINER, "printenv", "GMAIL_ROUTER_INBOX"])
        val = out.strip() if rc2 == 0 else ""
        return (val == "/inbox"), (val or "미설정 — run.py 가 workspace 로 폴백")

    s.probe("GMAIL_ROUTER_INBOX=/inbox", _router)

    s.probe("vault 읽기전용 마운트",
            lambda: (any(m.endswith(":/vault:ro") for m in mounts.split()), ""), warn_only=True)

    def _extra_env():
        # setup.sh 재실행은 extra.yml 을 volumes-only 로 재생성해 env 블록을 통째로 날린다.
        f = OPENCLAW_DOCKER / "docker-compose.extra.yml"
        if not f.is_file():
            return "warn", f"{f.name} 없음"
        txt = f.read_text(encoding="utf-8", errors="ignore")
        missing = [k for k in ("GMAIL_ROUTER_INBOX", "CLAUDE_CONFIG_DIR") if k not in txt]
        return (not missing), (f"env 키 소실: {', '.join(missing)} — setup.sh 재실행 흔적" if missing else "")

    s.probe("extra.yml env 블록 생존", _extra_env)
    return s


# ── 점검 5. 호스트 자동화 ───────────────────────────────────────────────────────
def check_hostauto() -> Section:
    s = Section("hostauto", "호스트 자동화")
    for unit in TIMERS:
        rc, out = run(["systemctl", "--user", "is-active", unit])
        state = out.strip()
        s.add("ok" if state in ("active", "waiting", "activating") else "fail",
              f"유닛 활성: {unit}", "" if rc == 0 else state)
    for unit in SERVICES:
        rc, out = run(["systemctl", "--user", "show", "-p", "Result", "--value", unit])
        res = out.strip() or "unknown"
        s.add("ok" if res == "success" else "fail", f"마지막 실행 결과: {unit}", "" if res == "success" else res)

    # ask-brain 은 요청-구동(path 유닛)이라 "유닛 활성"만으로는 살았는지 알 수 없다 — 워처가
    # 멀쩡히 대기 중이어도 답이 한 통도 안 나갈 수 있고, 실제로 2026-06-22~08-05 6주간
    # 발송 실패분이 조용히 유실됐다(로그에만 남고 아무도 안 봄). 그래서 **결과**를 본다.
    def _unsent():
        done = ASK_BRAIN_DONE
        if not done.is_dir():
            return "warn", f"{done} 없음"
        pend = sorted(done.glob("*.unsent"))
        if not pend:
            return "ok", ""
        newest = max(p.stat().st_mtime for p in pend)
        age_h = (time.time() - newest) / 3600
        return "fail", f"{len(pend)}건 미전송 (최근 {age_h:.1f}시간 전) — {done}/*.answer.md 에 답 보존됨"

    s.probe("ask-brain 회신 미전송", _unsent)
    return s


# ── 점검 6. 데이터·저장 ─────────────────────────────────────────────────────────
def check_data() -> Section:
    s = Section("data", "데이터·저장")

    def _backlog():
        if not INBOX.is_dir():
            return "fail", f"{INBOX} 없음"
        n = len([p for p in INBOX.iterdir() if not p.name.startswith(".")])
        return ("warn" if n > INBOX_WARN else "ok"), f"{n}건"

    s.probe("인박스 적체", _backlog)

    def _fresh():
        knowledge = VAULT / "knowledge"
        if not knowledge.is_dir():
            return "fail", "knowledge/ 없음"
        newest = max((p.stat().st_mtime for p in knowledge.rglob("*.md")), default=0)
        d = (time.time() - newest) / 86400
        return ("warn" if d > VAULT_STALE_DAYS else "ok"), f"최근 변경 {d:.1f}일 전"

    s.probe("vault 최근 변경", _fresh)

    def _disk():
        u = shutil.disk_usage(VAULT if VAULT.exists() else HOME)
        pct = u.free / u.total * 100
        return ("warn" if pct < DISK_WARN_PCT else "ok"), f"여유 {pct:.0f}% ({u.free // 2**30}GB)"

    s.probe("디스크 여유", _disk)
    return s


# ── 점검 7. 동기 ────────────────────────────────────────────────────────────────
def check_sync() -> Section:
    s = Section("sync", "동기")

    def _syncthing():
        # pgrep 패턴을 대괄호로 끊어 자기 자신을 잡지 않게 한다.
        rc, _ = run("pgrep -f '[s]yncthing' >/dev/null")
        return (rc == 0), "" if rc == 0 else "프로세스 없음 — 다중기기 동기 정지"

    s.probe("SyncThing 구동", _syncthing)
    return s


# ── 조립 ────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", help="결과 JSON 을 쓸 경로")
    ap.add_argument("--json", action="store_true", help="stdout 에 JSON 만 출력")
    args = ap.parse_args()

    sections = [
        check_gateway(),
        check_auth(),
        check_cron(),
        check_wiring(),
        check_hostauto(),
        check_data(),
        check_sync(),
    ]

    passed = sum(1 for s in sections for i in s.items if i["status"] == "ok")
    warned = sum(1 for s in sections for i in s.items if i["status"] == "warn")
    failed = sum(1 for s in sections for i in s.items if i["status"] == "fail")

    summary = {
        "host": platform.node(),
        "checkedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "ok": failed == 0 and warned == 0,
        "passed": passed,
        "warned": warned,
        "failed": failed,
        "sections": [{"key": s.key, "name": s.name, "items": s.items} for s in sections],
    }

    if args.summary:
        Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        # 콘솔은 사람용(개발자). 보고 문안은 health-report.py 가 따로 만든다.
        mark = {"ok": "[o]", "warn": "[!]", "fail": "[x]"}
        for s in sections:
            print(f"\n## {s.name}")
            for i in s.items:
                tail = f" — {i['detail']}" if i["detail"] else ""
                print(f"  {mark[i['status']]} {i['label']}{tail}")
        print(f"\n정상 {passed} · 경고 {warned} · 문제 {failed}")

    return 1 if failed else (2 if warned else 0)


if __name__ == "__main__":
    sys.exit(main())
