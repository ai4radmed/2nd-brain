# OpenClaw 게이트웨이 — Docker 컨테이너 설치 (간결판)

> 붙여넣기용 bash 명령 + 최소 이유만. 자세한 배경·트러블슈팅 상세는 추후 보강.
> 공식 문서: <https://docs.openclaw.ai/install/docker>

**왜 컨테이너**: native 설치는 호스트 user 권한 그대로라 탈취 시 피해가 크지만, 컨테이너는 피해가 boundary 로 제한됨.

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

## 2. 컨테이너 전용 폴더 (native `~/.openclaw` 와 분리)

> 별도 폴더라야 native 설정·메모리를 안 건드림. 컨테이너 user `node`(uid 1000) 소유로 맞춤.

```bash
mkdir -p ~/.openclaw-docker/workspace ~/.openclaw-docker/.claude
```

```bash
sudo chown -R 1000:1000 ~/.openclaw-docker
```

## 3. Claude 자격증명 선반입 (OAuth 방식 — setup 전 필수)

> onboarding 은 *기존* claude 자격증명을 재사용하므로, 미리 없으면 `Claude CLI is not authenticated` 로 중단됨. 호스트 `~/.claude` 와 **독립 lineage** 가 되도록 별도 로그인(복사 X — 회전 시 호스트가 로그아웃됨). *API 키 방식이면 이 단계 생략.*

호스트에 Claude Code 가 있으면 (간단):

```bash
CLAUDE_CONFIG_DIR="$HOME/.openclaw-docker/.claude" claude auth login
```

없으면 (컨테이너 번들로):

```bash
docker run --rm -it -u node -v ~/.openclaw-docker/.claude:/home/node/.claude \
  --entrypoint /app/node_modules/@anthropic-ai/claude-agent-sdk-linux-x64/claude \
  ghcr.io/openclaw/openclaw:latest auth login
```

확인 (파일 생기면 OK):

```bash
ls -l ~/.openclaw-docker/.claude/.credentials.json
```

## 4. 환경변수 export + 셋업 실행

> `setup.sh` 는 `.env` 가 아니라 **셸 환경변수**를 봄 → 반드시 `export`. (`.claude` 마운트가 토큰을 영속화.)

```bash
export OPENCLAW_IMAGE="ghcr.io/openclaw/openclaw:latest"
export OPENCLAW_CONFIG_DIR=$HOME/.openclaw-docker
export OPENCLAW_WORKSPACE_DIR=$HOME/.openclaw-docker/workspace
export OPENCLAW_EXTRA_MOUNTS="$HOME/.openclaw-docker/.claude:/home/node/.claude"
```

native 와 **병행 설치**면 포트도 재지정 (기본 설치는 생략):

```bash
export OPENCLAW_GATEWAY_PORT=18889   # 호스트 18889→컨테이너 18789
export OPENCLAW_BRIDGE_PORT=18990    # 기본 18790 충돌 방지
```

```bash
./scripts/docker/setup.sh
```

위저드: *personal-by-default* → **Y**, *Setup mode* → **QuickStart**, *Provider* → **Anthropic OAuth (claude-cli)**.

> ⚠️ 출력에 `Config: /home/<you>/.openclaw-docker` 가 보여야 정상. `~/.openclaw`(native) 나 `Building ... openclaw:local` 이 보이면 env 미전달 → `Ctrl+C` 후 4단계부터 다시.

## 5. PATH fix — 번들 claude 를 PATH 에 노출 (★필수)

> **이거 안 하면 모든 채널 메시지가 `Something went wrong` 으로 실패한다.** 이미지의 claude 가 PATH 에 없어 openclaw 가 bare `claude` 를 spawn 할 때 ENOENT→EPIPE. SDK 경로를 PATH 앞에 붙여 해결. (`.claude` 마운트도 같은 파일에 둠.)

setup.sh 가 만든 `docker-compose.extra.yml` 을 PATH 포함본으로 덮어씀:

```bash
cat > ~/projects/openclaw-docker/docker-compose.extra.yml <<EOF
services:
  openclaw-gateway:
    volumes:
      - $HOME/.openclaw-docker/.claude:/home/node/.claude
    environment:
      - PATH=/app/node_modules/@anthropic-ai/claude-agent-sdk-linux-x64:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
  openclaw-cli:
    volumes:
      - $HOME/.openclaw-docker/.claude:/home/node/.claude
    environment:
      - PATH=/app/node_modules/@anthropic-ai/claude-agent-sdk-linux-x64:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
EOF
```

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

브라우저에서 `http://127.0.0.1:18789/`(병행 설치면 `:18889`) 열고 `.env` 의 `OPENCLAW_GATEWAY_TOKEN` 붙여넣기. 토큰 박힌 URL 재발급:

```bash
docker compose -f docker-compose.yml -f docker-compose.extra.yml run --rm openclaw-cli dashboard --no-open
```

브라우저도 device 페어링이 필요하면 `access not configured` 대신 requestId 가 뜸 → `... devices approve <requestId>` (exec 방식, 6단계와 동일).

## 8. 운영

```bash
curl -fsS http://127.0.0.1:18789/healthz      # 병행이면 :18889
```

```bash
cd ~/projects/openclaw-docker
docker compose -f docker-compose.yml -f docker-compose.extra.yml logs -f openclaw-gateway   # 로그
docker compose -f docker-compose.yml -f docker-compose.extra.yml down                        # 정지
docker compose -f docker-compose.yml -f docker-compose.extra.yml up -d openclaw-gateway       # 재기동
```

> ⚠️ **모든 `docker compose` 명령에 `-f docker-compose.yml -f docker-compose.extra.yml` 를 항상 함께** 줄 것 (extra.yml = PATH fix + .claude 마운트). 빠지면 기본값으로 recreate 되며 깨짐.

---

## (선택) 응답 속도·비용 튜닝

> opus + thinking + 누적 컨텍스트가 무거우면 첫 출력까지 180s 를 넘겨 watchdog 이 죽임(`no-output stall`). 데모·경량 용도면 가벼운 모델 + 하트비트 off 로 3~10초대.

```bash
python3 - <<'PY'
import json, pathlib
f = pathlib.Path.home()/".openclaw-docker/openclaw.json"
d = json.loads(f.read_text())
d["agents"]["defaults"]["model"]["primary"] = "anthropic/claude-sonnet-4-6"  # 또는 haiku-4-5
d["agents"]["defaults"]["heartbeat"] = {"every": "0m"}                       # 하트비트 끔
f.write_text(json.dumps(d, indent=2, ensure_ascii=False)); print("ok")
PY
```

적용: 5단계의 `--force-recreate` 재생성. 로그에 `agent model: ...sonnet-4-6` + `[heartbeat] disabled` 확인.

---

## (선택) gog 붙이기 — Google Workspace (Gmail·Calendar·Tasks)

gog 스킬은 번들돼 있지만 **gog 바이너리·인증이 따로 필요**합니다(대시보드 활성화는 brew 설치라 컨테이너에선 실패). gog 는 **정적 단일 바이너리**라 browser 와 달리 시스템 deps 없이 됩니다.

> ⚠️ **반드시 한 단계씩, 각 STEP 의 _검증_ 이 통과한 뒤 다음으로.** 한꺼번에 바꾸면 실패 시 원인 추적이 불가능합니다(저자 실측 교훈 — browser 설정에서 겪음).

**전제 (gog 자체 인증)**: 호스트에 gog 가 설치되어 있고, **컨테이너 전용 OAuth 클라이언트**로 인증된 격리 config 디렉토리가 있어야 합니다. gog 설치·Google OAuth(GCP 프로젝트/클라이언트) 는 <https://gogcli.sh> 참조. native gog 와 **병행**하려면 별도 `--client` 로 인증해 토큰을 분리하세요:
> ```bash
> gog auth credentials set <client_secret.json> --client openclaw-container
> gog auth add <account@gmail.com> --client openclaw-container   # 브라우저 OAuth (대화형)
> ```
> 결과 config 디렉토리: `~/.config/gogcli-openclaw-container/`, keyring 암호: 안전한 곳에 보관(아래 `GOG_KEYRING_PASSWORD`).

---

### STEP 1 — gog 바이너리를 마운트 경로에 복사
`~/.openclaw-docker` 는 컨테이너의 `/home/node/.openclaw` 로 마운트되므로, 그 아래 `bin/` 에 두면 컨테이너에서 보입니다.
```bash
mkdir -p ~/.openclaw-docker/bin
cp "$(command -v gog)" ~/.openclaw-docker/bin/gog && chmod +x ~/.openclaw-docker/bin/gog
```
**✅ 검증** (정적 바이너리 + 호스트에 존재):
```bash
file ~/.openclaw-docker/bin/gog   # "statically linked" 포함해야 함
```

### STEP 2 — 인증이 살아있는지 *먼저* 확인 (컨테이너 건드리기 전)
gog 는 `~/.config/gogcli` 를 읽으므로, HOME 을 임시로 격리 dir 로 돌려 격리 config 의 인증만 점검합니다(호스트 메인 gog 무손상):
```bash
T=$(mktemp -d); mkdir -p "$T/.config"; ln -s ~/.config/gogcli-openclaw-container "$T/.config/gogcli"
HOME="$T" GOG_KEYRING_PASSWORD='<keyring-암호>' gog auth list --client openclaw-container; rm -rf "$T"
```
**✅ 검증**: 계정(`<account@gmail.com>`)이 목록에 나오면 인증 정상.
**❌ 실패 시**(키링 복호화 오류·빈 목록): 컨테이너로 가기 전에 먼저 `gog auth add … --client openclaw-container` 로 **재인증**(별도 client 라 호스트 메인 무손상). 여기서 막히면 다음 STEP 으로 가지 마세요.

### STEP 3 — 키링 암호를 `.env` 에 + extra.yml 에 마운트·PATH·env 추가
```bash
echo "GOG_KEYRING_PASSWORD=<keyring-암호>" >> ~/projects/openclaw-docker/.env
```
`docker-compose.extra.yml` 을 **gog 추가본**으로 덮어씁니다(기존 claude PATH-fix 포함):
```bash
cat > ~/projects/openclaw-docker/docker-compose.extra.yml <<EOF
services:
  openclaw-gateway:
    volumes:
      - $HOME/.openclaw-docker/.claude:/home/node/.claude
      - $HOME/.config/gogcli-openclaw-container:/home/node/.config/gogcli
    environment:
      - PATH=/home/node/.openclaw/bin:/app/node_modules/@anthropic-ai/claude-agent-sdk-linux-x64:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
      - GOG_KEYRING_PASSWORD=\${GOG_KEYRING_PASSWORD}
  openclaw-cli:
    volumes:
      - $HOME/.openclaw-docker/.claude:/home/node/.claude
      - $HOME/.config/gogcli-openclaw-container:/home/node/.config/gogcli
    environment:
      - PATH=/home/node/.openclaw/bin:/app/node_modules/@anthropic-ai/claude-agent-sdk-linux-x64:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
      - GOG_KEYRING_PASSWORD=\${GOG_KEYRING_PASSWORD}
EOF
```
재생성:
```bash
cd ~/projects/openclaw-docker
docker compose -f docker-compose.yml -f docker-compose.extra.yml up -d --force-recreate openclaw-gateway
```
**✅ 검증** (바이너리·config·env 가 컨테이너에 도달):
```bash
GW=$(docker ps --filter name=openclaw-gateway --format '{{.Names}}' | head -1)
docker exec "$GW" which gog          # /home/node/.openclaw/bin/gog
docker exec "$GW" gog --version      # v0.13.0 (rc=0)
docker exec "$GW" ls /home/node/.config/gogcli   # client_secret.json·keyring 등 보임
docker exec "$GW" sh -c 'echo "${GOG_KEYRING_PASSWORD:+set}"'   # "set" 출력
```

### STEP 4 — 컨테이너 *안* 에서 gog 인증·실제 API 검증
```bash
docker exec "$GW" gog auth list                       # 계정 보이면 키링 복호화 OK
docker exec "$GW" gog gmail search --query 'newer_than:1d' --account <account@gmail.com> -j --max 1
```
**✅ 검증**: `auth list` 에 계정이 나오고, gmail 검색이 `rc=0` + JSON 결과면 **실제 Google API 호출 성공**.
**❌ `:ro` 관련 쓰기 오류**가 나면 extra.yml 의 `gogcli` 마운트에 붙은 `:ro` 를 제거(RW)하고 재생성 — 토큰 갱신 쓰기가 필요한 경우입니다. (보안 강화로 `:ro` 를 원하면 RW 로 한 번 토큰 갱신 후 다시 `:ro` 로.)

### STEP 5 — 워크스페이스에 gog 계정 명시 (★계정 불일치 함정 회피)

> ⚠️ **이 단계를 빠뜨리면 STEP 4 에서 gog 가 멀쩡히 작동해도, 봇은 "이메일에 접근할 수 있는 도구가 연결되어 있지 않습니다" 로 답합니다 (저자 실측).** 원인: 봇은 워크스페이스 신원 파일 `USER.md` 에 적힌 *사용자 이메일* 로 gog 를 호출하는데, 그 이메일이 **gog 인증 계정과 다르면** gog 가 `OAuth client credentials missing` 으로 실패 → 봇은 "도구 없음" 으로 결론냅니다. (개인 페르소나 이메일 ≠ gog 인증 계정인 경우 특히 발생.)

봇 워크스페이스(`~/.openclaw-docker/workspace/USER.md`)에 **gog 인증 계정**을 명시해, 봇이 올바른 계정으로 호출하게 합니다:

```bash
cat >> ~/.openclaw-docker/workspace/USER.md <<'EOF'

## Google Workspace (gog)
- gog 인증 계정: <account@gmail.com>   ← gog config 의 account_clients 와 동일해야 함
- gog 호출 시 `--account` 를 생략(기본값 사용)하거나 위 계정을 사용. 다른 이메일로는 호출하지 말 것(미인증 → 실패).
EOF
```
**✅ 검증**: USER.md 에 적은 계정이 gog 기본 계정과 같은지 대조:
```bash
GW=$(docker ps --filter name=openclaw-gateway --format '{{.Names}}' | head -1)
docker exec "$GW" sh -c 'cat /home/node/.config/gogcli/config.json'   # account_clients 의 계정 = USER.md 의 계정
```

### STEP 6 — 스킬·봇 최종 확인
```bash
docker exec -e OPENCLAW_GATEWAY_PORT=18789 "$GW" node dist/index.js skills list 2>&1 | grep -i gog
```
**✅ 검증**: gog 가 `ready`. 텔레그램에서 **`/new`**(워크스페이스 변경 반영) 후:
```
내 메일 최근 5개 제목 알려줘
```
봇이 gog 로 실제 Gmail 을 읽어 답하면 **end-to-end 완료**.

> 💡 **`/new` 필수** — 워크스페이스 파일(USER.md)은 *새 세션 첫 턴* 에 주입됩니다. 기존 대화 그대로면 STEP 5 변경이 반영 안 돼 계속 실패합니다.

## 트러블슈팅 (요약)

| 증상 | 해결 |
|---|---|
| 봇 `Something went wrong`, 로그에 `write EPIPE` | **5단계 PATH fix** 안 됨. `docker exec <gw> claude --version` 으로 확인 |
| 봇 `access not configured` + pairing code | **6단계** `pairing approve telegram <code>` |
| 봇 "이메일 도구가 연결돼 있지 않습니다"(gog 는 STEP4 에서 작동하는데도) | **gog STEP 5** — `USER.md` 의 이메일 ≠ gog 인증 계정. 워크스페이스에 gog 계정 명시 후 `/new`. (`gog --account <틀린계정>` → `OAuth client credentials missing`) |
| 봇 응답 `timed out 180s (no-output stall)` | 위 **튜닝**(가벼운 모델/heartbeat off) 또는 `cliBackends.<rt>.noOutputTimeoutMs` 상향 |
| CLI 가 `gateway closed (1006)` (병행 설치) | `docker compose run` 대신 `docker exec -e OPENCLAW_GATEWAY_PORT=18789 "$GW" node dist/index.js <cmd>` |
| 컨테이너 `address already in use :18789` (병행) | 4단계 `OPENCLAW_GATEWAY_PORT`/`OPENCLAW_BRIDGE_PORT` 재지정 후 재시도 |
| `EACCES /home/node/.openclaw` | `sudo chown -R 1000:1000 ~/.openclaw-docker` |
| 이미지 빌드 OOM (exit 137) | RAM 2GB+ 필요 |

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

> 요점: **컨테이너화는 속도와 무관.** 느림의 본질은 게이트웨이가 매 턴 붙이는 *시스템프롬프트·스킬·MCP·이력의 누적*이며, native 설치로 바꿔도 동일하다.

## 다음 단계

- 최초 구동 시 쓸 수 있는 기본 스킬: [openclaw-skills.md](./openclaw-skills.md)
- native 절차: [openclaw-native.md](./openclaw-native.md)
- 공식 문서: <https://docs.openclaw.ai/install/docker>
