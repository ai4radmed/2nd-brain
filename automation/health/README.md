# brain-health — 2nd-brain 아침 헬스체크·텔레그램 보고

매일 아침 **2nd-brain 전체가 정상 작동하는지 자동 점검하고 텔레그램으로 한 통 보낸다.**
정상이어도 보낸다 — **"조용함 = 정상"이라는 착각을 원천 차단**하기 위해서다.

설계는 `radsafety-pwa` 의 아침 헬스체크(`documents/health_monitoring_guide.md`)와 같은 규약을 따른다.
그쪽이 이미 검증된 형식이고, 두 보고가 같은 문법이라 아침에 나란히 읽힌다.

---

## 왜 만들었나

`gmail-weekly-report` cron 이 **4일째 `error` 였는데 아무도 몰랐다.** 자동화가 조용히 죽으면
조용한 게 정상인지 죽은 건지 구별할 방법이 없다. 관측이 없는 자동화는 자동화가 아니다.

## 구조 — 세 부품 + 세 겹의 알림

| 부품 | 파일 | 역할 |
|---|---|---|
| 스케줄러 | `brain-health.timer` | 알람시계 — 매일 06:40 KST |
| 조립·순서 | `brain-health.sh` | 지휘자 — 진찰 → 보고 → 생존신호 |
| 진찰 | `health-check.py` | 점검만 하고 JSON 을 남긴다 (부작용 0) |
| 보고 | `health-report.py` | JSON → 사람이 읽을 문안 → 텔레그램 |

알림은 세 겹이고, **각 겹이 잡는 실패가 다르다**:

1. **텔레그램 아침 보고** — 게이트웨이·인증·cron·배선의 이상. 정상이어도 매일 한 통(하트비트).
2. **유닛 실패 배지** — 문제가 있으면 `brain-health.service` 도 exit 1 → `systemctl --user --failed` 에 흔적.
3. **dead man's switch** *(선택 · `HEALTH_PING_URL`)* — PC 종료·정전·WSL2 VM 종료로 **점검 자체가 못 돌 때**.
   1·2 는 스크립트가 돌아야 작동하므로 이 경우를 못 잡는다. 밖에 있는 서비스(healthchecks.io 등)가
   ping 두절을 대신 알려준다. 미설정이면 조용히 생략된다.

### 두 가지 설계 원칙

**① 감시자는 감시 대상 밖에 산다.**
이 스크립트는 **호스트**에서 돌며 OpenClaw 컨테이너를 들여다본다. OpenClaw 안에서 OpenClaw 를
감시하면 게이트웨이가 죽는 순간 보고도 같이 죽는다. 같은 이유로 텔레그램 발송도 게이트웨이를
경유하지 않고 봇 API 를 직접 친다.

**② 진찰 실패로 보고를 끊지 않는다.**
점검이 실패했다고 스크립트를 즉시 끝내면 *"이상 감지" 보고가 발송되지 못한다.* 그래서
실패를 일단 삼키고 → 보고를 먼저 보내고 → 마지막에 exit 로 표면화한다.

---

## 점검 항목 (29개 · 7영역)

| # | 영역 | 무엇을 보나 |
|---|---|---|
| 1 | 게이트웨이 | 컨테이너 실행·healthcheck · 이미지 버전 핀 · 클론↔이미지 dual-pin |
| 2 | 인증 | 자격 파일 · **refresh token 보유**·유효기간 · access 신선도 · **라이브 1턴 호출** · gog 계정 · keyring 비밀번호 |
| 3 | 자동 발화 | cron 잡별 마지막 상태 · **스케줄 stuck 여부** |
| 4 | 캡처 배선 | `/inbox` rw 마운트 · `GMAIL_ROUTER_INBOX` · vault ro · **extra.yml env 생존** |
| 5 | 호스트 자동화 | 타이머·path 유닛 활성 · 서비스 마지막 실행 결과 |
| 6 | 데이터·저장 | 인박스 적체 · vault 최근 변경 · 디스크 여유 |
| 7 | 동기 | SyncThing 구동 |

굵은 항목은 **실제로 겪은 사고**에서 나왔다:

- **refresh token 보유** — 자격에 refresh 가 없으면 만료 후 자가갱신이 불가능한데,
  `doctor`·`auth status` 는 통과한다. 어느 날 cron 만 401 로 죽는다.
- **라이브 1턴 호출** — `doctor`·`auth status` 는 **라이브 토큰 검증을 하지 않는다.**
  설정이 멀쩡한데 실제 호출은 실패하는 상태를 잡는 유일한 방법.
- **cron stuck** — 게이트웨이 비정상 종료로 run 이 `running` 에 박히면 틱이 영영 스킵된다.
  `enabled` 인데 안 도는 상태이고, `Next` 가 과거인 것이 유일한 단서다.
- **extra.yml env 생존** — `setup.sh` 재실행은 이 파일을 volumes-only 로 재생성해
  env 블록(PATH·CLAUDE_CONFIG_DIR·GMAIL·GOG)을 통째로 날린다. 2026-07 캡처 회귀의 원인.

## 보고 문안 규약

```
2nd-brain(kimbi) 모든 점검항목 정상 (29/29)
2026-08-04 06:40 KST

1. 텔레그램 게이트웨이
1-1. 게이트웨이 실행중 (…) [o]
...
3. 자동 실행 일정
3-12. 예약 실행: gmail-weekly-report — 마지막 상태 error [x]

문제 3-12
```

- **번호식** — 큰분류 `1.` `2.`, 세부 `1-1.` `1-2.` … 세부번호는 큰분류를 가로질러 이어서 증가한다.
  그래서 **마지막 항목 번호 = 전체 항목 수**이고, 머리줄 `(29/29)` 과 같은 축을 쓴다.
  **두 숫자가 어긋나면 그 자체가 버그 신호다.**
- **무이모지** — 상태는 줄 맨 끝에 `[o]`/`[!]`/`[x]`. 눈이 한 열만 훑으면 된다.
- **쉬운 말** — 기술 라벨은 점검 스크립트(콘솔용)에 그대로 두고, 번역은 보고 계층에서만 한다.
  사전에 없는 라벨은 **원문 그대로** 나간다 — 번역이 없다고 항목이 조용히 사라지면 안 된다.
- **명사형** — "…열림" 이지 "…열렸습니다" 가 아니다. 판정은 줄 끝 표식이 지므로,
  문장과 표식이 서로 반대말이 되는 사고를 막는다.
- 전부 정상일 때만 "모든 점검항목 정상" — **경고 1건도 그 말을 쓰지 않는다.**

---

## 설치

```bash
cd ~/projects/2nd-brain/automation/health
mkdir -p ~/.config/systemd/user
ln -sf "$PWD/brain-health.service" ~/.config/systemd/user/
ln -sf "$PWD/brain-health.timer"   ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now brain-health.timer
systemctl --user list-timers brain-health.timer     # NEXT 확인
```

머신별 설정(토큰·임계·유닛 목록)은 **git 미추적** 파일에 둔다 — 머신마다 다르다.

```bash
mkdir -p ~/.config/2nd-brain
cat > ~/.config/2nd-brain/health.env <<'EOF'
# 비우면 openclaw.json 의 봇 토큰을 재사용한다.
# HEALTH_TG_TOKEN=
# HEALTH_TG_CHAT=8669227844
HEALTH_REPORT=all
# 이 머신에서 켜져 있어야 할 유닛(공백 구분) — 머신마다 다르다.
# HEALTH_TIMERS="brain-drain.timer parser-drain.timer"
# dead man's switch — 설정하면 정상일 때만 ping. 미설정이면 생략.
# HEALTH_PING_URL=https://hc-ping.com/xxxxxxxx
EOF
chmod 600 ~/.config/2nd-brain/health.env
```

## 운영

```bash
# 지금 즉시 1회 (정시 실행과 완전히 동일한 경로 — 텔레그램도 동일하게 온다)
systemctl --user start brain-health.service

# 발송 없이 문안만 보기
python3 health-check.py --summary /tmp/h.json
OPENCLAW_JSON=/nonexistent HEALTH_TG_TOKEN= python3 health-report.py /tmp/h.json

# 콘솔 상세(개발자용)
python3 health-check.py

# 로그·마지막 결과
tail -50 ~/.local/state/brain-health.log
jq . ~/.local/state/brain-health.json
```

### 보고 on/off — 코드 변경 없이

`~/.config/2nd-brain/health.env` 의 한 줄만 고친다.

| 값 | 뜻 |
|---|---|
| `HEALTH_REPORT=all` | 기본 — 정상/이상 매일 보고 (하트비트) |
| `HEALTH_REPORT=fail` | 이상일 때만 보고 (정상은 침묵) |
| `HEALTH_REPORT=off` | 보고 끔 (점검·로그·유닛 배지는 유지) |

`HEALTH_REPORT_STYLE` 로 항목 표기도 바꾼다: `plain`(기본, 쉬운 말) · `both`(기술 원문+쉬운 말 2줄) · `tech`(기술 원문).

### 시각 변경

`brain-health.timer` 의 `OnCalendar` 한 줄. 시스템 TZ(Asia/Seoul) 기준이라 변환이 필요 없다.
`Persistent=true` 라 PC 가 꺼져 있어 건너뛴 아침은 **부팅 직후 한 번** 돈다 — kimbi 는 24/7 이 아니므로,
"어제 보고가 없었다"가 침묵이 아니라 정보가 되게 하는 장치다.

---

## 이 도구의 이름에 대해

**"OpenClaw 헬스체크"가 아니라 "2nd-brain 헬스체크"다.** OpenClaw 는 7개 영역 중 3개(게이트웨이·cron·배선)일 뿐이다.
OpenClaw 를 나중에 얇은 브리지로 교체하거나 은퇴시켜도, 그 영역만 갈아끼우면 나머지 점검은 그대로 산다.
홈서버로 옮겨갈 때도 머신 종속 값이 전부 env 로 빠져 있어 파일은 그대로 따라간다.

## 다중 기기

보고 머리줄에 **호스트명**이 박힌다(`2nd-brain(kimbi) …`). cron-status 시트를 열지 않아도
어느 PC 가 지금 일하고 있는지 매일 아침 확인된다.
발화 머신을 하나로 유지하는 규율 자체는 `/cron` 스킬이 권위다.

## 관련

- `radsafety-pwa/documents/health_monitoring_guide.md` — 원본 설계(개념 가이드)
- `automation/brain-drain/` · `automation/ask-brain/` — 같은 자리의 형제 유닛
- vault `02_areas/brain-system/automation-review-policy.md` — 자동 우선·주간 감사 정책
