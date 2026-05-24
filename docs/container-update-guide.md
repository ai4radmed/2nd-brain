# 컨테이너 업데이트 가이드 — `sb-claude` 의 Claude Code 버전 갱신

`2nd-brain-docker` 의 `sb-claude` 컨테이너에서 도는 Claude Code 의 버전을 안전하게 갱신하는 절차. **호스트(WSL2 native) 가 진실의 원천**, 컨테이너는 그 버전을 immutable build 로 추종하는 디자인.

## 목적·범위

- **무엇을 다루는가**: Claude Code 버전 갱신의 정상 절차 + 검증 + 트러블슈팅
- **무엇을 안 다루는가**: 첫 셋업 (`README.md` 의 "첫 셋업"), Claude Code 자체 사용법
- **누구에게**: Dr. Ben (재구축 시) + 같은 패턴을 따라 운영하는 다른 사용자

## 디자인 원칙 — "호스트 = 진실의 원천"

```
[호스트의 claude binary]   ← npm/nvm 으로 자동 업데이트 (Anthropic 의 release 흐름)
        │
        │  make sync 가 호스트 버전을 read
        ▼
[.env 의 CLAUDE_CODE_VERSION]   ← 핀 (truth-of-record)
        │
        │  docker compose build 시 ARG 로 주입
        ▼
[컨테이너 이미지: 2nd-brain/claude-cli:<version>]   ← immutable
        │
        │  컨테이너 안 self-update 차단 (DISABLE_AUTOUPDATER=1)
        ▼
[실행 중인 sb-claude 컨테이너]
```

핵심 invariant:
- **호스트는 자동 업데이트**: nvm npm 의 `claude` 가 자체 self-update 활성 → Anthropic 릴리스에 자동 따라감
- **컨테이너는 핀 + 수동 동기**: `.env` 의 명시 버전으로 빌드 → 명시 갱신 시점에만 변경
- **둘 사이 격차는 `make sync` 로 메움**: 호스트 → `.env` → 이미지 재빌드의 1-step 자동화

이 분리의 가치:
- ✓ 컨테이너 재현성 (특정 버전 고정 → 같은 이미지 = 같은 동작)
- ✓ 컨테이너 침해 시 self-update 가 새 코드를 끌어오는 위험 차단 (`DISABLE_AUTOUPDATER=1`)
- ✓ 호스트는 최신 받되, 컨테이너 갱신은 의도적 행위 (검증 단계 보장)

## 버전 핀 메커니즘 — 3 layers

### Layer 1: `.env` 의 `CLAUDE_CODE_VERSION`

```
CLAUDE_CODE_VERSION=2.1.128
```
- truth-of-record. 모든 후속 layer 가 이 값을 따라감
- `latest` 같은 dist-tag 사용 금지 (compose 가 명시적으로 reject — `?CLAUDE_CODE_VERSION must be set`)

### Layer 2: `compose.yml` 의 build args + image tag

```yaml
build:
  args:
    CLAUDE_CODE_VERSION: ${CLAUDE_CODE_VERSION:?...}
image: 2nd-brain/claude-cli:${CLAUDE_CODE_VERSION}
```
- 빌드 시점에 ARG 로 Dockerfile 에 전달
- 이미지 tag 가 버전과 일치 → `docker images` 로 즉시 확인 가능

### Layer 3: `Dockerfile` 의 native install

```dockerfile
FROM debian:trixie-slim
ARG CLAUDE_CODE_VERSION
RUN apt-get install -y curl ca-certificates ...
RUN curl -fsSL https://claude.ai/install.sh | bash -s ${CLAUDE_CODE_VERSION}
```
- 공식 권장 `install.sh` 의 **버전 핀 모드** (`bash -s <ver>`)
- 결과: `~/.local/share/claude/versions/<ver>/` 에 self-contained Bun-compiled binary, `~/.local/bin/claude` symlink
- **Node·npm 베이스 불필요** — Claude Code 는 runtime 임베드 binary. 베이스 이미지가 `node:24-slim` 에서 `debian:trixie-slim` 으로 슬림화 (이미지 크기 약 350 MB 감소)
- 호스트의 `install.sh` 와 정확히 동일 메커니즘 — 인지부하 통일

## 정상 업데이트 흐름 — 4단계

### Step 1 — 호스트 버전 확인

```bash
claude --version
# 예: 2.1.130 (Claude Code)
```

호스트가 자동 업데이트되어 있으면 새 버전이 보임. 만약 옛 버전이면 먼저 호스트 업데이트:
```bash
nvm use default                       # nvm 환경 활성화 (셸에 따라)
npm update -g @anthropic-ai/claude-code
claude --version                       # 갱신 확인
```

### Step 2 — 호스트 ↔ 컨테이너 동기

```bash
cd ~/projects/2nd-brain-docker
make sync
```

`scripts/bin/sync-claude-version.sh` 가 실행:
1. 호스트 `claude --version` 파싱
2. `.env` 의 `CLAUDE_CODE_VERSION` 과 비교
3. **같으면**: "Already in sync. No rebuild needed." → 종료 (no-op)
4. **다르면**: `.env` 갱신 + `docker compose build claude`

출력 예시 (실제 갱신 시):
```
Host Claude Code: 2.1.130
Container pin:    2.1.128
Updating .env: 2.1.128 -> 2.1.130
Rebuilding image...
[+] Building 45.3s (12/12) FINISHED
Done. Run 'make restart' to swap the running container to the new image.
```

> ⚠ `make sync` 는 **이미지만 재빌드**. 실행 중인 컨테이너는 옛 이미지로 계속 돌고 있음.

### Step 3 — 컨테이너 swap

```bash
make restart
```
- 내부적으로 `docker compose down && docker compose up -d`
- `claude-state` named volume 은 보존 (auth·session·history 무손상)
- bind-mount (`vault`, `vault-guide`) 도 그대로

### Step 4 — 검증

```bash
sb-healthcheck
```

**3-way 일치** 가 핵심 — 다음이 모두 동일 버전 가리켜야:
- `.env` 의 `CLAUDE_CODE_VERSION`
- `sb-healthcheck` [8] 섹션의 `claude binary` 버전
- 컨테이너 안 `claude --version` 직접 실행 결과

`sb-healthcheck` 가 자동으로 .env vs binary 일치 검증 ([8] 섹션의 `[PASS] version matches .env`).

수동 추가 검증 (필요 시):
```bash
docker exec -it sb-claude claude --version
docker images | grep 2nd-brain/claude-cli
```

## 자주 마주칠 시나리오

### A. 일상 — 호스트가 자동 업데이트됐고 컨테이너 따라가고 싶을 때

```bash
make sync && make restart && sb-healthcheck
```

→ 한 줄. `make sync` 가 no-op 면 (이미 동기) restart 만 일어나고 끝.

### B. 특정 버전으로 핀 (downgrade 또는 보류)

호스트 자동 업데이트가 문제 있는 새 버전을 가져왔을 때, 컨테이너만 옛 버전 유지:

```bash
# .env 직접 편집
nano .env  # CLAUDE_CODE_VERSION=2.1.128 (옛 안정 버전)

make build && make restart
sb-healthcheck                       # 3-way 일치 확인
```

이 경우 `make sync` 는 호스트 버전과 다르니 매번 update 시도 → **`make sync` 사용 안 하고** 직접 `make build` 만.

### C. 컨테이너 stale 의심 — 강제 재빌드

캐시 문제·이미지 손상 의심 시:

```bash
make clean      # 컨테이너 + 이미지 + volume 삭제 (claude-state 도 사라짐 ⚠)
make build && make up
2nd-brain-docker  # 첫 진입 시 /login 1회 (auth 재발급)
```

⚠ `make clean` 은 `claude-state` volume 도 지움 → **auth·세션 이력 잃음**. login 재진행 필요.

`claude-state` 만 보존하고 이미지만 갈고 싶으면:
```bash
docker compose down                       # 컨테이너만 down (volume 보존)
docker rmi 2nd-brain/claude-cli:$(grep CLAUDE_CODE_VERSION .env | cut -d= -f2)
make build && make up
```

### D. CLI 의 새 기능을 즉시 컨테이너에 — `make sync` 의 단축

호스트에서 실험·검증 끝난 새 버전을 컨테이너에 즉시 적용:

```bash
# 호스트에서 신버전 검증 후
make sync && make restart
```

호스트가 진실 → 컨테이너 추종의 정상 흐름.

## 검증 체크리스트 (업데이트 후)

```bash
# 1. .env 와 호스트 버전 일치
diff <(claude --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1) \
     <(grep CLAUDE_CODE_VERSION .env | cut -d= -f2)

# 2. 이미지 tag 일치
docker images | grep 2nd-brain/claude-cli

# 3. 실행 중 컨테이너의 binary 버전
docker exec -it sb-claude claude --version

# 4. 종합 (3-way 일치)
sb-healthcheck                       # [8] 섹션의 PASS 확인

# 5. 컨테이너 안 self-update 비활성 확인
docker exec -it sb-claude bash -c 'echo "DISABLE_AUTOUPDATER=$DISABLE_AUTOUPDATER"'
# → DISABLE_AUTOUPDATER=1 이어야

# 6. claude-state 영구화 확인 (login 무손상)
docker exec -it sb-claude claude   # /login prompt 없이 정상 진입
```

## 트러블슈팅

### `make sync` 가 "ERROR: 'claude' not found in PATH on host"

원인: 인터랙티브 셸의 nvm PATH 가 make 의 셸 환경에 없음.

조치:
```bash
# nvm 명시적 source 후 sync
bash -lc "make sync"
# 또는 호스트 셸에서 nvm 활성화 확인 후 재시도
which claude
nvm current
```

### `make sync` 후 build 실패 — npm install OOM (exit 137)

원인: WSL2 의 메모리 부족 (sharp/libvips 빌드 등).

조치: `~/.wslconfig` (Windows 측) 메모리 늘림:
```ini
[wsl2]
memory=4GB
swap=4GB
```
PowerShell 에서 `wsl --shutdown` → 재시작 → `make build`.

### 컨테이너가 새 이미지로 안 바뀜 — `make restart` 후에도 옛 binary

원인: `restart` 가 같은 image tag 의 옛 컨테이너를 재시작했을 가능성.

조치:
```bash
docker compose down
docker compose up -d --force-recreate
sb-healthcheck
```

### 컨테이너 안에서 `claude` 가 자동 업데이트 시도 (DISABLE_AUTOUPDATER 무시)

원인: Claude CLI 의 일부 버전이 환경변수를 다르게 read.

조치: compose.yml 의 `DISABLE_AUTOUPDATER: "1"` 가 environment 에 있는지 확인. 그래도 trigger 되면 [Claude Code GitHub issues](https://github.com/anthropics/claude-code/issues) 에 보고 + 임시 우회로 `claude` 의 자체 설정으로 disable.

### 호스트 버전과 .env 가 매번 어긋남 — 호스트 자동 업데이트 너무 빠름

원인: 호스트가 거의 매일 새 버전 받음 → 매번 `make sync` 부담.

전략 옵션:
- **A**: 컨테이너를 일정 주기 (주 1회) 만 sync. `make sync` 안 하면 옛 버전 유지 — 안정성 우선.
- **B**: 호스트 자동 업데이트도 끄기 — `npm config set update-notifier false` 또는 `claude config set autoUpdates off`. 그러면 둘 다 수동.
- **C**: cron 으로 매일 자동 sync — 단 주의: cron 환경엔 nvm PATH 없음, wrapper 필요.

### `claude-state` volume 데이터 백업

login 정보·세션 history 가 휘발 위험 시 백업:
```bash
docker run --rm -v 2nd-brain-docker_claude-state:/state -v "$PWD":/backup alpine \
  tar czf /backup/claude-state-$(date +%Y%m%d).tar.gz -C /state .
```

복구:
```bash
docker run --rm -v 2nd-brain-docker_claude-state:/state -v "$PWD":/backup alpine \
  tar xzf /backup/claude-state-YYYYMMDD.tar.gz -C /state
```

## 운영 사례

| 일자 | 호스트 버전 | 컨테이너 버전 | 액션 |
|---|---|---|---|
| 2026-05-04 | 2.1.128 | 2.1.128 | 초기 셋업, 동기 상태 |
| (다음 sync 시 갱신) | | | |

새 sync 시 본 표 갱신.

## 관련 문서

- `README.md` — 첫 셋업 및 일상 사용
- `docs/openclaw-setup.md` — OpenClaw 셋업 (다른 도구의 동일 패턴)
- `docs/syncthing-setup.md` — vault 동기 (호스트 측 인프라)
- `docs/gogcli-container-setup.md` — gog 의 컨테이너 격리 (Option B)
- `2nd-brain-vault/knowledge/02_areas/brain-system/tools/claude-code/notes/claude-code-devcontainer.md` — Anthropic 공식 devcontainer 패턴 비교 (vault, 비공개)
- `scripts/bin/sb-healthcheck` — 3-way 일치 검증 도구
- `scripts/bin/sync-claude-version.sh` — `make sync` 의 본체

## 변경 이력

- **2026-05-06**: 초안. 호스트 = 진실의 원천 디자인 + 4단계 정상 흐름 + 검증 체크리스트 + 트러블슈팅 7케이스 정리.
