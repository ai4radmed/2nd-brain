# OpenClaw 게이트웨이 — Docker 컨테이너 설치 (간결판)

> 붙여넣기용 bash 명령 + 최소 이유만. 자세한 배경·트러블슈팅 상세는 추후 보강.
> 공식 문서: <https://docs.openclaw.ai/install/docker>

**왜 컨테이너**: 호스트에 직접 설치하면 user 권한 그대로라 탈취 시 피해가 크지만, 컨테이너는 피해가 boundary 로 제한됨.

## 이 가이드 사용법 (사용자 / AI 에이전트 공통)

- **설치 형태**: 컨테이너 1개 = **운영(production)** 이 기본. 같은 머신에 **데모용 2번째 컨테이너**를 추가할 수도 있고, *그때만* 포트를 다르게 준다(4단계).
- **AI 에이전트가 대화형으로 진행할 때**:
  1. 전제(아래)부터 점검 — `docker --version` · `docker compose version` · `git --version`.
  2. 사용자에게 확인할 결정: ① 이 컨테이너가 *첫(운영)* 인가 *추가(데모)* 인가 → 포트 결정, ② 인증은 *OAuth(권장)* 인가 *API 키* 인가.
  3. **🧑 사용자 직접 단계**(브라우저·폰 조작, 에이전트가 대신 못 함)에선 멈추고 안내 — Claude OAuth 로그인(3단계)·BotFather 토큰+텔레그램 pairing(6단계)·Control UI(7단계).

## 전제

- **WSL2** + **Docker Engine + Docker Compose v2** + **git**
- **클라우드 AI 구독** (저자: Anthropic Claude Max)
- **Claude Code** (사실상 전제 — skill 워크플로우 + 아래 자격증명 선반입에 사용):
  ```bash
  curl -fsSL https://claude.ai/install.sh | bash
  ```

---

## 1. 저장소 클론

```bash
git clone https://github.com/openclaw/openclaw.git ~/projects/openclaw-docker
```

```bash
cd ~/projects/openclaw-docker
```

## 2. 컨테이너 데이터 폴더 준비

> 컨테이너가 읽고 쓰는 설정·데이터(bind-mount)를 둘 호스트 폴더. **운영(production)은 공식 기본 `~/.openclaw`** 를 그대로 쓴다 — 별도 지정 없이 `docker compose up` 만으로 뜨도록(이게 이 가이드의 핵심). 컨테이너 user `node`(uid 1000) 소유로 맞춘다. (데모용 2번째 컨테이너를 둘 거면 그건 별도 폴더 — 예: `~/.openclaw-demo`.)

```bash
mkdir -p ~/.openclaw/workspace ~/.openclaw/.claude
```

```bash
sudo chown -R 1000:1000 ~/.openclaw
```

## 3. Claude 자격증명 선반입 (OAuth 방식 — setup 전 필수)

> onboarding 은 *기존* claude 자격증명을 재사용하므로, 미리 없으면 `Claude CLI is not authenticated` 로 중단됨. 호스트 `~/.claude` 와 **독립 lineage** 가 되도록 별도 로그인(복사 X — 회전 시 호스트가 로그아웃됨). *API 키 방식이면 이 단계 생략.*
>
> 🧑 **사용자 직접**: `auth login` 은 **브라우저 OAuth 승인**이 필요합니다 — 에이전트는 명령만 실행하고, 출력된 URL 승인은 사용자가 합니다.

호스트에 Claude Code 가 있으면 (간단):

```bash
CLAUDE_CONFIG_DIR="$HOME/.openclaw/.claude" claude auth login
```

없으면 (컨테이너 번들로):

```bash
docker run --rm -it -u node -v ~/.openclaw/.claude:/home/node/.claude \
  --entrypoint /app/node_modules/@anthropic-ai/claude-agent-sdk-linux-x64/claude \
  ghcr.io/openclaw/openclaw:latest auth login
```

확인 (파일 생기면 OK):

```bash
ls -l ~/.openclaw/.claude/.credentials.json
```

## 4. 환경변수 export + 셋업 실행

> `setup.sh` 는 `.env` 가 아니라 **셸 환경변수**를 봄 → 반드시 `export`. (`.claude` 마운트가 토큰을 영속화.)

**운영(production)** — 공식 기본값(`~/.openclaw` + 포트 18789/18790)을 그대로 쓰므로 이미지만 지정:

```bash
export OPENCLAW_IMAGE="ghcr.io/openclaw/openclaw:latest"
```

**데모용 2번째 컨테이너**를 같은 머신에 추가할 때만 — 운영이 `~/.openclaw`·18789 를 점유하므로 — 별도 폴더 + 포트를 재지정:

```bash
export OPENCLAW_IMAGE="ghcr.io/openclaw/openclaw:latest"
export OPENCLAW_CONFIG_DIR=$HOME/.openclaw-demo
export OPENCLAW_WORKSPACE_DIR=$HOME/.openclaw-demo/workspace
export OPENCLAW_EXTRA_MOUNTS="$HOME/.openclaw-demo/.claude:/home/node/.claude"
export OPENCLAW_GATEWAY_PORT=18889   # 호스트 18889→컨테이너 18789
export OPENCLAW_BRIDGE_PORT=18990    # 기본 18790 충돌 방지
```

```bash
./scripts/docker/setup.sh
```

위저드: *personal-by-default* → **Y**, *Setup mode* → **QuickStart**, *Provider* → **Anthropic OAuth (claude-cli)**.

> ⚠️ 출력의 `Config:` 가 의도한 폴더(운영=`/home/<you>/.openclaw`, 데모=`...openclaw-demo`)와 일치해야 정상. `Building ... openclaw:local`(ghcr 이미지 대신 로컬 빌드) 이 보이면 `OPENCLAW_IMAGE` 미전달 → `Ctrl+C` 후 4단계부터 다시.

## 5. PATH fix — 번들 claude 를 PATH 에 노출 (★필수)

> **이거 안 하면 모든 채널 메시지가 `Something went wrong` 으로 실패한다.** 이미지의 claude 가 PATH 에 없어 openclaw 가 bare `claude` 를 spawn 할 때 ENOENT→EPIPE. SDK 경로를 PATH 앞에 붙여 해결. (`.claude` 마운트도 같은 파일에 둠.)

setup.sh 가 만든 `docker-compose.extra.yml` 을 PATH 포함본으로 덮어씀:

```bash
cat > ~/projects/openclaw-docker/docker-compose.extra.yml <<EOF
services:
  openclaw-gateway:
    volumes:
      - $HOME/.openclaw/.claude:/home/node/.claude
    environment:
      - PATH=/app/node_modules/@anthropic-ai/claude-agent-sdk-linux-x64:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
  openclaw-cli:
    volumes:
      - $HOME/.openclaw/.claude:/home/node/.claude
    environment:
      - PATH=/app/node_modules/@anthropic-ai/claude-agent-sdk-linux-x64:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
EOF
```

> 같은 `extra.yml` 에 **gog·vault 마운트**(2nd-brain 통합)를 함께 얹는다 — gog config(`~/.config/gogcli-openclaw-container`), vault(`~/projects/2nd-brain-vault`), `GOG_KEYRING_PASSWORD`·`GMAIL_ROUTER_*` env. 단계별: [openclaw-docker-gog.md](./openclaw-docker-gog.md). (데모 컨테이너면 위 `.claude` 경로를 `~/.openclaw-demo/.claude` 로.)

재생성 + 확인:

```bash
cd ~/projects/openclaw-docker
docker compose -f docker-compose.yml -f docker-compose.extra.yml up -d --force-recreate openclaw-gateway
```

```bash
GW=$(docker ps --filter name=openclaw-gateway --format '{{.Names}}' | head -1)
docker exec "$GW" claude --version   # 2.1.x (Claude Code) 면 OK
```

## 6. 텔레그램 봇 추가 (초기 설정에서 함께)

> 봇 토큰은 대시보드가 아니라 CLI 로 등록. 포트 함정 회피 위해 게이트웨이 컨테이너 안에서 내부 포트(18789)로 실행.
>
> 🧑 **사용자 직접**: @BotFather 봇 생성·토큰 발급, 그리고 아래 pairing 을 위한 텔레그램 메시지 전송은 사용자가 합니다 (에이전트는 토큰을 받아 명령 실행).

@BotFather 에서 `/newbot` 으로 토큰 발급 후:

```bash
GW=$(docker ps --filter name=openclaw-gateway --format '{{.Names}}' | head -1)
docker exec -e OPENCLAW_GATEWAY_PORT=18789 "$GW" \
  node dist/index.js channels add --channel telegram --token "<봇토큰>"
```

텔레그램에서 봇에게 메시지를 보내면 `access not configured` + **pairing code** 가 옴. 그 코드로 승인:

```bash
docker exec -e OPENCLAW_GATEWAY_PORT=18789 "$GW" \
  node dist/index.js pairing approve telegram <PAIRING_CODE>
```

이후 봇에 다시 메시지 → 정상 응답.

## 7. Control UI 접속

브라우저에서 `http://127.0.0.1:18789/`(데모/추가 컨테이너면 `:18889`) 열고 `.env` 의 `OPENCLAW_GATEWAY_TOKEN` 붙여넣기. 토큰 박힌 URL 재발급:

```bash
docker compose -f docker-compose.yml -f docker-compose.extra.yml run --rm openclaw-cli dashboard --no-open
```

브라우저도 device 페어링이 필요하면 `access not configured` 대신 requestId 가 뜸 → `... devices approve <requestId>` (exec 방식, 6단계와 동일).

## 8. 운영

```bash
curl -fsS http://127.0.0.1:18789/healthz      # 데모/추가 컨테이너면 :18889
```

```bash
cd ~/projects/openclaw-docker
docker compose -f docker-compose.yml -f docker-compose.extra.yml logs -f openclaw-gateway   # 로그
docker compose -f docker-compose.yml -f docker-compose.extra.yml down                        # 정지
docker compose -f docker-compose.yml -f docker-compose.extra.yml up -d openclaw-gateway       # 재기동
```

> ⚠️ **모든 `docker compose` 명령에 `-f docker-compose.yml -f docker-compose.extra.yml` 를 항상 함께** 줄 것 (extra.yml = PATH fix + .claude 마운트). 빠지면 기본값으로 recreate 되며 깨짐.

## 9. 스킬·cron — 무인 자동화 (게이트웨이 cron vs 사이드카)

스킬을 무인 주기 실행하려면 **그 스킬이 브라우저를 쓰는지**에 따라 거처가 갈린다. 게이트웨이 컨테이너(ghcr 이미지)에는 **playwright/chromium 이 없다** — 그래서:

| 스킬 유형 | 예 | 무인 거처 |
|---|---|---|
| **텍스트형**(gog API·LLM, 브라우저 X) | `gmail-label-actions`(라벨→GWS 후속작업), `gws-assistant` | **게이트웨이 cron** (컨테이너 안) |
| **브라우저형**(playwright headed) | `webmail-watch`(anti-headless SPA), `society-watch` | **별도 headed-Xvfb 사이드카** + host 스케줄러 |

### 9a. 게이트웨이 cron — gmail-label-actions (무인 메일 처리)

라벨(1~8) 단 메일을 Calendar/Tasks/Drafts 후속작업으로 완결·캡처. 브라우저 비의존이라 게이트웨이 cron 에서 안전. `~/.openclaw/cron/jobs.json` 에 잡 추가:

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

반영(8단계 recreate) 후 검증 — **cron CLI 는 게이트웨이 토큰 필요**:

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

---

## 초기 설정 시 반드시 검토 (모델·watchdog·하트비트·thinking)

설치 직후 *반드시* 한 번 결정해야 응답이 느리거나 멈추지 않습니다 (저자 실측: 단순 gog 작업 sonnet 18~34초 → **haiku 6.5초**. 측정 근거는 [openclaw-skills.md](./openclaw-skills.md) "응답 속도 최적화").

**1. 작업에 맞는 모델** — 기계적 작업(메일·일정·할일·검색)은 `haiku-4-5`, 복잡 추론(지저분한 메일에서 날짜 추출 등)만 `sonnet`/`opus`.
```bash
python3 - <<'PY'
import json, pathlib
f = pathlib.Path.home()/".openclaw/openclaw.json"
d = json.loads(f.read_text())
d["agents"]["defaults"]["model"]["primary"] = "anthropic/claude-haiku-4-5"  # 추론 필요시 sonnet-4-6
d["agents"]["defaults"]["heartbeat"] = {"every": "0m"}                       # 3번 하트비트 off
f.write_text(json.dumps(d, indent=2, ensure_ascii=False)); print("ok")
PY
```
적용: 5단계의 `--force-recreate`. 로그에 `agent model: ...haiku-4-5` + `[heartbeat] disabled` 확인.

**2. watchdog ↔ 연결(다단계) 작업** — 게이트웨이는 **180초간 출력 없으면 turn 을 강제 종료**합니다(no-output watchdog). 여러 단계·여러 항목을 한 프롬프트에 몰면 걸려 죽습니다. → **단계별로 쪼개고**, 프롬프트에 **"각 처리마다 한 줄씩 회신"** 을 넣어 *중간 출력이 흘러 타이머가 리셋* 되게 합니다. 첫 토큰 자체가 stall 하는 간헐 무응답(스트리밍 버그)은 프롬프트로 못 막으니 **[신뢰성 섹션](#신뢰성--스트리밍-stall-과-자동-복구-watchdog--model-fallback-)의 watchdog+fallback 한 쌍**으로 자동 복구시키세요.

**3. 하트비트** — 주기적 self-run 이 불필요하면 끄기 (위 1번 코드에 `heartbeat.every="0m"` 포함). 동시 세션·비용 절감.

**4. think mode** — `haiku` 는 기본 thinking 으로 충분히 빠릅니다. ⚠️ `agents.defaults.thinking` 을 직접 넣으면 **config 검증 오류로 게이트웨이가 crash-loop** 합니다(저자 실측). thinking 을 굳이 낮추려면 모델 스펙 문법이 필요하니, 보통은 **모델 선택(1번)으로 대체**하세요.

> ⚠️ **위임 함정**: 다단계 작업 프롬프트에 *"백그라운드·하위 에이전트로 위임하지 말고 이 턴에서 직접 실행"* 을 안 넣으면, 봇이 detached 워커로 분리해 **결과가 안 돌아올 수 있습니다**(고아 run). 위임 금지를 명시하세요.

---

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

적용: 5단계의 `--force-recreate`. 게이트웨이 healthy + 일반 turn 정상 회신 확인.

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

---

## (선택) gog — Google Workspace (Gmail·Calendar·Tasks)

봇이 Gmail·Calendar·Drive·Tasks 등을 다루려면 gog CLI 를 컨테이너에 붙입니다. gog 는 정적 단일 바이너리라 browser 와 달리 시스템 deps 없이 됩니다.

→ 단계별 설치(STEP 1~6 — 검증 게이트 + 계정 불일치 함정 회피): **[openclaw-docker-gog.md](./openclaw-docker-gog.md)**

## 트러블슈팅 (요약)

| 증상 | 해결 |
|---|---|
| 봇 `Something went wrong`, 로그에 `write EPIPE` | **5단계 PATH fix** 안 됨. `docker exec <gw> claude --version` 으로 확인 |
| 봇 `access not configured` + pairing code | **6단계** `pairing approve telegram <code>` |
| 봇 "이메일 도구가 연결돼 있지 않습니다"(gog 는 STEP4 에서 작동하는데도) | **gog STEP 5** — `USER.md` 의 이메일 ≠ gog 인증 계정. 워크스페이스에 gog 계정 명시 후 `/new`. (`gog --account <틀린계정>` → `OAuth client credentials missing`) |
| 봇 응답 `timed out 180s (no-output stall)` / 무거운 turn 만 간헐 무응답 후 `FailoverError` | [**신뢰성 섹션**](#신뢰성--스트리밍-stall-과-자동-복구-watchdog--model-fallback-) — model fallback + watchdog 한 쌍으로 자동 복구. (근본은 Claude Code 스트리밍 버그, 컨테이너 무관) |
| 봇·`/new` 모두 묵묵부답, webhook pending=0 인데 응답 없음 | stall 이 텔레그램 spool 을 wedge — 신뢰성 섹션 "spool-wedge" 복구 절차 |
| CLI 가 `gateway closed (1006)` (추가 컨테이너 병행 시) | `docker compose run` 대신 `docker exec -e OPENCLAW_GATEWAY_PORT=18789 "$GW" node dist/index.js <cmd>` |
| 컨테이너 `address already in use :18789` (추가 컨테이너 병행 시) | 4단계 `OPENCLAW_GATEWAY_PORT`/`OPENCLAW_BRIDGE_PORT` 재지정 후 재시도 |
| `EACCES /home/node/.openclaw` | `sudo chown -R 1000:1000 ~/.openclaw` (데모면 `~/.openclaw-demo`) |
| 이미지 빌드 OOM (exit 137) | RAM 2GB+ 필요 |
| gog `aes.KeyUnwrap(): integrity check failed` | `GOG_KEYRING_PASSWORD` 가 **gog 키링** 비번과 불일치. gog 키링(`~/.config/gogcli-openclaw-container/keyring`)은 OpenClaw 자체 credentials 와 **별개 비번** — 그 키링을 만든 비번을 줘야 함 |
| `cron list`/`status` 가 `gateway token mismatch` | `--token <gateway.auth.token>` 전달 (9a 참조). remote.token 미설정이라 CLI 가 인증 못 함 |
| 브라우저형 스킬(webmail-watch·society-watch) cron 이 게이트웨이서 실패 | 게이트웨이 이미지에 playwright/chromium **없음** — 게이트웨이 cron 대상 아님. **사이드카로 분리**(9b 참조) |

> 진단 팁: `OPENCLAW_DEBUG=1 OPENCLAW_CLI_BACKEND_LOG_OUTPUT=1` 를 environment 에 넣어 재생성하면 백엔드 stdout/stderr·`cli argv` 가 로그에 보임.

## 부록 — 왜 Claude Code 직접 실행보다 느린가 (단계별 프롬프트 누적)

봇 응답이 Claude Code 를 터미널에서 직접 쓰는 것보다 느린 건 **컨테이너 때문이 아니라**(Docker 오버헤드는 무시 가능), 메시지가 `텔레그램 → 게이트웨이 → claude-cli → API` 로 가며 **단계마다 처리할 양이 누적**되기 때문입니다. 이 설치 기준 실측:

### ① 텔레그램 → 게이트웨이
사용자 원문(수~수십 자) + 채널·발신자 메타만. **미미함.**

### ② 게이트웨이 → claude-cli 호출 (여기서 폭증)
게이트웨이가 그 짧은 메시지를 무거운 claude 호출로 감싸며 아래를 붙입니다:

| 항목 | 주입 방식 | 실측 | 비고 |
|---|---|---|---|
| 시스템 프롬프트 | `--append-system-prompt-file` | **~23.5KB** | openclaw 운영지침 + 워크스페이스 파일(AGENTS.md 7.8KB·SOUL.md·IDENTITY/USER/TOOLS/HEARTBEAT) 통째. **첫 턴만** |
| 스킬 | `--plugin-dir` | **~12.8KB** | 스킬 정의 묶음 |
| MCP 도구 | `--mcp-config` (528B) | 서버서 스키마 로드 | openclaw MCP 서버 연결 → `mcp__openclaw__*` 도구 스키마가 컨텍스트로 들어옴 |
| 대화 이력 | `--resume <session>` | 누적↑ | 직전까지 전체 대화 (턴마다 증가) |
| 확장 thinking | `--effort medium` | — | 추론 토큰·지연↑, partial 미스트림 |

### ③ claude-cli → Anthropic API
claude 가 자기 baseline 을 더함 (Claude Code 와 동일분이라 *openclaw 의 추가 부담은 아님*): Claude Code 자체 시스템 프롬프트 + 내장 도구 ~50개 정의(Bash/Read/Edit/…). ②의 항목들과 합쳐져 **매 API 호출의 입력 컨텍스트**가 됩니다.

> **결과**: `"안녕"`(6 byte) 한 줄이 claude 가 실제 받는 입력으로는 **시스템프롬프트 23.5KB + 스킬 12.8KB + MCP 도구 스키마 + 내장 도구정의 + 누적 이력 = 수만 토큰**이 됩니다 (첫 턴 기준).

### 왜 느림·stall 로 이어지나
- 입력 토큰이 크면 **첫 토큰까지 시간(TTFT)↑**.
- `--effort medium` thinking 은 partial 이 안 흘러 게이트웨이엔 "출력 없음"으로 보임 → **180s no-output watchdog** 위험.
- 매 턴 temp 파일 작성 + MCP 연결 = **~10초 전처리**(로그의 `Inbound`→`cli exec` 간격).
- Claude Code(대화형)는 이 컨텍스트를 한 번 warm 하게 올려 재사용 + prompt caching 으로 가볍지만, 봇은 메시지마다 서브프로세스로 다시 조립.

### 완화 (일부는 위 튜닝에서 적용)
- **가벼운 모델**(sonnet/haiku) + **하트비트 off** — 시스템 프롬프트의 Heartbeat 섹션·주기 실행 제거.
- **스킬 최소화**(12.8KB↓), **워크스페이스 파일 슬림화**(AGENTS.md 7.8KB 등 → 시스템 프롬프트↓).
- 연속 대화는 **2번째 턴부터 resume + prompt cache** 로 가벼워짐 (첫 턴이 가장 무거움).

> 요점: **컨테이너화는 속도와 무관.** 느림의 본질은 게이트웨이가 매 턴 붙이는 *시스템프롬프트·스킬·MCP·이력의 누적*이며, 호스트에서 직접 돌려도 동일하다.

## 다음 단계

- 최초 구동 시 쓸 수 있는 기본 스킬: [openclaw-skills.md](./openclaw-skills.md)
- 공식 문서: <https://docs.openclaw.ai/install/docker>
