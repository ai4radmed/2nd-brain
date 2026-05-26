# OpenClaw Docker — 운영 심화 (Control UI·자동화·신뢰성)

> [openclaw-docker-install.md](./openclaw-docker-install.md) 로 기본 설치(봇 동작·초기 설정)를 마친 뒤 보는 **심화** 문서입니다. 초보자는 install 문서만으로 충분합니다. 여기서는 Control UI(로컬 대시보드)·스킬 무인 자동화(cron·사이드카)·스트리밍 stall 자동복구·운영 트러블슈팅을 다룹니다.

## Control UI 접속 (로컬 전용·선택)

> Control UI = 웹 **대시보드**(게이트웨이 웹 관리창). **`127.0.0.1` 로컬에서만** 열리므로 *원격(집)에서는 Telegram 이 주 창구*이고, 이건 로컬에서 상태·로그·설정을 볼 때 쓰는 **선택** 단계입니다.

브라우저에서 `http://127.0.0.1:18789/` 열고 **게이트웨이 토큰**을 입력칸에 붙여넣습니다. 토큰 위치:
- `~/projects/openclaw-docker/.env` 의 `OPENCLAW_GATEWAY_TOKEN` (setup.sh 가 기록 — **`~/.openclaw/.env` 아님**에 주의), 또는
- 권위 원본 `~/.openclaw/openclaw.json` 의 `gateway.auth.token`.

토큰 박힌 URL 로 바로 열려면:

```bash
docker compose -f docker-compose.yml -f docker-compose.extra.yml run --rm openclaw-cli dashboard --no-open
```

### 트러블슈팅 — 토큰은 맞는데 연결 안 됨 (저자 실측, 반복 발생)

게이트웨이 로그에서 `[ws] ... reason=` 를 먼저 확인:
```bash
docker compose -f docker-compose.yml -f docker-compose.extra.yml logs --tail=30 openclaw-gateway | grep '\[ws\]'
```
- `reason=pairing required: device is not approved yet (requestId: ...)` / `device_token_mismatch` → **브라우저 device 승인 필요**:
  ```bash
  GW=$(docker ps --filter name=openclaw-gateway --format '{{.Names}}' | head -1)
  docker exec -e OPENCLAW_GATEWAY_PORT=18789 "$GW" node dist/index.js devices list            # Pending 의 requestId 확인
  docker exec -e OPENCLAW_GATEWAY_PORT=18789 "$GW" node dist/index.js devices approve <requestId>
  ```
  승인 후 브라우저 **새로고침** → 연결.
- `reason=device signature expired` 가 (승인 후에도) **반복** → 브라우저 호스트(Windows)와 게이트웨이(WSL/컨테이너)의 **시계 차이**. 컨테이너=WSL 시각은 보통 동기이니 **Windows 시계 동기**(설정 → 시간 및 언어 → "지금 동기화"), 필요시 WSL `sudo hwclock -s`.

## 스킬·cron — 무인 자동화 (게이트웨이 cron vs 사이드카)

스킬을 무인 주기 실행하려면 **그 스킬이 브라우저를 쓰는지**에 따라 거처가 갈린다. 게이트웨이 컨테이너(ghcr 이미지)에는 **playwright/chromium 이 없다** — 그래서:

| 스킬 유형 | 예 | 무인 거처 |
|---|---|---|
| **텍스트형**(gog API·LLM, 브라우저 X) | `gmail-label-actions`(라벨→GWS 후속작업), `gws-assistant` | **게이트웨이 cron** (컨테이너 안) |
| **브라우저형**(playwright headed) | `webmail-watch`(anti-headless SPA), `society-watch` | **별도 headed-Xvfb 사이드카** + host 스케줄러 |

### 9a. 게이트웨이 cron — gmail-label-actions (무인 메일 처리)

라벨(1~8) 단 메일을 Calendar/Tasks/Drafts 후속작업으로 완결·캡처. 브라우저 비의존이라 게이트웨이 cron 에서 안전.

> **전제 — 이 스킬은 번들이 아니라 *템플릿*이라 먼저 설치해야 한다** (저자 실측: 설치 안 하면 봇이 스킬 자체를 모름):
> ```bash
> cp -r ~/projects/2nd-brain/templates/skills/openclaw/gmail-label-actions ~/.openclaw/workspace/skills/
> ```
> 그 뒤 ① env `GMAIL_ROUTER_ACCOUNT`(gog 계정과 동일) 를 컨테이너에 주입(`.env` + extra.yml — `GOG_KEYRING_PASSWORD` 와 동일 방식), ② Gmail 라벨 `1 저장`…`8 회신`+`9 완료`(9개) 준비, ③ 재생성. 설치·적응·라벨 규칙은 [그 스킬 README](../templates/skills/openclaw/gmail-label-actions/README.md), 런타임(OpenClaw vs Claude Code) 구분은 [templates/skills/README.md](../templates/skills/README.md).

설치 후 `~/.openclaw/cron/jobs.json` 에 잡 추가:

```jsonc
{ "version": 1, "jobs": [{
  "id": "<uuid>", "agentId": "main", "name": "gmail-label-actions-poll",
  "enabled": true,
  "schedule": { "kind": "cron", "expr": "*/30 * * * *" },
  "sessionTarget": "isolated", "wakeMode": "now",
  "payload": { "kind": "agentTurn", "message": "/gmail-label-actions" },
  "delivery": { "mode": "announce", "channel": "telegram", "to": "<chatId>" }
}]}
```

반영(`--force-recreate`) 후 검증 — **cron CLI 는 게이트웨이 토큰 필요**:

```bash
GW=$(docker ps --filter name=openclaw-gateway --format '{{.Names}}' | head -1)
TOK=$(docker exec "$GW" sh -c 'python3 -c "import json;print(json.load(open(\"/home/node/.openclaw/openclaw.json\"))[\"gateway\"][\"auth\"][\"token\"])"')
docker exec "$GW" node /app/dist/index.js cron list --token "$TOK"   # Next 시각·enabled 확인
```

> ⚠️ `--token` 없이 `cron list/status` 하면 `gateway token mismatch` 로 거부됨(remote.token 미설정).
> 동작 검증(비파괴): `docker exec "$GW" sh -c 'cd /home/node/.openclaw/workspace/skills/gmail-label-actions && python3 run.py --dry-run'` — 라벨별 건수만 검색.

### 9b. 브라우저형 사이드카 — webmail-watch (headed-under-Xvfb)

KIRAMS 같은 anti-headless SPA 는 headless 면 빈 shell 백지 → **headed(가상 디스플레이 Xvfb)** 라야 렌더. 게이트웨이엔 브라우저가 없으므로 **별도 사이드카 이미지**(Playwright 공식 이미지 + Xvfb 직접 기동)로 분리하고, **host systemd-timer**(또는 cron)가 1회성 `docker compose run --rm` 으로 주기 호출한다(게이트웨이 cron→docker 는 docker socket 권한상승이라 회피).

자세한 레시피·자산: vault `knowledge/02_areas/brain-system/tools/openclaw/webmail-sidecar/`. 핵심:

```bash
# host systemd-user 타이머 (예: 평일 08-18시 매시)
systemctl --user enable --now openclaw-webmail-sidecar.timer
```

## 신뢰성 — 스트리밍 stall 과 자동 복구 (watchdog + model fallback) ★

> **증상**: 봇이 특정 turn 에서 **아무 응답도 안 하고 멈췄다가**(thinking 조차 없음) 한참 뒤 `Something went wrong` / 로그에 `CLI produced no output for 180s` · `turn failed ... FailoverError`. 가벼운 turn(인사·간단 검색)은 멀쩡한데 **무거운 resume·cold-start turn 만 간헐적으로** 걸린다. **이 설정 없이 그대로 두면 stall 이 재발한다.**

### 근본 원인 — 컨테이너가 아니라 Claude Code 스트리밍 버그

라이브 포렌식 결과 이건 OpenClaw·Docker 고유 문제가 **아니다**. 상위 **Claude Code 의 스트리밍 연결 stall 버그**다:

- claude 가 Anthropic 소켓에서 응답을 기다리며 `epoll_wait` 에 무한 매달림 — **read-timeout 부재**. 죽은 연결을 재사용하면 응답이 영영 안 옴.
- 어시스턴트 출력이 0 byte → OpenClaw 의 **no-output watchdog**(기본 180초)이 turn 을 강제 종료 → `FailoverError`.
- 공개 이슈: claude-code [#25979](https://github.com/anthropics/claude-code/issues/25979)(read-timeout 부재 무한 hang), [#23081](https://github.com/anthropics/claude-code/issues/23081)(retry 가 stale http2 pool 미리셋), [#53328](https://github.com/anthropics/claude-code/issues/53328)(tool_result 유실 후 hang).
- 컨테이너에서 빈도가 **더 높아 보이는 이유**는 NAT 가 idle 연결을 더 빨리 떨궈서일 뿐, 원인은 동일. host native 게이트웨이에서도 같은 계열로 발생한다.

검증으로 배제된 헛다리: ❌ 모델/인증/네트워크 (격리 시 bare `claude -p` 는 2초 정상, 토큰·망 OK) · ❌ raw 프롬프트 크기 (120KB fresh 프롬프트는 컨테이너·호스트 둘 다 7~11초 정상) · ❌ 블로그발 `CLAUDE_ENABLE_BYTE_WATCHDOG`·`CLAUDE_STREAM_IDLE_TIMEOUT_MS` env (claude 2.1.x 바이너리·번들에 그 문자열 **부재** — strings 로 실재 검증함. **claude-side 노브 없음 확정**).

### 해결 — OpenClaw 레이어에서 잡는다 (두 설정 한 쌍)

claude-side 에 손댈 노브가 없으므로 **OpenClaw 가 stall 을 감지(watchdog)하고 다른 모델로 재시도(model fallback)** 하게 한다. 둘은 짝이다 — watchdog 만 있으면 죽이기만 하고, fallback 만 있으면 watchdog 이 안 깨우면 영영 매달린다.

```bash
python3 - <<'PY'
import json, pathlib
f = pathlib.Path.home()/".openclaw/openclaw.json"
d = json.loads(f.read_text())
defs = d["agents"]["defaults"]

# (1) model fallback — primary stall→FailoverError 시 다음 모델로 자동 재시도.
#     재시도는 fresh 프로세스/연결이라 죽은 http2 연결을 버리고 복구된다.
defs["model"] = {
    "primary": "anthropic/claude-haiku-4-5",
    "fallbacks": ["anthropic/claude-haiku-4-5", "anthropic/claude-sonnet-4-6"],
}

# (2) reliability watchdog — no-output 타임아웃을 180→90s 로 단축해 복구를 앞당김.
#     ⚠️ "command":"claude" 가 없으면 스키마 검증에서 거부된다.
defs["cliBackends"] = {
    "claude-cli": {
        "command": "claude",
        "reliability": {"watchdog": {
            "fresh":  {"noOutputTimeoutMs": 90000},
            "resume": {"noOutputTimeoutMs": 90000},
        }},
    }
}
f.write_text(json.dumps(d, indent=2, ensure_ascii=False)); print("ok")
PY
```

적용: install 5단계의 `--force-recreate`. 게이트웨이 healthy + 일반 turn 정상 회신 확인.

**동작 흐름**: stall → watchdog 90s 종료 → `turn failed FailoverError` → 로그 `model fallback decision: next=anthropic/claude-sonnet-4-6`(설정 전엔 `next=none` 이라 재시도 안 했음) → `cli exec model=sonnet`(새 프로세스/연결) → 보통 8~9초 정상 완료. stall turn 총 소요는 ~100~200초(watchdog 대기 + 재시도)로 느리지만, **무응답 → 복구**로 바뀐다. (실증 2026-05-23: haiku 186s stall → sonnet 8.7s 성공 → 봇 정상 회신.)

### 설정 함정 (실측)

- **`cliBackends` 위치**: 반드시 `agents.defaults` **하위**. top-level 에 넣으면 `Invalid config <root>: Invalid input` 으로 **게이트웨이 crash-loop**.
- **`command: "claude"` 필수**: `CliBackendSchema` 가 `command` 를 요구 → `reliability` 만 넣으면 스키마 거부.
- **noOutputTimeoutMs 범위**: 최소 1000ms, 전체 agent timeout(`agents.defaults.timeoutSeconds`, 기본 600초)−1초 로 cap. 90초는 "빠른 복구" 선택이고, 재시도 자체가 싫으면 180→600 상향(완화)만 해도 된다.
- **provider prefix**: 위 예시는 컨테이너 OAuth 라 `anthropic/...`. host native + claude CLI 백엔드는 `claude-cli/claude-opus-4-7` 같은 표기를 쓴다 — 환경의 모델 ID 표기에 맞춰라.

### 부작용 — stall 이 텔레그램 수신 큐 전체를 막는다 (spool-wedge)

OpenClaw 텔레그램은 수신 메시지를 spool(`<config>/telegram/ingress-spool-default/`)에 적재하고 **1건씩 순서대로** 처리한다. stall 난 turn 이 `.json.processing` 락을 쥔 채 멈추면 **그 뒤 모든 메시지가 큐에서 영구 대기** — `/new` 조차 무응답. fallback 이 stall 을 빨리 복구하면 이 wedge 도 함께 완화되지만, 이미 막혔다면:

1. spool 디렉토리 `ls` 로 `.processing` 잔존·미처리 `.json` 적체 확인 (`getWebhookInfo` 의 pending 은 0 으로 정상으로 보일 수 있음 — spool 은 그 아래 계층).
2. 막은 항목을 spool 밖으로 이동(재처리 시 재stall 방지 — staller 는 버린다) → 게이트웨이 재시작 → 잔여 배수.

> ⚠️ **recreate 가 spool-wedge 를 재발시킨다**: turn 처리 중에 `--force-recreate`/restart 하면 그 turn 의 spool 항목이 stale `.processing` 으로 남아 다음 메시지를 막는다. **config 튜닝 recreate 전에 (1) 진행 중 turn 없음 확인, (2) recreate 후 spool 에 `.processing` 잔재 있으면 즉시 정리.**

### host native 와의 관계

같은 stall 은 host native 게이트웨이의 cron(`gws-assistant-poll`)에서도 `CLI produced no output for 600s` 로 먼저 나타났다(2026-05-19). 다만 native 쪽 1차 완화는 **모델 fallback 이 아니라** run.py 의 무거운 처리량을 600초 한참 아래로 묶는 방식(`POLL_HEAVY_BUDGET`)이었다 — *run 길이* 를 줄여 watchdog 을 안 건드리는 접근. 컨테이너 쪽은 첫 토큰 자체가 stall 하는 케이스라 *재시도(fallback)* 로 잡는다. **같은 근본 원인, 다른 레이어의 처방**임을 기억할 것.

## 트러블슈팅 (요약)

| 증상 | 해결 |
|---|---|
| 봇 `Something went wrong`, 로그에 `write EPIPE` | **install 5단계 PATH fix** 안 됨. `docker exec <gw> claude --version` 으로 확인 |
| 봇 `access not configured` + pairing code | **install 6단계** `pairing approve telegram <code>` |
| 봇 "이메일 도구가 연결돼 있지 않습니다"(gog 는 STEP4 에서 작동하는데도) | **gog STEP 5** ([openclaw-docker-add-gog.md](./openclaw-docker-add-gog.md)) — `USER.md` 의 이메일 ≠ gog 인증 계정. 워크스페이스에 gog 계정 명시 후 `/new`. (`gog --account <틀린계정>` → `OAuth client credentials missing`) |
| 봇 응답 `timed out 180s (no-output stall)` / 무거운 turn 만 간헐 무응답 후 `FailoverError` | [**신뢰성 섹션**](#신뢰성--스트리밍-stall-과-자동-복구-watchdog--model-fallback-) — model fallback + watchdog 한 쌍으로 자동 복구. (근본은 Claude Code 스트리밍 버그, 컨테이너 무관) |
| 봇·`/new` 모두 묵묵부답, webhook pending=0 인데 응답 없음 | stall 이 텔레그램 spool 을 wedge — 신뢰성 섹션 "spool-wedge" 복구 절차 |
| `EACCES /home/node/.openclaw` | `sudo chown -R 1000:1000 ~/.openclaw` |
| 이미지 빌드 OOM (exit 137) | RAM 2GB+ 필요 |
| gog `aes.KeyUnwrap(): integrity check failed` | `GOG_KEYRING_PASSWORD` 가 **gog 키링** 비번과 불일치. gog 키링(`~/.config/gogcli-openclaw-container/keyring`)은 OpenClaw 자체 credentials 와 **별개 비번** — 그 키링을 만든 비번을 줘야 함 |
| `cron list`/`status` 가 `gateway token mismatch` | `--token <gateway.auth.token>` 전달 (위 9a 참조). remote.token 미설정이라 CLI 가 인증 못 함 |
| 브라우저형 스킬(webmail-watch·society-watch) cron 이 게이트웨이서 실패 | 게이트웨이 이미지에 playwright/chromium **없음** — 게이트웨이 cron 대상 아님. **사이드카로 분리**(위 9b 참조) |

> 진단 팁: `OPENCLAW_DEBUG=1 OPENCLAW_CLI_BACKEND_LOG_OUTPUT=1` 를 environment 에 넣어 재생성하면 백엔드 stdout/stderr·`cli argv` 가 로그에 보임.

## 부록 — 왜 봇이 Claude Code 직접 실행보다 느린가

자세한 분석(텔레그램 → 게이트웨이 → claude-cli → API 단계별 프롬프트 누적, 시스템프롬프트 23.5KB·스킬 12.8KB·MCP·이력)은 **[openclaw-skills.md](./openclaw-skills.md) "왜 봇이 느린가"** 절로 이전했습니다.
