# OpenClaw Docker 컨테이너에 gog 붙이기 — Google Workspace (Gmail·Calendar·Tasks)

> [openclaw-docker-container.md](./openclaw-docker-container.md) 로 컨테이너 설치를 마친 뒤 진행하는 **선택** 단계입니다. gog 를 붙이면 봇이 Gmail·Calendar·Drive·Tasks·Docs·Sheets 를 다룰 수 있습니다. (능력 범위·한계는 [openclaw-skills.md](./openclaw-skills.md) 참조)

gog 스킬은 번들돼 있지만 **gog 바이너리·인증이 따로 필요**합니다(대시보드 활성화는 brew 설치라 컨테이너에선 실패). gog 는 **정적 단일 바이너리**라 browser 와 달리 시스템 deps 없이 됩니다.

> ⚠️ **반드시 한 단계씩, 각 STEP 의 _검증_ 이 통과한 뒤 다음으로.** 한꺼번에 바꾸면 실패 시 원인 추적이 불가능합니다(저자 실측 교훈 — browser 설정에서 겪음).

**전제 (gog 자체 인증)**: 호스트에 gog 가 설치되어 있고, **컨테이너 전용 OAuth 클라이언트**로 인증된 격리 config 디렉토리가 있어야 합니다. gog 설치·Google OAuth(GCP 프로젝트/클라이언트) 는 <https://gogcli.sh> 참조. 호스트 메인 gog 와 **병행**하려면 별도 `--client` 로 인증해 토큰을 분리하세요:
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
docker exec "$GW" gog gmail search 'newer_than:1d' --account <account@gmail.com> -p
```
**✅ 검증**: `auth list` 에 계정이 나오고, gmail 검색이 `rc=0` + 실제 메일이면 **Google API 호출 성공**.
**❌ `:ro` 관련 쓰기 오류**가 나면 extra.yml 의 `gogcli` 마운트에 붙은 `:ro` 를 제거(RW)하고 재생성 — 토큰 갱신 쓰기가 필요한 경우입니다. (보안 강화로 `:ro` 를 원하면 RW 로 한 번 토큰 갱신 후 다시 `:ro` 로.)

> 💡 `gog gmail search` 의 검색어는 `--query` 가 아니라 **위치 인자**입니다 (예: `gog gmail search 'newer_than:1d'`).

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

---

## 부록 — gog 호출 경로·반응시간, 그리고 *결정론적 skill* 의 필요

> gog 설치는 *출발점*일 뿐입니다. OpenClaw 봇으로 gog 를 자동화할 때 반응속도가 어떻게 결정되는지, 그래서 무엇을 준비해야 하는지를 정리합니다.

### OpenClaw 이 gog 를 호출하는 경로

```
Telegram → OpenClaw 게이트웨이 → claude-cli 백엔드 (모델 추론)
   → tool call → gog 실행
       → 바이너리 로드 + keyring 복호화 + OAuth(프로파일 만료 시 .claude creds bootstrap)
       → Google API HTTPS → 결과 JSON
   → 모델이 JSON 파싱 → 다음 단계 결정 → (다단계면 위 사이클 반복)
→ 응답
```

### 어디서 시간이 가나 (저자 실측, warm 기준)

| 구간 | 시간 | 비고 |
|---|---|---|
| **모델 추론 (턴당)** | **~5-10초 (구조적 하한)** | 시스템프롬프트 23.5KB + 추론 + JSON 파싱. **지배적 비용** |
| 단순 gog 작업 1건 | haiku **6.5초** / sonnet 18~34초 | 모델 선택이 좌우 (측정 근거: [openclaw-skills.md](./openclaw-skills.md) "응답 속도 최적화") |
| OAuth bootstrap | warm 0.34초 / cold ~7.6초(1회) | 토큰 만료·콜드스타트 시에만 |
| gog 호출 자체 | **~2초/call** | 네트워크 바운드, 결정형(빠름) |

**핵심: 반응시간은 gog 가 아니라 *LLM 매개* 가 지배합니다.** gog 는 ~2초로 빠른데, *매 단계를 모델이 추론·파싱·결정* 하는 것이 ~5-10초/턴을 더하고, 다단계면 그만큼 곱해집니다. 게다가 긴 침묵 구간은 watchdog 종료·하위에이전트 고아(미아)를 유발합니다.

### 그래서 — 반복·결정형 작업은 *얇은 결정론적 skill* 로 감싼다

라벨 첨부저장(`데모1 첨부저장`)처럼 **완전히 명세된(판단 0) 작업** 은, 여러 gog 호출을 하나의 "동사"로 묶는 **결정론적 스크립트 skill** 로 만들면:

- 모델 라운드트립 **N → 1** (cron 이면 0)로 압축 → **~5-10초 하한 *아래* 로** 단축
- watchdog 침묵·고아 위험 **동시 제거** (결정 지점이 1개뿐)

판단이 필요한 *롱테일* 만 LLM 에 남기고(이상 시 skip + 보고), 기계적 부분은 스크립트가 처리하는 **2층 구조** 가 빠르고 안정적입니다. (vault `CLAUDE.md` 의 "결정형 작업은 gog 로 위임" 원칙과 동일.)

### 결론 — OpenClaw 사용 *전* 에 공부할 것

> **OpenClaw 로 자동화를 잘 굴리기 위해 미리 익혀야 할 핵심 역량은 "최대한 간단한 추론 + 결정론적 skill 을 만드는 능력" 입니다.**

gog 설치·인증은 토대일 뿐이고, **반응속도·안정성은 그 위에 무엇을 어떻게 얹느냐(결정형 skill 설계)** 에 달려 있습니다. LLM 에 모든 단계를 추론시키면 느리고(턴당 하한) 불안정한데(watchdog·고아), *결정형 부분을 얇은 skill 로 떼어내고 LLM 은 판단에만* 쓰는 것이 이 시스템을 실용적으로 만드는 갈림길입니다.
