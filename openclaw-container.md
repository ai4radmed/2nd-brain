# OpenClaw 게이트웨이 — Docker 컨테이너 설치

[OpenClaw 공식 Docker 설치 문서](https://docs.openclaw.ai/ko/install/docker) 를 참고하여 저자가 설치한 방법을 정리하였습니다.

## 왜 도커 설치방법을 선택했는가?

- **native 설치에 비해 보안면에서 더 안전** — native 설치 시 OpenClaw 는 호스트 user 권한 그대로 작동해 같은 사용자의 모든 fs·credential·프로세스에 접근 가능합니다. 해킹으로 시스템이 탈취되었다고 가정하면 피해가 크지만, 컨테이너로 띄우면 피해가 컨테이너 boundary로 제한됩니다.


## 전제

- **WSL2** - 저자는 Windows 보다 WSL2 를 선호하므로 이하 **WSL2 환경에서 진행** 하였습니다.
- **Docker Engine + Docker Compose v2** - 컨테이너로 오픈클로를 설치하기 위해 필요합니다. 미설치 시 [Docker Engine 설치 가이드](https://docs.docker.com/engine/install/) 참조하시면 됩니다.
- **git** - OpenClaw 저장소를 클론하기 위해 필요합니다. 미설치 시 [Git 설치 가이드](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) 참조하시면 됩니다.
- **클라우드 AI 구독** - 최소 하나 이상의 클라우드 AI 를 구독해야 합니다. 저자는 Anthropic Claude Max, Gemini 구독 중.

## 1단계 — OpenClaw 저장소 클론

```bash
git clone https://github.com/openclaw/openclaw.git ~/projects/openclaw-docker
```

```bash
cd ~/projects/openclaw-docker
```

## 2단계 — 컨테이너 환경설정 폴더 준비

> 공식 docker.md 에는 이 단계가 없습니다. 저자는 이미 호스트에 native 로 OpenClaw 를 설치해 운영 중이라 (`~/.openclaw/`), `setup.sh` 가 기본값대로 그 디렉토리를 컨테이너에 bind-mount 하면 native 설정·OAuth 토큰·main 에이전트 메모리가 *컨테이너 onboarding 의 결과로 덮어쓰여지거나 컨테이너에서 그대로 사용 가능* 한 상태가 됩니다. 이를 방지하기 위해 컨테이너 전용 환경설정 폴더를 별도로 만듭니다. 컨테이너의 user (`node`, uid 1000) 가 쓸 수 있도록 소유권도 미리 맞춥니다.

```bash
mkdir -p ~/.openclaw-docker/workspace ~/.openclaw-docker/.claude
```

```bash
sudo chown -R 1000:1000 ~/.openclaw-docker
```

> ⚠️ **`.claude` 디렉토리를 함께 만드는 이유 (Claude OAuth 토큰 영속화)** — 아래 [Claude OAuth 토큰의 영속화](#claude-oauth-토큰의-영속화) 절 참조. OAuth (claude-cli) 방식으로 Anthropic 을 인증한다면, 토큰이 컨테이너의 `/home/node/.claude/.credentials.json` 에 저장되는데 이 경로는 기본 마운트 3곳 (`/home/node/.openclaw`, `/.openclaw/workspace`, `/.config/openclaw`) 어디에도 포함되지 않아 **컨테이너 종료와 함께 휘발**합니다. 특히 onboarding 은 `--rm` 일회성 컨테이너에서 돌기 때문에 인증 직후 토큰이 사라져 게이트웨이가 미인증 상태로 뜨는 오류가 발생합니다. 이를 막으려고 호스트에 `.claude` 폴더를 미리 만들고 3단계에서 마운트합니다.

> ⚠️ **(OAuth 방식) Claude CLI 자격증명 선반입 — 저자 실측으로 추가**: onboarding 의 "Anthropic Claude CLI" 인증 방식은 컨테이너 안에서 OAuth 플로우를 *새로 띄우지 않고*, 이미 인증된 Claude CLI 자격증명을 **재사용**합니다. 그래서 바인드된 `.claude` 폴더가 비어 있으면 다음 에러로 중단됩니다:
>
> ```
> Error: Claude CLI is not authenticated on this host.
> Run claude auth login first, then re-run this setup.
> ```
>
> 따라서 3단계(setup.sh) 실행 전에, 컨테이너가 볼 위치(`~/.openclaw-docker/.claude/`)에 자격증명 파일을 미리 넣어야 합니다.
>
> **호스트에 이미 Claude Code(CLI)가 인증돼 있으면** — native `~/.claude/.credentials.json` 을 복사 (가장 빠름, 저자 검증 경로):
>
> ```bash
> cp ~/.claude/.credentials.json ~/.openclaw-docker/.claude/
> sudo chown 1000:1000 ~/.openclaw-docker/.claude/.credentials.json
> ```
>
> **호스트에 Claude CLI 인증이 없으면** — 컨테이너 안에서 1회 OAuth 로그인을 진행해 토큰을 바인드 폴더에 써야 합니다(OpenClaw 버전에 따라 명령 상이, 미검증). 또는 onboarding 에서 **API 키 방식**을 고르면 이 선반입 자체가 불필요합니다(아래 [Anthropic 인증 방식](#anthropic-인증-방식--oauth-권장) 절).
>
> 토큰 복사는 native 와 같은 OAuth 자격증명을 컨테이너가 함께 쓰는 것이라 격리를 약간 약화시킵니다. 완전 격리가 필요하면 컨테이너 전용 OAuth 를 1회 새로 진행하세요.

## 3단계 — 셋업 스크립트 실행

미리 빌드된 ghcr 이미지를 사용하고 (로컬 빌드 생략 — 빠르고 RAM 부담 없음), 위 2단계에서 만든 별도 폴더를 마운트하도록 아래 환경변수를 **`export`** 한 뒤 `setup.sh` 를 실행합니다 (native 와 병행 설치라면 포트 재지정 변수도 함께 — 이 블록 맨 아래). **반드시 `export` 키워드를 붙여야** 다음 줄의 자식 프로세스 (`setup.sh`) 에 전달됩니다 (`export` 없이 `VAR=value` 만 쓰면 현재 셸 변수로만 남고 자식 프로세스에선 못 봅니다).

```bash
export OPENCLAW_IMAGE="ghcr.io/openclaw/openclaw:latest"
```

```bash
export OPENCLAW_CONFIG_DIR=$HOME/.openclaw-docker
```

```bash
export OPENCLAW_WORKSPACE_DIR=$HOME/.openclaw-docker/workspace
```

```bash
export OPENCLAW_EXTRA_MOUNTS="$HOME/.openclaw-docker/.claude:/home/node/.claude"
```

> 이 네 번째 변수가 Claude OAuth 토큰을 호스트에 영속화합니다 (위 2단계 ⚠️ + 아래 [Claude OAuth 토큰의 영속화](#claude-oauth-토큰의-영속화) 절). `setup.sh` 는 `OPENCLAW_EXTRA_MOUNTS` (형식 `source:target`) 를 받아 compose 오버레이로 추가 마운트를 생성합니다. **API 키 방식만 쓸 경우엔 이 변수가 불필요** 하지만, 저자는 요금제 이유로 OAuth 를 권장하므로 (아래 절) 기본 포함합니다.

**(선택) native OpenClaw 와 같은 머신에 병행 설치하는 경우** — native 게이트웨이가 이미 `18789` 를 점유 중이므로, 호스트 포트를 재지정하는 다섯 번째 변수도 **setup.sh 실행 전에** 함께 export 합니다:

```bash
export OPENCLAW_GATEWAY_PORT=18889   # 호스트 18889 → 컨테이너 18789 (병행 설치 시에만)
```

> `setup.sh` 의 마지막 단계가 게이트웨이를 이 포트로 기동하므로, **미리 설정하지 않으면 그 단계가 `address already in use` 로 실패**합니다 (저자 실측 — 아래 [트러블슈팅](#포트-18789-이미-사용-중-native-openclaw-와-병행-시--저자-실측) 참조). native 가 없는 일반 설치(외부 사용자 대다수)는 기본 `18789` 로 충분하니 이 변수는 생략합니다.

```bash
./scripts/docker/setup.sh
```

전달이 잘 됐다면 setup.sh 가 다음을 자동 수행합니다:

- ghcr 에서 미리 빌드된 게이트웨이 이미지 pull (출력: `Pulling ghcr.io/openclaw/openclaw:latest ...`)
- onboarding 위저드 — 프로바이더 선택 + API 키 / OAuth 인증
- 게이트웨이 토큰 생성 → `~/.openclaw-docker/.env` 에 기록
- `docker compose` 로 게이트웨이 기동

> ⚠️ **검증 포인트**: setup.sh 출력에 `Reusing gateway token from /home/ben/.openclaw/openclaw.json` 또는 `Building Docker image: openclaw:local` 가 나오면 환경변수가 **전달 안 됐다는 신호** 입니다 (prod `~/.openclaw/` 사용 + 로컬 빌드 모드). 즉시 `Ctrl+C` 로 중단하고 export 부터 다시 시작하세요.

> 로컬 이미지 빌드 (`./scripts/docker/setup.sh` 만 단독 실행, `OPENCLAW_IMAGE` 없이) 는 *OpenClaw contributor 가 소스를 수정한 뒤 그 변경을 빌드해 검증할 때* 만 사용합니다. 일반 사용자·교육 시연에는 ghcr 본이 빠르고 RAM OOM 위험 없습니다.

### 위저드 prompt — "personal-by-default"

setup.sh 의 첫 prompt — *I understand this is personal-by-default and shared/multi-user use requires lock-down. Continue?* — 는 OpenClaw 가 *개인 사용* 을 기본 가정한다는 확인입니다 (gateway 가 `127.0.0.1:18789` 에 personal mode 로 바인드, 추가 격리 없음).

- **혼자 사용하는 컴퓨터** (개인 노트북·데스크탑) → **Y** 또는 **Enter**.
- **공유 머신** (VPS·강의실 공용 PC·다중 사용자 서버) → 진행 전에 [공식 보안 가이드](https://docs.openclaw.ai/gateway/security) 검토 + onboarding 후 `gateway.bind=loopback` 등 lock-down 설정 필요.

### 위저드 prompt — Setup mode

다음 prompt — *Setup mode: ● QuickStart (recommended) / ○ Manual setup* — 는 셋업 진행 방식 선택입니다.

- **초보자·교육 시연·일반 운영** → **QuickStart**. 합리적 기본값으로 자동 구성, 핵심 prompt (프로바이더 선택·자격증명) 만 묻고 나머지는 default. 빠르게 작동하는 인스턴스 확보 후 필요하면 `openclaw configure` 로 나중에 조정 가능.
- **고급 사용자·특수 환경** (비표준 포트·custom bind·sandboxing 활성화 등) → Manual setup. 모든 옵션을 명시적으로 선택해야 하므로 prompt 수가 많고 시간 더 걸림.

QuickStart 의 모든 default 는 *사후 변경 가능* 이라 초기 부담이 없습니다.

## 4단계 — Control UI 접속

브라우저에서 `http://127.0.0.1:18789/` 열고, `.env` 의 `OPENCLAW_GATEWAY_TOKEN` 값을 Settings 에 붙여넣기.

대시보드 URL 을 다시 받으려면:

```bash
docker compose run --rm openclaw-cli dashboard --no-open
```

## 5단계 — 메시징 채널 추가 (선택)

Telegram:

```bash
docker compose run --rm openclaw-cli channels add --channel telegram --token "<your-bot-token>"
```

WhatsApp (QR):

```bash
docker compose run --rm openclaw-cli channels login
```

Discord:

```bash
docker compose run --rm openclaw-cli channels add --channel discord --token "<your-bot-token>"
```

상세: [WhatsApp](https://docs.openclaw.ai/channels/whatsapp) · [Telegram](https://docs.openclaw.ai/channels/telegram) · [Discord](https://docs.openclaw.ai/channels/discord)

## 6단계 — 헬스체크

liveness (인증 불필요):

```bash
curl -fsS http://127.0.0.1:18789/healthz
```

readiness (인증 불필요):

```bash
curl -fsS http://127.0.0.1:18789/readyz
```

상세 헬스 (게이트웨이 토큰 필요):

```bash
docker compose exec openclaw-gateway node dist/index.js health --token "$OPENCLAW_GATEWAY_TOKEN"
```

## 정지·재기동·로그

정지:

```bash
docker compose down
```

재기동:

```bash
docker compose up -d openclaw-gateway
```

로그 추적:

```bash
docker compose logs -f openclaw-gateway
```

## 영속성

Docker Compose 가 다음 경로를 bind-mount 한다 — 컨테이너 교체 후에도 유지. 호스트 측 경로는 3단계에서 `export` 한 환경변수로 결정됩니다 (이 문서에선 `~/.openclaw-docker/...`):

- `${OPENCLAW_CONFIG_DIR}` → `/home/node/.openclaw` (config·agents·cron·credentials)
- `${OPENCLAW_WORKSPACE_DIR}` → `/home/node/.openclaw/workspace`
- `${OPENCLAW_AUTH_PROFILE_SECRET_DIR:-${HOME}/.openclaw-auth-profile-secrets}` → `/home/node/.config/openclaw` (auth profile secret — API 키 등)
- `${OPENCLAW_EXTRA_MOUNTS}` 로 지정한 추가 경로 (이 문서: `~/.openclaw-docker/.claude` → `/home/node/.claude`, Claude OAuth 토큰)

> 환경변수를 `export` 하지 않으면 compose 가 기본값인 `${HOME}/.openclaw` 로 fallback 합니다 — 이 문서처럼 native 와 병행 설치하는 경우엔 반드시 3단계의 `export` 가 선행되어야 native 설정을 덮어쓰지 않습니다.

> ⚠️ **이 변수들은 *모든* `docker compose` 명령에 살아 있어야 합니다 (저자 실측).** 한 번이라도 빠진 셸에서 `up`·`run`·`down` 등을 돌리면 compose 가 기본값(포트 18789·`openclaw:local`·native `~/.openclaw`)으로 컨테이너를 **recreate** 하다 충돌나며, 돌고 있던 컨테이너까지 망가뜨립니다.
>
> **`.env` 의 한계 — `setup.sh` 는 못 덮습니다.** 이 문서가 `export` 방식을 쓰는 이유가 여기 있습니다. 소비자가 둘이고 변수를 읽는 방식이 다릅니다:
>
> - **`setup.sh`** (3단계) — bash 스크립트라 compose `.env` 를 **읽지 않고** 셸 환경변수를 직접 봅니다. 따라서 반드시 `export`(또는 `set -a; source ...; set +a`)가 선행돼야 합니다. `.env` 만 두고 export 를 생략하면 setup.sh 는 기본값(native `~/.openclaw`)으로 동작합니다.
> - **`docker compose`** (설치 *후* 반복되는 `up`·`down`·`run`·`logs`) — 프로젝트 디렉토리(`~/projects/openclaw-docker/`)의 `.env` 를 **자동으로** 읽습니다. 여기 변수를 적어두면 셸과 무관하게 적용돼 위 recreate 사고가 차단됩니다.
>
> 즉 `.env` 는 export 를 **대체하지 못하고**, *설치 후 운영* 단계만 보완합니다. (`.env` 엔 setup.sh 가 `OPENCLAW_GATEWAY_TOKEN` 을 기록하므로 경로/포트 변수만 추가하고, compose `.env` 안에서는 `$HOME` 이 확장되지 않으니 절대경로로 적습니다.)

플러그인 런타임 의존성은 별도 named volume `openclaw-plugin-runtime-deps` 에 저장 (호스트 bind mount 와 분리해 Docker Desktop / WSL 파일 I/O 마찰 회피).

## 트러블슈팅

### 이미지 빌드 중 OOM (exit 137)

RAM 2 GB 이상 필요. 더 큰 머신에서 재시도.

### `EACCES` (`/home/node/.openclaw` 권한 오류)

이미지가 uid 1000 (`node`) 으로 실행되므로 호스트 bind mount 가 uid 1000 소유여야 함 (이 문서의 컨테이너 전용 폴더 기준):

```bash
sudo chown -R 1000:1000 ~/.openclaw-docker
```

### Control UI 인증 실패 (Unauthorized / pairing required)

```bash
docker compose run --rm openclaw-cli dashboard --no-open
```

```bash
docker compose run --rm openclaw-cli devices list
```

```bash
docker compose run --rm openclaw-cli devices approve <requestId>
```

### 게이트웨이 target 이 `ws://172.x.x.x` 로 잡혀 페어링 실패

mode·bind 재설정:

```bash
docker compose run --rm openclaw-cli config set --batch-json '[{"path":"gateway.mode","value":"local"},{"path":"gateway.bind","value":"lan"}]'
```

### 포트 18789 이미 사용 중 (native OpenClaw 와 병행 시) — 저자 실측

호스트에 native OpenClaw 게이트웨이가 이미 18789 를 점유 중이면 컨테이너 기동이 `failed to bind host port 0.0.0.0:18789/tcp: address already in use` 로 실패합니다 (컨테이너가 Running 에 못 가고 `Created` 에 고착). compose 는 호스트 포트를 환경변수로 재지정할 수 있으니, 컨테이너만 다른 포트에 띄워 **공존**시킵니다 (브리지 18790 은 보통 비어 있어 그대로):

```bash
export OPENCLAW_GATEWAY_PORT=18889   # 호스트 18889 → 컨테이너 18789
docker compose -f docker-compose.yml -f docker-compose.extra.yml up -d openclaw-gateway
```

이후 Control UI·헬스체크도 새 포트(`http://127.0.0.1:18889/`)로 접근합니다. 이 변수는 위 ⚠️ 처럼 **모든 compose 명령에 동일하게** 주어야 합니다.

### Control UI: "브라우저 origin이 허용되지 않음"

포트를 재지정하면(예: 18889) 위저드가 핀해둔 `allowedOrigins`(18789)와 접속 origin(18889)이 어긋나 거부됩니다. 게이트웨이 config 의 `gateway.controlUi.allowedOrigins` 에 새 origin 을 추가하고 재시작합니다. `config set --batch-json` 은 따옴표·대괄호가 많아 멀티라인 붙여넣기에 잘 깨지므로, **config 파일을 직접 편집하는 쪽이 안전**합니다. 호스트의 `~/.openclaw-docker/openclaw.json` 에서:

```json
"allowedOrigins": [
  "http://localhost:18789",
  "http://127.0.0.1:18789",
  "http://localhost:18889",
  "http://127.0.0.1:18889"
]
```

저장 후 게이트웨이 재시작:

```bash
docker compose -f docker-compose.yml -f docker-compose.extra.yml up -d --force-recreate openclaw-gateway
```

### Control UI: "연결할 수 없음" / "device signature expired" / "pairing required" — 저자 실측

origin·토큰을 통과해도 Control UI 가 연결을 못 맺으면, 게이트웨이 로그에서 사유를 확인합니다:

```bash
docker compose -f docker-compose.yml -f docker-compose.extra.yml logs --tail=20 openclaw-gateway | grep '\[ws\]'
```

- `reason=token_missing` → 토큰 미입력. 토큰 박힌 URL(`http://127.0.0.1:<port>/#token=<TOKEN>`)로 열거나 입력칸에 붙여넣습니다. 토큰은 `~/projects/openclaw-docker/.env` 의 `OPENCLAW_GATEWAY_TOKEN`.
- `reason=pairing required: device is not approved yet (requestId: ...)` → 브라우저 device 가 승인 대기 상태입니다. 아래로 승인합니다:

  ```bash
  docker compose -f docker-compose.yml -f docker-compose.extra.yml run --rm openclaw-cli devices list
  docker compose -f docker-compose.yml -f docker-compose.extra.yml run --rm openclaw-cli devices approve <requestId>
  ```

  승인 후 브라우저는 ~15초마다 자동 재시도하므로 곧 연결됩니다(또는 Connect 재클릭).
- `reason=device signature expired` (시크릿 창에서도 반복) → 브라우저 호스트(예: Windows) 와 게이트웨이(WSL/컨테이너) 의 **시계 차이**가 서명 유효시간 검증을 깨는 경우입니다. 컨테이너=WSL 시각(`docker exec <gateway> date -u` vs `date -u`)이 맞는데도 나면 브라우저 호스트 시계를 동기합니다.

> 반복 테스트 시엔 일반 창의 캐시된 옛 device 서명이 꼬일 수 있으니, **시크릿 창**으로 토큰 URL 을 여는 것을 표준 절차로 삼으면 깔끔합니다.

더 자세한 내용은 [OpenClaw Docker 공식 문서](https://docs.openclaw.ai/install/docker) 참조.

## 컨테이너에서 호스트 LLM 사용 (Ollama · LM Studio)

컨테이너 안의 `127.0.0.1` 은 컨테이너 자신이라, 호스트에서 도는 Ollama / LM Studio 에 닿으려면 `host.docker.internal` 을 써야 한다.

호스트 측 서버를 외부 바인드로 띄우기:

```bash
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

```bash
lms server start --port 1234 --bind 0.0.0.0
```

OpenClaw onboarding 에서 URL 입력 시:

- Ollama: `http://host.docker.internal:11434`
- LM Studio: `http://host.docker.internal:1234`

## Anthropic 인증 방식 — OAuth 권장

OpenClaw 에서 Anthropic (Claude) 을 인증하는 방식은 두 가지입니다.

- **OAuth (claude-cli) — 권장.** onboarding 에서 OAuth 를 선택하면 컨테이너 안에 번들된 Claude Code (`/app/node_modules/@anthropic-ai/claude-agent-sdk-linux-x64/claude`) 의 자격증명을 사용합니다. **Claude Max / Pro 등 구독 요금제의 사용량 한도 안에서 동작** 하므로, 토큰 단위 종량 과금되는 API 키보다 비용이 예측 가능합니다.
  > ⚠️ **실측 정정 (2026-05-22)**: 최근 ghcr 빌드의 "Anthropic Claude CLI" 방식은 컨테이너 안에서 OAuth 플로우를 *새로 띄우지 않고*, 이미 인증된 Claude CLI 자격증명을 **재사용**합니다. 그래서 바인드 폴더에 토큰이 없으면 `Claude CLI is not authenticated on this host` 로 중단됩니다. → 2단계의 **자격증명 선반입**이 필요합니다.
- **API 키 — 비권장.** `ANTHROPIC_API_KEY` 또는 auth-profile secret 으로 등록. 종량 과금이라 같은 작업량이라도 구독 요금제 대비 비용이 커질 수 있어, 저자는 일반 운영에서 권장하지 않습니다. (단, API 키 방식은 secret 이 마운트된 `/home/node/.config/openclaw` 에 저장돼 영속화가 자동이므로 아래 `.claude` 마운트가 불필요하다는 *설치 편의상의* 장점은 있습니다.)

> 요금제 비용 때문에 OAuth 를 기본 권장합니다. 그래서 이 문서의 2·3단계는 OAuth 토큰 영속화를 위한 `.claude` 폴더 준비·마운트를 기본 포함합니다.

## Claude OAuth 토큰의 영속화

OAuth 방식을 쓸 때 반드시 알아야 할 함정입니다 (저자가 실측으로 확인).

**문제** — 컨테이너 HOME 은 `/home/node` 이고, Claude OAuth 토큰은 `/home/node/.claude/.credentials.json` 에 저장됩니다. 그런데 `setup.sh` 가 기본으로 마운트하는 경로는 다음 3곳뿐입니다:

- `/home/node/.openclaw` (config·agents·cron)
- `/home/node/.openclaw/workspace`
- `/home/node/.config/openclaw` (auth profile secret)

`/home/node/.claude` 는 **어디에도 포함되지 않습니다.** 게다가 onboarding 은 `setup.sh` 안에서 `docker compose run --rm` 으로 도는 **일회성 컨테이너** 입니다. 따라서 OAuth 인증을 마쳐도:

1. 토큰이 일회성 컨테이너의 `/home/node/.claude/` (마운트 안 됨) 에 기록되고
2. onboarding 컨테이너가 `--rm` 으로 종료되며 토큰이 **삭제**되고
3. 이어서 `up -d` 로 뜨는 실제 게이트웨이는 토큰이 없어 **미인증/오류** 상태가 됩니다.

**해결** — 호스트에 `.claude` 폴더를 미리 만들고 (2단계), `OPENCLAW_EXTRA_MOUNTS` 로 컨테이너의 `/home/node/.claude` 에 마운트합니다 (3단계). 이러면 토큰이 호스트 `~/.openclaw-docker/.claude/.credentials.json` 에 영속화돼 `--rm` onboarding·컨테이너 재기동에도 살아남습니다.

```bash
# 2단계에서 폴더 생성 + 소유권
mkdir -p ~/.openclaw-docker/.claude && sudo chown -R 1000:1000 ~/.openclaw-docker

# 3단계에서 마운트 변수 export
export OPENCLAW_EXTRA_MOUNTS="$HOME/.openclaw-docker/.claude:/home/node/.claude"
```

> **native 토큰 공유 대안 (비권장)**: `export OPENCLAW_EXTRA_MOUNTS="$HOME/.claude:/home/node/.claude"` 로 호스트 native 의 `~/.claude` 를 그대로 공유하면 재인증이 불필요합니다. 다만 (1) 컨테이너 격리(이 문서가 내세운 보안 이점)를 약화시키고 (2) 호스트 user(ben)와 컨테이너 user(node, uid 1000) 의 소유권이 달라 권한 마찰이 생길 수 있어 권장하지 않습니다. 별도 `~/.openclaw-docker/.claude` 에서 컨테이너용 OAuth 를 1회 새로 진행하는 쪽이 깔끔합니다.

## 다음 단계

- native 절차와의 비교: [openclaw-native.md](./openclaw-native.md)
- 자세한 공식 문서: <https://docs.openclaw.ai/install/docker>
