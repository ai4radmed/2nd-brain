# OpenClaw 업그레이드 체크리스트 (2026.5.20 → 신버전)

2nd-brain 의 OpenClaw 는 *단순 `docker pull` 이 아니다* — Claude Code(OAuth)·gog·신뢰성·자동화를 위한 **다수의 우회책**이 얹혀 있다. 업그레이드 시 **이 항목을 모두 보존/재적용/재검증**해야 깨지지 않는다. 권위 출처: `openclaw-docker-install.md`·`openclaw-docker-operations.md`·`openclaw-docker-add-gog.md`·`docker/openclaw-gateway/compose.yml`.

> 작성 2026-06-18. 현재 실행 = `ghcr.io/openclaw/openclaw:2026.5.20` **pull**(digest `sha256:a2a5cff…`), compose 프로젝트 `openclaw-docker`(`~/projects/openclaw-docker/docker-compose.yml` + `docker-compose.extra.yml`). cloned 레포 compose 는 `build: .` 도 가능(현재는 `OPENCLAW_IMAGE` override 로 pull).

---

## 0. ★GATE — 진행 전 반드시 (이게 'No' 면 전략이 바뀜)

- [x] **신버전 ghcr 이미지가 Claude Code CLI 를 번들하는가? → ❌ 아니오 (2026-06-18 웹 확정).**
  - 근거: GitHub Issue #66874 "*Official Docker image should ship with `claude` CLI pre-installed*" — `ghcr.io/openclaw/openclaw:latest`(=2026.6.x)는 **claude 를 PATH 에 안 올리고, 이미지에 미포함**. 2026.5.20 은 예외적으로 번들돼 있어 고정한 것. **upgrade 시 writable 레이어의 claude 설치는 소실 → 커스텀 Dockerfile 강제** (이슈 본문 명시).
  - **⇒ 업그레이드는 단순 pull 불가. 두 경로 중 택1:**
    - **(마운트) ✅ 검증됨(2026-06-18)** — claude 바이너리를 `~/.openclaw/bin/claude` 에 두면 PATH 맨앞이라 자동 인식(gog 와 동일 트릭). **빌드 불필요.**
    - (빌드) 커스텀 Dockerfile: 신 base + `npm install -g @anthropic-ai/claude-code` (이슈 Option A). 마운트가 안 될 때의 대안.
  - **정의적 검증(2026-06-18, pull 실측)**: `ghcr.io/openclaw/openclaw:2026.6.8`(1.56GB, Debian12/glibc2.36) — claude PATH·sdk디렉토리·바이너리 **전부 부재 확정**.
  - **마운트 검증(throwaway --rm)**: 추출 번들 claude 2.1.143 → 2026.6.8 에서 `--version` OK / 호스트 claude 2.1.181 도 OK(glibc 호환) / `~/.openclaw/bin` PATH 맨앞 노출도 OK. → **claude 바이너리는 self-contained 단일 ELF(233MB)라 마운트만으로 동작.**
  - **마운트 소스 결정 필요**: ① 번들 2.1.143 추출(버전핀·OpenClaw 테스트본, host 자동업뎃 무관) vs ② 호스트 claude(항상 최신, 단 surprise 업뎃 위험). 무인 게이트웨이라 **①(핀) 권장**.
  - ⚠️ 잔여검증(바이너리 실행 ≠ cli-backend 전체동작): 실 agent-turn·doctor 스키마·lane버그는 **2026.6.8 throwaway 게이트웨이**(별도 state+포트)로 E2E 테스트 필요.
  - ⚠️ extra.yml PATH 의 옛 sdk 경로(`/app/node_modules/@anthropic-ai/claude-agent-sdk-linux-x64`)는 신 이미지에 없음 → 무해(존재만 안 함, bin 이 먼저)하나 정리 가능.
- [x] **lane-path 버그(`MissingAgentHarnessError`)가 2026.6.8 에서 고쳐졌나? → ✅ 고쳐짐 (2026-06-18 스테이징 리허설 실증).** 재시작 후 main 세션 *이어가기* turn 이 정상 응답("네"), harness 에러 0. → **업그레이드 시 텔레그램 이어가기 실패 + 재시작마다 `/new` 가 사라짐.**
- [ ] 타깃 버전 확정(최신 vs 보수적), 다중기기(kimbi+ai4lt) 순서, 자동화 잠깐 정지 가능한 타이밍.

## 0.5 스테이징 리허설 결과 (2026-06-18, 격리 throwaway 게이트웨이로 실증)

prod `~/.openclaw` 사본 + 마운트 claude + 텔레그램/cron OFF + 포트 18889 로 2026.6.8 게이트웨이를 띄워 검증:

- ✅ **마운트 동작**: `~/.openclaw/bin/claude`(번들 2.1.143 추출) 가 2026.6.8 에서 인식·실행.
- ⚠️ **config 스키마 마이그레이션 필수**: 그대로면 `agents.defaults: Invalid input` 으로 **boot 실패**. `doctor --fix` 가 자동 복구:
  - **최상위 `agents.defaults.agentRuntime:{id:"claude-cli"}` 제거**(per-model agentRuntime 만 잔존) ← 이게 lane 버그의 그 config + 스키마 거부 원인.
  - `maxConcurrent`·`subagents` 기본값 추가, 모델목록 6→4 정리, messages/commands/plugins/skills/meta 정규화.
- ✅ **doctor --fix 후 boot 성공** + 마운트 claude 인식 + skills(ask-brain·gog·gmail-label-actions) ✓ ready.
- ✅ **실 agent-turn 완주**(lane=main, cli-backend → 마운트 claude → "네").
- ✅ **lane 버그 수정 실증**(재시작 후 이어가기 OK).
- ⏳ **미검증(실 cutover 시)**: 신뢰성 config(cliBackends watchdog+fallback)의 2026.6.8 스키마 수용, gog end-to-end, vault 마운트, 실 텔레그램 채널.

## 1. 백업·롤백 안전망

- [ ] `openclaw backup` 으로 `~/.openclaw` 상태 백업.
- [ ] **현재 2026.5.20 이미지 보관**(`docker image`) — 문제 시 핀 되돌리기.
- [ ] `~/.openclaw` 전체 + `.env` + `docker-compose.extra.yml` 별도 복사.

## 2. 이미지·빌드 모델 (A)

- [ ] `OPENCLAW_IMAGE` 새 태그로 변경 — **단 GATE 통과 시**. 미통과면 `build: .` 빌드(RAM 2GB+, OOM exit137 주의).
- [ ] cloned 레포(`~/projects/openclaw-docker`) 도 새 버전으로(빌드 시 Dockerfile 동기).

## 3. Claude Code (OAuth) 통합 — 4중 (B)

- [ ] OAuth 자격증명 선반입 유지(`~/.openclaw/.claude`, 호스트 `~/.claude` 와 독립).
- [ ] `.claude` 마운트(`~/.openclaw/.claude → /home/node/.claude`).
- [ ] **PATH fix** — 번들 claude sdk 경로가 **새 이미지에서 동일한지 재확인**(`/app/node_modules/@anthropic-ai/claude-agent-sdk-linux-x64`). 바뀌면 PATH 수정.
- [ ] **`CLAUDE_CONFIG_DIR=/home/node/.claude`** 유지(없으면 하니스 등록 실패·채널 무응답).
- [ ] 검증: `docker exec $GW claude --version`(2.1.x) + `claude -p "Reply OK"`(config-not-found 경고 無).

## 4. gog (Google Workspace) 통합 — 5중 (C)

- [ ] gog 바이너리 `~/.openclaw/bin/gog`(정적) + PATH 에 `bin/`.
- [ ] 격리 gog config(HOME-symlink 트릭, `~/.config/gogcli-openclaw-container`) 마운트.
- [ ] `GOG_KEYRING_PASSWORD`(.env+extra.yml). gogcli 마운트 `:ro` 토글.
- [ ] `~/.openclaw/workspace/USER.md` 의 gog 계정 명시 유지(계정 불일치 함정).
- [ ] 검증: `docker exec $GW gog auth list` + `gog gmail search 'newer_than:1d'`.

## 5. 신뢰성·안정성 (D)

- [ ] **model fallback + watchdog 한 쌍** 재적용: `model.fallbacks:[haiku,sonnet]` + `cliBackends.claude-cli.{command:"claude",reliability.watchdog 90s}`.
  - ⚠️ 스키마: `cliBackends` 는 `agents.defaults` 하위, `command:"claude"` 필수(없으면 crash-loop). **신버전 스키마 변경 가능 → `doctor --fix` 후 재검증.**
- [ ] spool-wedge 주의: recreate 전 진행 turn 없음 확인 + 후 `.processing` 정리.

## 6. 모델·성능 (E)

- [ ] `model.primary = anthropic/claude-haiku-4-5`, `heartbeat.every="0m"`.
- [ ] **`agents.defaults.thinking` 직접 설정 금지**(crash-loop) — 신버전도 동일한지 확인.
- [ ] `agentRuntime.id="claude-cli"`(preferred Claude CLI form) 유지 여부 — 신버전에서 lane-path 처리 확인(GATE 2 와 연동).

## 7. 채널·페어링·Control UI (F)

- [ ] 텔레그램 봇 토큰·pairing 유지(`~/.openclaw` 영속이라 보통 보존).
- [ ] Control UI **device 재승인** 필요할 수 있음(`devices approve`) + 시계 동기.
- [ ] cron CLI `--token` 필요(gateway.auth.token).

## 8. compose 하드닝·핀 (G)

- [ ] 컨테이너측 경로 핀(`OPENCLAW_STATE_DIR/CONFIG_PATH/WORKSPACE_DIR`), 포트 18789 내부고정.
- [ ] `cap_drop`(NET_RAW/NET_ADMIN)·`no-new-privileges`·`OPENCLAW_DISABLE_BONJOUR=1`.
- [ ] **모든 compose 명령에 `-f docker-compose.yml -f docker-compose.extra.yml`** 동반.

## 9. 자동화 거처 (H) — 이미지에 playwright/chromium 없음

- [ ] gmail-label-actions 템플릿 설치 유지(`~/.openclaw/workspace/skills/`).
- [ ] 브라우저형(webmail-watch·society-watch) = headed-Xvfb 사이드카(게이트웨이 cron 아님).
- [ ] 호스트 드레인(parser-drain·brain-drain) host systemd-user 타이머 — 이미지와 무관(영향 적음).
- [ ] **ask-brain**(2026-06-18 신규): OpenClaw 트리거 스킬 + 호스트 path 유닛 — `~/.openclaw/workspace/skills/ask-brain/` 보존. [[project_ask_brain_vault_boundary]]

## 10. 업그레이드 후 최종 검증

- [ ] 게이트웨이 healthy + `claude --version` + `skills list`(gog·ask-brain·gmail-label-actions ready).
- [ ] cron(gmail-label-actions) Status=ok.
- [ ] ★**텔레그램 *이어가기* 메시지 1건**(GATE 2 버그 재발 여부 — `doctor` 못 잡음, 실메시지만 확인).
- [ ] gog end-to-end(메일 읽기), ask-brain end-to-end(vault 질의).
- [ ] docs 버전핀·메모리([[project_openclaw_container_native_coexistence]]·[[reference_openclaw_claude_config_dir]]) 갱신.
- [ ] ai4lt 반복.

---

## 메타
- 근거 인벤토리: 2026-06-18 세션 조사(설치/운영/add-gog 문서 + compose + live extra.yml + 실행 이미지 digest).
- 관련: [[reference_openclaw_claude_config_dir]](하니스 lane 버그) · [[project_openclaw_container_native_coexistence]](버전핀) · [[project_ask_brain_vault_boundary]].
