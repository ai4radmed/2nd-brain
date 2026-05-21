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

## 3단계 — 셋업 스크립트 실행

미리 빌드된 ghcr 이미지를 사용하고 (로컬 빌드 생략 — 빠르고 RAM 부담 없음), 위 2단계에서 만든 별도 폴더를 마운트하도록 세 환경변수를 **`export`** 한 뒤 `setup.sh` 를 실행합니다. **반드시 `export` 키워드를 붙여야** 다음 줄의 자식 프로세스 (`setup.sh`) 에 전달됩니다 (`export` 없이 `VAR=value` 만 쓰면 현재 셸 변수로만 남고 자식 프로세스에선 못 봅니다).

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

- **OAuth (claude-cli) — 권장.** onboarding 에서 OAuth 를 선택하면 컨테이너 안에 번들된 Claude Code (`/app/node_modules/@anthropic-ai/claude-agent-sdk-linux-x64/claude`) 가 OAuth 플로우를 진행하고, 발급된 토큰을 `~/.claude/.credentials.json` 에 저장합니다. **Claude Max / Pro 등 구독 요금제의 사용량 한도 안에서 동작** 하므로, 토큰 단위 종량 과금되는 API 키보다 비용이 예측 가능합니다.
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
