# OpenClaw 게이트웨이 — native 설치

[공식 OpenClaw Install 문서](https://docs.openclaw.ai/install) 를 따른 절차. 각 명령은 한 줄씩 그대로 복사·붙여넣기 가능.

## 전제

- Node 24 (권장) 또는 Node 22.14+ — 인스톨러가 자동 처리
- macOS / Linux / WSL2 / Windows — WSL2 가 가장 안정적

## 1단계 — 인스톨러 스크립트

macOS / Linux / WSL2:

```bash
curl -fsSL https://openclaw.ai/install.sh | bash
```

Windows (PowerShell):

```powershell
iwr -useb https://openclaw.ai/install.ps1 | iex
```

인스톨러가 OS 를 감지해 Node 설치 (필요 시) → OpenClaw 설치 → onboarding 위저드까지 자동 수행한다.

onboarding 을 건너뛰고 설치만 하려면:

```bash
curl -fsSL https://openclaw.ai/install.sh | bash -s -- --no-onboard
```

## 2단계 — 검증

```bash
openclaw --version
```

```bash
openclaw doctor
```

```bash
openclaw gateway status
```

`openclaw` 명령이 안 찾힐 경우 아래 [트러블슈팅](#트러블슈팅) 참조.

## 3단계 — 데몬 등록 (Linux / WSL2 / macOS)

호스트 부팅 시 게이트웨이가 자동 기동되도록 systemd user service (또는 macOS LaunchAgent) 로 등록:

```bash
openclaw gateway install
```

또는 onboarding 단계에서 함께 등록하려면:

```bash
openclaw onboard --install-daemon
```

Linux / WSL2 에서 사용자 세션 종료 후에도 데몬이 살아 있게 하려면:

```bash
sudo loginctl enable-linger $USER
```

## 4단계 — Control UI 접속

브라우저에서 `http://127.0.0.1:18789/` 열기. 게이트웨이 토큰을 Settings 에 입력. 토큰 확인:

```bash
cat ~/.openclaw/.env | grep OPENCLAW_GATEWAY_TOKEN
```

대시보드 URL 을 다시 받으려면:

```bash
openclaw dashboard --no-open
```

## 5단계 — 메시징 채널 추가 (선택)

Telegram:

```bash
openclaw channels add --channel telegram --token "<your-bot-token>"
```

WhatsApp (QR):

```bash
openclaw channels login
```

Discord:

```bash
openclaw channels add --channel discord --token "<your-bot-token>"
```

상세: [WhatsApp](https://docs.openclaw.ai/channels/whatsapp) · [Telegram](https://docs.openclaw.ai/channels/telegram) · [Discord](https://docs.openclaw.ai/channels/discord)

## 업데이트·재시작·중지

업데이트:

```bash
openclaw update
```

게이트웨이 재시작:

```bash
openclaw gateway restart
```

게이트웨이 중지:

```bash
openclaw gateway stop
```

상태 확인:

```bash
openclaw gateway status
```

## 데이터 위치

OpenClaw 의 모든 영속 상태는 `~/.openclaw/` 에 저장된다:

- `~/.openclaw/openclaw.json` — gateway token·OAuth profile·Telegram bot token 등 (secret 포함, 백업 시 주의)
- `~/.openclaw/agents/<agentId>/` — 에이전트별 메모리·인증 프로파일
- `~/.openclaw/cron/jobs.json` — cron 정의
- `~/.openclaw/workspace/` — main 에이전트 워크스페이스 (skill·메모리)

## 트러블슈팅

### `openclaw` 명령을 찾을 수 없음

전역 npm prefix 가 `$PATH` 에 없을 가능성. 확인:

```bash
node -v
```

```bash
npm prefix -g
```

```bash
echo "$PATH"
```

`$(npm prefix -g)/bin` 이 `$PATH` 에 없으면 shell rc 에 추가:

```bash
echo 'export PATH="$(npm prefix -g)/bin:$PATH"' >> ~/.zshrc
```

(bash 면 `~/.bashrc`.) 새 터미널을 연 뒤 다시 시도.

### sharp 빌드 실패 (libvips 충돌, npm 직접 설치 시)

```bash
SHARP_IGNORE_GLOBAL_LIBVIPS=1 npm install -g openclaw@latest
```

## 다음 단계

- 다른 머신에서도 동일하게 깔려면 같은 절차를 그 머신에서 반복.
- 컨테이너로 격리 실행해보려면: [openclaw-container.md](./openclaw-container.md).
- 자세한 공식 문서: <https://docs.openclaw.ai/install>.
