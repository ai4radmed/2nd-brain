# gmail-label-router — 결정형 Gmail 라벨 라우터 (예제 스킬)

OpenClaw 용 **커스텀 스킬 예제**. Gmail 라벨이 붙은 메일을 *LLM 판단 없이* 정해진 동작으로 처리한다. 여기서는 한 가지 라우트만 담았다:

> 라벨 **`1 저장`** 메일의 **스레드(본문+첨부) 전체**를 저장 디렉토리에 캡처한 뒤(스레드별 폴더: `_thread.md` 본문 + 첨부 원본), 성공한 메일만 라벨을 **`9 완료`** 로 교체.

## 왜 "결정형 래퍼" 인가

봇에게 *프롬프트로* "라벨 메일 처리해줘" 를 시키면 매 실행 LLM 이 단계를 추론한다 — 느리고, 첫 토큰이 늦으면 **no-output watchdog** 에 걸려 turn 이 죽거나 고아(미아) run 이 된다. 이 스킬은 그 절차를 **고정 코드**로 박아 LLM 을 핫패스에서 제거한다:

- **판단 0** → 빠르고 watchdog 종료·고아 위험 없음.
- **fail-safe** → 캡처가 성공한 메일만 라벨을 교체(실패 시 라벨 유지 → 유실 방지).
- **멱등성** → 같은 스레드(threadId)가 같은 message_count 로 다시 와도 재캡처하지 않음(중복 0). 라벨 교체 실패로 재실행돼도 안전.
- **thread 단위 + 건별 한 줄 출력** → 출력이 흘러 watchdog 타이머가 리셋됨.

배경 설명: [`docs/openclaw-skills.md`](../../../../docs/openclaw-skills.md) 의 "실습 — 라벨 자동화" 절. 이 스킬은 거기서 보여주는 *프롬프트-only 자동화* 의 **결정형 래퍼 버전**이다.

## 전제

- **OpenClaw 게이트웨이** 가동 중 ([`docs/openclaw-docker-container.md`](../../../../docs/openclaw-docker-container.md)).
- **gog CLI** 설치 + 본인 Gmail 계정 인증 완료 ([`docs/openclaw-docker-gog.md`](../../../../docs/openclaw-docker-gog.md)).
- Python 3.

## 적용 (2곳만 본인 환경에 맞게)

1. **계정** — 환경변수 `GMAIL_ROUTER_ACCOUNT` 에 본인 Gmail 계정 (코드에 기본값 없음 — 누출 방지). *어디에 넣는지는 아래 [계정·env 설정 위치](#계정env-설정-위치--봇으로-쓸-때-핵심).*
2. **저장 위치** — 환경변수 `GMAIL_ROUTER_INBOX` (기본 `~/.openclaw/workspace/attachments`).

> **라벨은 고정 규칙입니다 (코드 수정 대상 아님).** 이 스킬은 트리거 `1 저장` → 완료 `9 완료` 를 쓴다 — Gmail 에 **이 두 라벨을 그대로 만들어** 사용하세요(없으면 봇에게 "gog 로 라벨 만들어줘"). 라벨명에 공백이 있어 검색 쿼리는 `label:"1 저장"` 형태를 쓴다.

## 설치 (워크스페이스에 복사)

OpenClaw 는 `~/.openclaw/workspace/skills/<이름>/` 에서 스킬을 로드한다. 이 폴더를 그대로 복사:

```bash
cp -r templates/skills/openclaw/gmail-label-router ~/.openclaw/workspace/skills/
```

> Docker 컨테이너로 운영 중이면, 워크스페이스가 마운트된 호스트 경로(예: `~/.openclaw-docker/workspace/skills/`)에 복사한다. 복사 후 게이트웨이가 스킬을 다시 스캔하도록 `skills list` 로 확인.

## 계정·env 설정 위치 (★ 봇으로 쓸 때 핵심)

env 를 **어디에 넣느냐는 실행 방식에 따라 다릅니다.**

### Docker 컨테이너 + 봇 (실사용)

봇이 부르면 `run.py` 는 **게이트웨이 컨테이너 안**에서 실행되므로, 계정은 *컨테이너의 환경변수*로 들어가야 한다. 이 repo 가 아니라 컨테이너 쪽 두 파일에 (기존 `GOG_KEYRING_PASSWORD` 과 똑같은 방식):

1. `~/projects/openclaw-docker/.env` (repo 밖·비공개) 에 값:
   ```
   GMAIL_ROUTER_ACCOUNT=you@gmail.com
   ```
2. `~/projects/openclaw-docker/docker-compose.extra.yml` 의 `openclaw-gateway`·`openclaw-cli` 두 `environment:` 블록에 참조:
   ```yaml
         - GMAIL_ROUTER_ACCOUNT=${GMAIL_ROUTER_ACCOUNT}
   ```
3. 재생성 + 확인:
   ```bash
   cd ~/projects/openclaw-docker
   docker compose -f docker-compose.yml -f docker-compose.extra.yml up -d --force-recreate openclaw-gateway
   GW=$(docker ps --filter name=openclaw-gateway --format '{{.Names}}' | head -1)
   docker exec "$GW" printenv GMAIL_ROUTER_ACCOUNT   # 계정이 나오면 OK
   ```

> ⚠️ **2nd-brain repo 안에는 계정을 넣지 마세요** — 공개 repo 라 commit 시 누출됩니다. 계정은 컨테이너 `.env`(repo 밖)에만.
> ⚠️ 이 계정은 **gog 인증 계정과 일치**해야 합니다 ([gog 설치](../../../../docs/openclaw-docker-gog.md)). 다르면 `OAuth client credentials missing` 류로 실패합니다.

### 수동 CLI 테스트 (네이티브 또는 컨테이너 안)

스킬 동작만 빠르게 확인할 땐 인라인 env 로 — 아래 "실행·검증".

## 실행·검증 (수동 테스트)

> 아래 인라인 명령은 **수동 확인용**이다. Docker 라면 호스트가 아니라 컨테이너 안에서 돌린다: env 는 위에서 이미 컨테이너에 주입됐으므로 인라인 없이 `docker exec "$GW" python3 /home/node/.openclaw/workspace/skills/gmail-label-router/run.py --dry-run`.

먼저 **건수만** 확인(저장·라벨변경 없음):

```bash
GMAIL_ROUTER_ACCOUNT=you@gmail.com python3 ~/.openclaw/workspace/skills/gmail-label-router/run.py --dry-run
```

실제 처리:

```bash
GMAIL_ROUTER_ACCOUNT=you@gmail.com python3 ~/.openclaw/workspace/skills/gmail-label-router/run.py
```

**봇(텔레그램 등) 실사용**: 위 "계정·env 설정 위치"로 컨테이너에 env 를 넣었으면, SKILL.md 의 자연어 트리거("1 저장 처리해줘" / "먼저 몇 건인지 봐줘")로 부르면 된다 — 인라인 env 불필요.

## 알려진 한계

- **멱등성 (threadId + message_count)**: 라벨 교체가 실패해 같은 스레드가 다음 실행에 다시 잡혀도, 메시지 수가 같으면 재캡처하지 않고 **라벨만 정리**한다(중복 0). 메시지 수가 늘면(새 답장) 기존 폴더를 **덮어써 갱신**한다(폴더명은 첫 캡처 날짜 스탬프 유지). 키는 `_thread.md` 프론트매터의 `gmail_thread_id`·`message_count`. *vault 전체* 중복(이미 brainify된 스레드 재유입)은 brainify 단계의 노트 프론트매터 dedup이 담당(별도).
- 라우트가 **1개**다. 같은 동사(스레드 캡처)로 라벨만 늘리려면 라우트 상수를 늘리고, *다른 동사*(일정 등록·할일 등록 등)가 필요하면 `process_thread` 패턴을 본떠 핸들러를 추가한다.

## 파일

| 파일 | 역할 |
|---|---|
| `run.py` | 모든 로직 (결정형 처리). gog 호출은 `gog_json`(조회)·`gog_call`(변경) 두 래퍼로 수렴. |
| `SKILL.md` | OpenClaw 스킬 매니페스트 — 자연어 트리거 + 실행 모드(`run.py` / `--dry-run`). |
| `README.md` | 이 문서. |
