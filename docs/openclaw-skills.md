# OpenClaw 스킬 — 무엇을 바로 쓰고, 어디까지 할 수 있나

[openclaw-docker-container.md](./openclaw-docker-container.md) 로 게이트웨이를 처음 띄우면, 별도 설치 없이도 일정 수의 **스킬(skill)** 이 이미 들어 있습니다. 이 문서는 **바로 쓸 수 있는 스킬(ready)** 부터 — 더 풀려면 무엇이 필요한지(needs-setup·Docker slim 한계), gog 로 할 수 있는 것·없는 것, cron 자동화·실용 활용까지 — 한곳에 정리합니다.

> 측정 환경: ghcr `openclaw/openclaw` (버전 2026.5.20). 스킬 구성·개수는 버전에 따라 달라질 수 있으니, 본인 환경에서는 아래 *확인 명령* 으로 직접 보세요.

## 스킬이란?

스킬은 AI 에이전트(여기선 봇)가 **외부 도구를 다루는 능력의 묶음**입니다. 스킬이 없어도 질의응답·요약·번역·글쓰기 같은 *순수 대화* 는 됩니다. 스킬은 거기에 "날씨 조회", "다이어그램 생성", "웹페이지 조작" 처럼 *바깥 세계를 건드리는* 구체적 기능을 더합니다.

## 설치된 스킬 확인하기

```bash
cd ~/projects/openclaw-docker
docker compose -f docker-compose.yml -f docker-compose.extra.yml run --rm openclaw-cli skills list
```

> native 와 **병행 설치**(포트 재지정)한 경우엔 위 명령이 `gateway closed` 로 끊깁니다. 그땐 게이트웨이 컨테이너 안에서 내부 포트로 실행하세요:
> ```bash
> GW=$(docker ps --filter name=openclaw-gateway --format '{{.Names}}' | head -1)
> docker exec -e OPENCLAW_GATEWAY_PORT=18789 "$GW" node dist/index.js skills list
> ```

출력 첫 줄에 `Skills (N/58 ready)` 처럼 나옵니다 — **58개가 번들되어 있지만, 그중 "ready" 만 바로 쓸 수 있고** 나머지는 외부 CLI·자격증명 설정이 필요한 "needs setup" 입니다.

## 최초 구동 시 바로 쓰는 스킬 (ready 14개)

순정 설치에서 "ready" 로 뜨는 스킬은 **14개** 입니다. 일반 사용자 관점으로 묶으면:

> ⚠️ **주의**: "ready" 는 *스킬 파일이 있다*는 뜻이지 *바로 작동한다*는 보장이 아닙니다. 외부 바이너리가 필요한 스킬(특히 **browser-automation**)은 slim Docker 에선 추가 설치가 필요합니다 — 아래 **"Docker slim 베이스의 한계"** 절 참조.

### A. 일상·업무 (일반 사용자에게 가장 유용)

| 스킬 | 무엇을 할 수 있나 | 비고 |
|---|---|---|
| ☔ **weather** | 위치별 현재 날씨·예보, 여행 계획 (예: "내일 서울 비 와?") | 설정 불필요 |
| 🧭 **diagram-maker** | 개념·아키텍처·플로우 다이어그램(SVG/HTML/Excalidraw) 생성 | 설정 불필요 |
| 🖼️ **meme-maker** | 밈 템플릿 검색 + 이미지 밈 생성 | 설정 불필요 |
| 🌐 **browser-automation** | 웹페이지 다단계 제어(로그인 확인·탭 관리·폼 입력) — 가장 강력 | ⚠️ **Docker 는 Chromium 추가 설치 필요** (아래 "Docker slim 베이스의 한계" 절) |
| 📝 **notion** | Notion 페이지·데이터베이스·코멘트·검색 관리 | 실제 연동엔 Notion 통합 토큰 필요할 수 있음 |
| 🖼️ **canvas** | 연결된 OpenClaw 노드(폰·맥) 화면에 HTML 표시 | 노드 앱 페어링 필요 |

### B. 작업 자동화 (파워 유저)

| 스킬 | 무엇을 |
|---|---|
| 🪝 **taskflow** | 다단계·비동기 작업을 하나의 durable 작업으로 조율 (대기·하위작업·상태 관리) |
| 📥 **taskflow-inbox-triage** | 위 taskflow 의 인박스 분류·라우팅 예제 패턴 |

### C. 개발자·관리자용 (일반 사용자에겐 덜 관련)

| 스킬 | 용도 |
|---|---|
| **skill-creator** | 스킬(SKILL.md) 생성·편집·검증 |
| **spike** | 일회성 프로토타입으로 실현 가능성 검증·비교 |
| **node-inspect-debugger** | Node.js 디버깅 |
| **python-debugpy** | Python 디버깅 |
| **healthcheck** | 호스트 보안 점검(SSH·방화벽·업데이트·백업) |
| **node-connect** | OpenClaw 노드(Android/iOS/macOS) 페어링 진단 |

### D. 스킬 없이 되는 기본 능력

질의응답 · 요약 · 번역 · 브레인스토밍 · 글쓰기 등은 스킬과 무관하게 기본으로 됩니다.

## 더 풀려면 — "needs setup" 44개

나머지 44개는 외부 도구·자격증명을 붙이면 켜집니다. 일반 사용자가 자주 원하는 것 예:

- **이메일** (himalaya), **GitHub** (gh-issues), **Discord**, **Apple Notes/Reminders**, **1Password**, **Gemini CLI**, **coding-agent**(Codex·Claude Code 위임) 등.

이들은 사용자마다 계정·CLI 설치가 달라 *순정 데모 범위를 넘습니다*. 필요한 것만 골라 개별 설정하세요 (`skills list` 가 각 스킬의 setup 안내를 가리킵니다).

## Docker slim 베이스의 한계 — 외부 도구가 필요한 스킬 붙이기

> ⚠️ **중요**: `skills list` 의 "ready" 는 *스킬 파일이 있다*는 뜻이지 *런타임이 갖춰졌다*는 뜻이 **아닙니다.** 외부 바이너리(브라우저·gog 등)가 필요한 스킬은 **slim Docker 이미지에선 바로 작동하지 않습니다.**

### 왜 이미지가 slim 인가
- **macOS 베이스 불가**: 컨테이너는 호스트 리눅스 커널을 공유 → macOS 컨테이너 베이스는 존재하지 않음. macOS 전용 스킬(apple-notes 등)은 *연결된 macOS 노드*에서 돕니다.
- **크기·보안·per-user 인증**: 58개 deps 를 다 박으면 수 GB + 공격면 증가 + 어차피 자격증명은 사용자마다 다름 → **의도적으로 slim + 온디맨드 설치**.
- 스킬 install 메타데이터는 보통 **brew(native 호스트) 전제** → brew 없는 slim Debian 컨테이너에선 설치가 실패합니다.

### 두 가지 케이스 (실측)

**① browser-automation — 시스템 라이브러리 필요 → 커스텀 이미지**
- 이미지에 Chromium 본체·시스템 libs(`libglib` 등)가 없음. `skills list` 엔 ready 로 떠도 봇은 "browser tool not activated".
- Chromium 바이너리는 마운트 경로에 설치해 영속 가능하나, **시스템 libs 는 `apt`(root)로 깔아야 하고 이미지 layer 라 recreate 시 사라짐** → 진짜 영속은 **커스텀 이미지**(`FROM` 베이스 + `install-deps`)뿐.

**② gog (Gmail·Calendar·Tasks) — 정적 바이너리 → 복사로 해결**
- gog 스킬은 번들돼 있고 `requires.bins: ["gog"]` 로 gog 바이너리를 요구. **대시보드 활성화는 brew 설치를 시도하나 컨테이너에 brew 없어 실패** → 켜지지만 작동 안 함.
- 단 gog 는 **정적 단일 바이너리**라 시스템 libs 불필요 → 호스트 바이너리를 마운트 경로에 복사 + PATH 추가 → **영속·간단**(browser 와 결정적 차이).
- 인증은 별도: `~/.config/gogcli-*` 마운트 + **Google OAuth(GCP 프로젝트·클라이언트) 설정** — 이건 native 든 Docker 든 동일한 *Google 연동의 본질적 관문*이지 Docker 탓이 아닙니다.

> 📋 **단계별 설치 절차(검증 게이트 포함)**: [openclaw-docker-gog.md](./openclaw-docker-gog.md) 의 **STEP 1~6** 참조 — 바이너리 복사·config 마운트·keyring env·실 API 검증, 그리고 봇이 "이메일 도구 없음" 으로 막히는 **계정 불일치 함정 회피(STEP 5)** 까지.

### 일반 규칙

| 스킬 런타임 유형 | slim Docker 영속 방법 |
|---|---|
| 이미 번들 / npm / **정적 바이너리** (예: gog) | 마운트 경로에 복사 or 이미 있음 → 쉬움 |
| **시스템 라이브러리·OS 패키지** 필요 (예: 브라우저) | **커스텀 이미지에 bake** (`install-deps`) |
| 자격증명·토큰 (OAuth 등) | 마운트된 config 에 저장 → 영속 |

> 핵심: **"skill ready ≠ Docker 에서 작동".** 정적 바이너리는 복사로, 시스템 의존성은 커스텀 이미지로. 공식 문서는 이 통합 절차를 (gog=gogcli.sh / Docker baking=install/docker.md / 스킬 메타=tools/skills.md 로) **흩어놓아서**, 이 강의록이 그 빈틈을 메웁니다.

## gog 로 할 수 있는 것 (설치·인증 후)

> 능력의 권위 출처: ① 봇이 읽는 **`SKILL.md`**(`/app/skills/gog/SKILL.md`) · ② **`gog --help`** / `gog <서비스> --help`(명령 트리) · ③ **`gog auth list`**(인증 scope = 실제 천장) · ④ <https://gogcli.sh>(공식 docs)

**인증 scope(천장, 개인 계정 기준)**: `gmail · calendar · drive · docs · sheets · slides · contacts(people) · classroom · tasks · chat · forms · groups`

| 서비스 | 봇이 자연어로 시킬 수 있는 것 | gog 명령 예 |
|---|---|---|
| 📧 **Gmail** | 검색·읽기·발송·초안·답장 | `gog gmail search 'newer_than:7d'` · `gog gmail send --to … --subject … --body …` · `gog gmail drafts create …` |
| 📅 **Calendar** | 일정 조회·생성·수정·색상 | `gog calendar events <cal> --from <iso> --to <iso>` · `gog calendar create …` |
| ✅ **Tasks(할일)** | 할일 조회·관리 | `gog tasks --help` |
| 📁 **Drive** | 검색·목록·다운로드·업로드 | `gog drive search "…"` · `gog drive upload <path>` |
| 📄 **Docs** | 본문 출력·export | `gog docs cat <id>` · `gog docs export <id> --format txt` |
| 📊 **Sheets** | 셀 읽기·쓰기·추가·삭제 | `gog sheets get <id> "Tab!A1:D10"` · `gog sheets append …` |
| 👤 **Contacts** | 연락처 목록·내 프로필 | `gog contacts list` · `gog me` |
| 🖼️ Slides · 🎓 Classroom · 👥 Groups | 명령 트리 존재 | `gog slides/classroom/groups --help` |

> 강의 한 줄: **gog 로 봇은 "메일·일정·할일·드라이브·문서·시트" 를 자연어로 다룬다** — 일반 사용자가 가장 원하는 *정리* 작업을 정확히 커버. 단 Docker 설치는 위 STEP 절차 필요(특히 **계정 신원 일치**).

## gog 단독 vs 시스템 커스텀 스킬 — 무엇이 안 되나

> 한 줄: **구글 *안* 에서 끝나는 작업은 gog 단독으로 됨. 구글 *밖* 2nd-brain 으로 끌어와 정리(브레인화)는 안 됨.**

| 작업 | gog 단독 | 근거 |
|---|---|---|
| 일정 등록 | ✅ 완전 | `gog calendar create` — 구글 쪽에서 끝남 |
| 할일 등록 | ✅ 완전 | `gog tasks add` |
| 회신·초안 작성 | ✅ 완전 | `gog gmail send --reply-to-message-id` / `gmail drafts create` |
| 라벨별 첨부파일 *다운로드* | ✅ 됨 | `gmail messages search "label:X"` → `gmail get` → `gmail attachment` |
| 라벨별 첨부파일 → **2nd-brain 정리 저장** | ❌ | 아래 3가지 부재 |

**gog 단독으로 ❌ 인 것 (= 시스템 커스텀 스킬이 메우던 영역):**

1. **vault 접근** — 컨테이너에 `~/projects/2nd-brain-vault` 가 **마운트 안 됨** → 다운로드해도 PARA 구조에 못 넣음 (컨테이너 workspace 에 떨굴 뿐).
2. **브레인화 규약** — 파일명 규칙·knowledge/sources 분리·**동반 노트**(frontmatter+요약)·wikilink. (커스텀 `brainify-inbox` 스킬)
3. **분류·트리아지 정책** — 라벨→액션 매핑(8-라벨 모델)·4분류·dedup·멱등성·검증된 JSON 파싱. (커스텀 `gws-assistant` 등)

> **gog = 동사(Google API 능력) · 커스텀 스킬 = 문장(워크플로우·정책) + 2nd-brain 통합.**
> 컨테이너에서 브레인화까지 하려면 ① vault 마운트 + ② 커스텀 스킬 이식이 추가로 필요합니다.

## 실습 — 스킬 없이 gog + cron 으로 라벨 자동화

> 교육 포인트: **새 스킬을 만들지 않고**, 이미 깔린 gog 스킬 + 내장 cron + *프롬프트 한 덩어리* 만으로 반복 자동화가 된다.

**시나리오**: Gmail 라벨별 처리 후 `완료` 로 이동 — `첨부저장`→첨부 다운로드, `일정등록`→캘린더 등록, `할일등록`→할일 등록.

**사전 준비**: Gmail 에 라벨 `데모1 첨부저장`·`데모2 일정등록`·`데모3 할일등록`·`데모4 완료` 생성 (없으면 봇에게 "gog 로 만들어줘"). 번호 접두로 정렬·구분이 쉽다.

### ① 작업 프롬프트 (텔레그램에 붙여넣기 — **라벨 1개씩**)

> 💡 **라벨별로 따로 실행**합니다. 3개를 한 프롬프트에 묶으면 다단계 작업이 길어져 **180s no-output watchdog** 에 걸려 죽습니다(저자 실측). 라벨당 1개 + *각 메일 처리 시 한 줄 보고* 로 쪼개면 빠르고, 출력이 흘러 watchdog 타이머도 리셋됩니다. (처음 한 번씩 수동 실행해 검증 후 cron 등록)

**[1] 첨부 저장**
```
gog 로 라벨 "데모1 첨부저장" 메일을 처리해줘. 계정 기본값.
각 메일 첨부를 ~/.openclaw/workspace/attachments/ 에 다운로드하고,
성공한 메일만 "데모1 첨부저장" 제거 + "데모4 완료" 추가.
각 메일 처리할 때마다 한 줄씩 보고하고, 끝에 "처리 N / 실패 M" 요약.
```
**[2] 일정 등록**
```
gog 로 라벨 "데모2 일정등록" 메일을 처리해줘. 계정 기본값.
각 메일 내용에서 제목·날짜·시간을 추출해 기본 캘린더에 일정 등록(gog calendar create),
성공한 메일만 "데모2 일정등록" 제거 + "데모4 완료" 추가.
각 메일 처리할 때마다 한 줄씩 보고하고, 끝에 "처리 N / 실패 M" 요약.
```
**[3] 할일 등록**
```
gog 로 라벨 "데모3 할일등록" 메일을 처리해줘. 계정 기본값.
각 메일 제목을 할일로 등록(gog tasks add),
성공한 메일만 "데모3 할일등록" 제거 + "데모4 완료" 추가.
각 메일 처리할 때마다 한 줄씩 보고하고, 끝에 "처리 N / 실패 M" 요약.
```
> 공통 규칙: **성공한 메일만** 라벨 이동, 실패는 라벨 유지 + 사유 보고.
> 라벨명에 공백이 있어 검색은 `label:"데모1 첨부저장"`(따옴표) 또는 `label:데모1-첨부저장`(공백→하이픈) — 봇이 보통 알아서 조정.

### ② cron 등록 (텔레그램 한 줄)
```
방금 그 라벨 처리 작업을 매일 아침 8시에 자동 실행하도록 cron 에 등록해줘.
```
→ 내장 cron 에 "정해진 시각 + 이 프롬프트" 가 예약되어, 시간마다 자동 처리.

### ★ 이 과정에 새 스킬은 만들어지지 않는다
| 쓰이는 것 | 정체 |
|---|---|
| gog 스킬 | 이미 설치된 *번들* (새로 안 만듦) |
| cron 항목 | 내장 cron 의 *예약 데이터* — "언제 + 어떤 프롬프트" 만 저장. SKILL.md·코드 없음 |
| 프롬프트 | 위 텍스트 = *정책*. cron 메시지에 저장돼 매 실행 LLM 이 해석 |

- `workspace/skills/` 에 **새 파일이 안 생긴다** = "스킬" 이 아니라 "예약된 지시문(데이터)".
- cron 메시지가 슬래시커맨드(`/skill명`)가 아닌 **평범한 자연어** 라, 컨테이너의 cron→스킬확장 경로도 안 탄다.
- 정리: **능력(gog) + 스케줄러(cron) + 지시문(프롬프트)** = "스킬 제작" 이 아니라 "기존 능력의 예약 사용".

### 한계 (솔직)
- 첨부는 **컨테이너 workspace** 에 저장 (vault 아님 — 브레인화 저장은 별도, 위 비교 표).
- 무인 반복 신뢰성은 프롬프트 품질·완료조건 명확성에 의존 → 안정 운영엔 결정형 래퍼 권장.
- **자연 멱등**: 처리한 메일은 트리거 라벨이 제거돼 다음 실행 검색에 안 잡힘.

### 결정형 래퍼 예제 — `gmail-label-router`

위 프롬프트-only 방식의 신뢰성 한계를 넘으려면 *절차를 코드로 박은* 커스텀 스킬을 쓴다. 그 실제 예제가 [`templates/skills/gmail-label-router/`](../templates/skills/gmail-label-router/) 에 있다 — `[1] 첨부 저장` 프롬프트를 **LLM 판단 0 의 Python 래퍼**로 옮긴 버전이다(빠르고 watchdog 종료·고아 위험 없음). 적용은 라벨·계정(env)·저장경로 3곳만 본인 환경에 맞게 고친 뒤 `~/.openclaw/workspace/skills/` 로 복사. 설치·적응법은 그 폴더의 [README](../templates/skills/gmail-label-router/README.md).

## 데모로 보여주기 좋은 것

설정이 전혀 필요 없는 네 가지가 시연에 적합합니다:

- **weather** — 즉답으로 "살아있는 봇" 임을 보여줌 ("내일 부산 날씨")
- **diagram-maker** — 눈에 보이는 산출물 ("이 흐름 플로우차트로 그려줘")
- **meme-maker** — 가벼운 재미 요소
- **browser-automation** — "웹을 직접 만진다" 는 강력함 시연

## 실습 — diagram-maker 로 플로우차트 만들기 (요청 → 결과 받기)

### 1) 좋은 요청법 — 5가지 레버

스킬 내부 규칙(짧은 라벨·요소 5~9개·의미색·분기 다이아몬드)을 요청에 미리 박으면 결과 품질이 확 올라갑니다:

1. **포맷**: "깔끔한 SVG/HTML" (정밀·standalone) 또는 "Excalidraw 손그림" (편집용)
2. **방향**: 위→아래 / 좌→우 / 역할별 swimlane
3. **단계 나열 + 연결**, 분기는 "예/아니오"로
4. **요소 5~9개**로 제한 (빽빽하면 지저분)
5. **의미색**: 시작/처리/판단/저장/종료 구분 (무지개색 금지)

복붙 예시:

```
아래 절차를 깔끔한 SVG/HTML 플로우차트로 그려줘.
- 방향: 위에서 아래로
- 단계: ① 자료 유입 → ② 중복 검사 → ③ (판단)이미 있나? 예→기존 노트 링크 / 아니오→④ PARA 분류 → ⑤ 동반 노트 작성 → ⑥ 저장
- 판단(③)은 다이아몬드, 예/아니오 분기 표시
- 색은 시작/처리/판단/저장을 의미별로 구분, 무지개색 금지
- 제목 "브레인화 흐름"
- 완성본을 PNG 이미지로도 보내줘
```

### 2) 결과물 받는 법

봇은 보통 `…workspace/brain_flow.html 에 저장했습니다` 처럼 **컨테이너 경로**를 알려줍니다. 하지만:

- **컨테이너에 들어갈 필요 없습니다.** 워크스페이스(`/home/node/.openclaw/workspace/`)는 호스트 `~/.openclaw-docker/workspace/` 로 **마운트**돼 있어, 같은 파일이 호스트에 그대로 있습니다 — 봇이 만드는 모든 파일이 여기 나타납니다.
- WSL2 에서 Windows 기본 브라우저로 바로 열기:
  ```bash
  powershell.exe -NoProfile -Command "Start-Process '$(wslpath -w ~/.openclaw-docker/workspace/brain_flow.html)'"
  ```
  (`cmd.exe /c start` 는 작업 디렉토리가 WSL(UNC)이면 경고 → PowerShell `Start-Process` 권장.)
- **텔레그램에서 이미지로 바로** 보려면 요청에 *"PNG 이미지로도 보내줘"* 추가 (위 예시 마지막 줄) → 봇이 내장 브라우저로 캡처해 그림으로 전송.
- `.excalidraw` 파일은 받아서 [excalidraw.com](https://excalidraw.com) 에 끌어놓으면 편집·출력.

> 컨테이너 경로(`/home/node/.openclaw/workspace/…`) 와 호스트 경로(`~/.openclaw-docker/workspace/…`) 는 **같은 파일의 두 이름**입니다.

## 실용 활용 아이디어 3가지 (기본 스킬만으로)

needs-setup 스킬 없이, 텔레그램으로 바로 되는 활용입니다.

> ⚠️ 아래 1~3 은 모두 **browser-automation** 을 씁니다 — **slim Docker** 라면 먼저 브라우저를 활성화해야 합니다(위 "Docker slim 베이스의 한계" 절). native 설치는 바로 됩니다.

### 1. 웹 리서치 → 정리 → 다이어그램 (설정 0)
**스킬**: browser-automation + 기본 LLM + diagram-maker. 봇이 웹을 직접 읽어 핵심을 정제하고 플로우차트/표로 시각화.
```
전자여권 재발급 절차를 웹에서 조사해서, 핵심만 6단계 이내로 정리하고
위→아래 SVG 플로우차트로 그려줘. 완성본 PNG 도 보내줘.
```

### 2. 주말 나들이·여행 브리핑 (설정 0)
**스킬**: weather + browser-automation + 기본 LLM. 날씨 + 장소·맛집 수집 + 시간대별 일정.
```
이번 토요일 강릉 당일치기. 날씨 확인하고, 가볼 만한 곳·맛집 웹에서 찾아서
오전·점심·오후·저녁 시간대별 일정표로 짜줘.
```

### 3. 반복 점검 자동화 (정기 모니터링)
**스킬**: taskflow + browser-automation. 가격·예약 슬롯·등록 오픈·공지 변동을 점검 → 변화 시 알림.
```
이 페이지(URL)의 등록 오픈 여부를 확인해서, '오픈'으로 바뀌면 텔레그램으로 알려줘.
```
> 한 번 점검은 설정 0. **정기 반복**만 cron(스케줄) 한 줄이 필요 (heartbeat 를 껐다면 cron 으로 대체).

| 아이디어 | 핵심 스킬 | 추가 설정 |
|---|---|---|
| 1. 웹 리서치→다이어그램 | browser-automation + diagram-maker | 없음 |
| 2. 여행 브리핑 | weather + browser-automation | 없음 |
| 3. 정기 모니터링 | taskflow + browser-automation | 정기 실행 시 cron |

## 응답 속도 최적화 (실측 기반)

봇이 느리면 대부분 **세팅 문제**입니다. 단순 gog 작업(메일 3건 제목)으로 실측:

| 설정 | warm 응답 | 비고 |
|---|---|---|
| sonnet-4-6 (기본) | 18~34초 | thinking 무거움 |
| **haiku-4-5** | **6.5초** | **3~5배 빠름** |
| 다단계를 한 턴에 몰빵 | ❌ ~180초 후 죽음 | no-output watchdog |
| 백그라운드 위임 | ❌ 고아·무응답 | 워커가 결과를 안 돌려줌 |

> 전처리·OAuth 부트스트랩은 **warm 에서 ~0.5초로 무시 가능**. 콜드(재시작 직후 첫 메시지)만 +8초 — 일회성.

### 어떻게 빠르게 하나 — 설치 체크리스트로

구체적 설정·결정은 **설치 시 1회 결정** 사항이라, [openclaw-docker-container.md](./openclaw-docker-container.md) 의 **"초기 설정 시 반드시 검토 (모델·watchdog·하트비트·thinking)"** 에 체크리스트로 정리돼 있습니다. 핵심만:

- **① 작업에 맞는 모델** — 기계적 작업 = `haiku-4-5` (가장 큰 레버), 추론 필요 = `sonnet`.
- **② watchdog ↔ 다단계 작업** — 한 턴에 몰빵 금지 → 단계별 분리 + **"각 처리마다 한 줄 회신"**(타이머 리셋). 위 **"실습 — gog + cron 라벨 자동화"** 절 참조.
- **③ 위임 금지** — 프롬프트에 *"백그라운드·하위 에이전트로 위임하지 말고 직접 실행"*.
- **④ 하트비트 off** / thinking 은 모델 선택으로 대체 (⚠️ `agents.defaults.thinking` 직접 설정은 crash).

### 구조적 하한 (못 줄이는 부분)
자연어 매개라 매 턴 "읽고→생각하고→툴 호출→결과 읽고→응답" LLM 루프를 돕니다 → 직접 `gog`(2초)보다 **항상 느림**(최적화해도 단순 작업 **~5~10초**). **즉답**이 필요하면 직접 gog/Claude Code, **폰·비동기·cron·푸시**가 가치면 봇.

> 느림의 *구조적 원인*(매 턴 시스템프롬프트 23.5KB + 스킬 + MCP + 이력 누적)은 [openclaw-docker-container.md](./openclaw-docker-container.md) 의 "왜 느린가" 부록 참조.

## 정리

- 순정 OpenClaw = 스킬 58개 번들, **즉시 사용 14개** + 기본 대화.
- 일반 사용자 체감 가치는 **A(일상·업무 6개) + D(기본 대화)**, 나머지는 개발/관리자용이거나 설정이 필요.
- 더 많은 일상 기능(이메일·캘린더·GitHub)은 "needs setup" 을 개별 해제.

> 다음: 스킬 추가·제작은 [openclaw-docker-container.md](./openclaw-docker-container.md) 의 운영 흐름과 OpenClaw 공식 문서 <https://docs.openclaw.ai> 를 참고하세요.
