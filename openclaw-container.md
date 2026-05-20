# OpenClaw 게이트웨이 — Docker 컨테이너 설치

[OpenClaw 공식 Docker 설치 문서](https://docs.openclaw.ai/install/docker) 를 따른 절차. 각 명령은 한 줄씩 그대로 복사·붙여넣기 가능.

## 언제 컨테이너를 고르나

- 호스트를 흔들지 않고 격리 환경에서 OpenClaw 를 띄우고 싶을 때 (데모·테스트)
- 다중 인스턴스 운영 — 한 머신에서 prod·demo 두 게이트웨이 동시 실행
- VPS 같은 공유 호스트에서 깔끔한 boundary 가 필요할 때

본인 머신에서 영속 운영이 목적이라면 [native 설치](./openclaw-native.md) 가 더 단순.

## 전제

- Docker Desktop 또는 Docker Engine + Docker Compose v2
- 이미지 빌드용 RAM 최소 2 GB (1 GB 호스트에서는 `pnpm install` OOM-kill, exit 137)
- 이미지·로그 저장용 디스크 여유

Docker 미설치 시: [Docker Engine 설치 가이드](https://docs.docker.com/engine/install/) 또는 [Docker Desktop](https://docs.docker.com/desktop/) 참조.

## 1단계 — OpenClaw 저장소 클론

```bash
git clone https://github.com/openclaw/openclaw.git ~/openclaw
```

```bash
cd ~/openclaw
```

## 2단계 — 셋업 스크립트 실행

로컬 이미지 빌드 (기본):

```bash
./scripts/docker/setup.sh
```

또는 미리 빌드된 ghcr 이미지 사용 (빌드 생략, 빠름):

```bash
OPENCLAW_IMAGE="ghcr.io/openclaw/openclaw:latest" ./scripts/docker/setup.sh
```

`setup.sh` 가 다음을 자동 수행한다:

- 게이트웨이 이미지 빌드 (또는 ghcr 이미지 pull)
- onboarding 위저드 — 프로바이더 API 키 입력
- 게이트웨이 토큰 생성 → `.env` 에 기록
- `docker compose` 로 게이트웨이 기동

## 3단계 — Control UI 접속

브라우저에서 `http://127.0.0.1:18789/` 열고, `.env` 의 `OPENCLAW_GATEWAY_TOKEN` 값을 Settings 에 붙여넣기.

대시보드 URL 을 다시 받으려면:

```bash
docker compose run --rm openclaw-cli dashboard --no-open
```

## 4단계 — 메시징 채널 추가 (선택)

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

## 5단계 — 헬스체크

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

Docker Compose 가 다음 경로를 bind-mount 한다 — 컨테이너 교체 후에도 유지:

- `${HOME}/.openclaw` → `/home/node/.openclaw` (config·agents·cron·credentials)
- `${HOME}/.openclaw/workspace` → `/home/node/.openclaw/workspace`

플러그인 런타임 의존성은 별도 named volume `openclaw-plugin-runtime-deps` 에 저장 (호스트 bind mount 와 분리해 Docker Desktop / WSL 파일 I/O 마찰 회피).

## 트러블슈팅

### 이미지 빌드 중 OOM (exit 137)

RAM 2 GB 이상 필요. 더 큰 머신에서 재시도.

### `EACCES` (`/home/node/.openclaw` 권한 오류)

이미지가 uid 1000 (`node`) 으로 실행되므로 호스트 bind mount 가 uid 1000 소유여야 함:

```bash
sudo chown -R 1000:1000 ~/.openclaw
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

## 다음 단계

- native 절차와의 비교: [openclaw-native.md](./openclaw-native.md)
- 자세한 공식 문서: <https://docs.openclaw.ai/install/docker>
