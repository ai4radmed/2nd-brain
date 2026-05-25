# openclaw-gateway — 2nd-brain OpenClaw 게이트웨이 (canonical docker 구성)

공식 **ghcr 이미지를 pull** 해 구동하는 운영 정본. `~/.openclaw` 를 bind-mount 해 상태 영속.
(커스텀 이미지 빌드 없음 — 그래서 OpenClaw 본가 소스 clone 불필요.)

## 파일
- `compose.yml` — 단일 정본 compose (ghcr pull, `container_name: 2nd-brain-openclaw-gateway`)
- `.env.example` — 환경변수 템플릿. `.env` 로 복사·채움 (`.env` 는 secret 포함 → git 미추적)

## 실행
```bash
cd ~/projects/2nd-brain/docker/openclaw-gateway
cp .env.example .env          # secret·경로 채움
docker compose up -d openclaw-gateway
docker compose run --rm openclaw-cli <openclaw 명령>
```
설치·트러블슈팅 상세: [`../../docs/openclaw-docker-install.md`](../../docs/openclaw-docker-install.md), gog 통합: [`../../docs/openclaw-docker-gog.md`](../../docs/openclaw-docker-gog.md).

## 이력
- **2026-05-25 ghcr canonical 화**: 구 `compose.openclaw.yml`(2nd-brain-docker "박물관" 흡수분 — *커스텀 빌드* `2nd-brain/openclaw-gateway` 이미지 + `sb-openclaw`, **실행된 적 없는 죽은 파일**)와 `Dockerfile` 을 제거하고, 실제 운영(ghcr-pull)과 일치하는 `compose.yml` 로 교체.
  - 그간 라이브 실행은 본가 클론 `~/projects/openclaw-docker` 에서 `docker-compose.yml`(본가) + `docker-compose.extra.yml`(우리, gitignore·로컬전용·미동기)로 했음 → 그 구성을 이 단일 compose 로 인코딩해 **git 동기·재현 가능**하게 함.
- ⚠️ **라이브 실행 위치 전환**(`openclaw-docker` → 이 폴더)은 별도 검증 단계: `.claude` 자격증명이 현재 `~/.openclaw-docker/.claude` 에 있어, 전환 시 `.env` 의 `OPENCLAW_CLAUDE_DIR` 로 지정하거나 `~/.openclaw/.claude` 로 이전 필요. 전환 전까지 실행 권위는 `openclaw-docker`.
