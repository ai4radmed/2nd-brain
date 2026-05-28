# OpenClaw Docker 설치
- **Why?**: 호스트에 직접 설치하면 user 권한 그대로라 탈취 시 피해가 크지만, 컨테이너는 피해가 boundary 로 제한됨.   
- OpenClaw에서 제공하는 docker 설치 (<https://docs.openclaw.ai/install/docker>)와는 달리 저자는 Claude Code CLI를 OAuth로 설치하기 위해서 아래와 같이 변경하여 진행함

## 1. 저장소 클론
```bash
git clone --branch v2026.5.20 https://github.com/openclaw/openclaw.git ~/projects/openclaw-docker
```
- 2026.05.27 기준 최신 이미지에 Claude Code CLI가 없어 2026.05.20 버전으로 고정함   
- `setup.sh`·`docker-compose.yml`와 이미지(`OPENCLAW_IMAGE`)는 **같은 버전이어야**  함.

```bash
cd ~/projects/openclaw-docker
```

## 2. 컨테이너 데이터 폴더 준비

- OpenClaw 컨테이너가 사용할(=mount) 폴더는 WSL(=host)에 미리 생성해야 함
```bash
mkdir -p ~/.openclaw/workspace ~/.openclaw/.claude
```
- 컨테이너 user `node`(uid 1000) 소유로 맞춘다.
```bash
sudo chown -R 1000:1000 ~/.openclaw
```

## 3. Claude 자격증명 선반입 (OAuth 방식 — setup 전 필수)
- Claude Code OAuth 토큰을 #2에서 미리 준비한 폴더에 추가로 발급받아 저장
```bash
CLAUDE_CONFIG_DIR="$HOME/.openclaw/.claude" claude auth login
```


## 4. 환경변수 export + 셋업 실행
- 사용할 OpenClaw 이미지를 #1에서 지정한 것과 같도록 선언   
- 컨테이너 내부에서 Claude Code를 인식할 수 있도록 환경변수 선언
```bash
export OPENCLAW_IMAGE="ghcr.io/openclaw/openclaw:2026.5.20"
export OPENCLAW_EXTRA_MOUNTS="$HOME/.openclaw/.claude:/home/node/.claude"
```

```bash
./scripts/docker/setup.sh
```
- OpenClaw 초기설정
   - *personal-by-default* → **Y**
   - *Setup mode* → **QuickStart**
   - *Provider* → **Anthropic OAuth (claude-cli)**
   - 나머지는 skip 하고 나중에 설정 진행

## 5. PATH fix — 번들 claude 를 PATH 에 노출 (★필수)
- 설정이 완료된 후 컨테이너 내부에서 Claude code를 PATH에 등록
- setup.sh 가 만든 `docker-compose.extra.yml` 을 PATH 포함본으로 덮어씀:

```bash
cat > ~/projects/openclaw-docker/docker-compose.extra.yml <<EOF
services:
  openclaw-gateway:
    container_name: 2nd-brain-openclaw-gateway
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

## 7. 운영

```bash
curl -fsS http://127.0.0.1:18789/healthz
```

```bash
cd ~/projects/openclaw-docker
docker compose -f docker-compose.yml -f docker-compose.extra.yml logs -f openclaw-gateway   # 로그
docker compose -f docker-compose.yml -f docker-compose.extra.yml down                        # 정지
docker compose -f docker-compose.yml -f docker-compose.extra.yml up -d openclaw-gateway       # 재기동
```

> ⚠️ **모든 `docker compose` 명령에 `-f docker-compose.yml -f docker-compose.extra.yml` 를 항상 함께** 줄 것 (extra.yml = PATH fix + .claude 마운트). 빠지면 기본값으로 recreate 되며 깨짐.

---

## 초기 설정 시 반드시 검토 (모델·하트비트·thinking)

설치 직후 *반드시* 한 번 결정해야 응답이 느리거나 멈추지 않습니다 (저자 실측: 단순 gog 작업 sonnet 18~34초 → **haiku 6.5초**. 측정 근거는 [openclaw-skills.md](./openclaw-skills.md) "왜 느린가").

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

**2. watchdog ↔ 연결(다단계) 작업** — 게이트웨이는 **180초간 출력 없으면 turn 을 강제 종료**합니다(no-output watchdog). 여러 단계·여러 항목을 한 프롬프트에 몰면 걸려 죽습니다. → **단계별로 쪼개고**, 프롬프트에 **"각 처리마다 한 줄씩 회신"** 을 넣어 *중간 출력이 흘러 타이머가 리셋* 되게 합니다. 첫 토큰 자체가 stall 하는 간헐 무응답(스트리밍 버그)은 프롬프트로 못 막으니 **[openclaw-docker-operations.md](./openclaw-docker-operations.md) 의 신뢰성 섹션(watchdog+fallback)** 으로 자동 복구시키세요.

**3. 하트비트** — 주기적 self-run 이 불필요하면 끄기 (위 1번 코드에 `heartbeat.every="0m"` 포함). 동시 세션·비용 절감.

**4. think mode** — `haiku` 는 기본 thinking 으로 충분히 빠릅니다. ⚠️ `agents.defaults.thinking` 을 직접 넣으면 **config 검증 오류로 게이트웨이가 crash-loop** 합니다(저자 실측). thinking 을 굳이 낮추려면 모델 스펙 문법이 필요하니, 보통은 **모델 선택(1번)으로 대체**하세요.

> ⚠️ **위임 함정**: 다단계 작업 프롬프트에 *"백그라운드·하위 에이전트로 위임하지 말고 이 턴에서 직접 실행"* 을 안 넣으면, 봇이 detached 워커로 분리해 **결과가 안 돌아올 수 있습니다**(고아 run). 위임 금지를 명시하세요.

## 다음 단계

- 최초 구동 시 쓸 수 있는 기본 스킬·능력·속도: [openclaw-skills.md](./openclaw-skills.md)
- (선택) gog 로 Google Workspace(Gmail·Calendar·Tasks) 연계: [openclaw-docker-add-gog.md](./openclaw-docker-add-gog.md)
- 운영 심화 — Control UI(로컬 대시보드)·무인 자동화(cron·사이드카)·신뢰성(stall 자동복구)·트러블슈팅: [openclaw-docker-operations.md](./openclaw-docker-operations.md)
- 공식 문서: <https://docs.openclaw.ai/install/docker>
