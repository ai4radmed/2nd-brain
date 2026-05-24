# Container gogcli — Privilege-Separated Setup (Option B)

`2nd-brain-docker` 의 컨테이너 Claude (`sb-claude`) 가 [steipete/gogcli](https://github.com/steipete/gogcli) 를 통해 Google Workspace 작업을 수행할 때, **호스트의 gog 자격증명을 그대로 마운트하지 않고 별도 OAuth client·keyring 으로 권한을 분리**하는 절차.

## 왜 이렇게 하나 — 위협 모델

컨테이너 Claude 는 외부 입력(메신저 webhook·웹 검색 결과 등)을 처리할 가능성이 있는 환경. prompt injection 으로 인한 자격증명 exfiltration 을 가정해야 한다.

호스트의 `~/.config/gogcli/` 를 그대로 마운트하면:

- 컨테이너 침해 = 호스트의 모든 Google API 권한 침해와 동등
- Audit log 에서 컨테이너 행위 ↔ 호스트 행위 식별 불가능 (같은 OAuth client_id)
- 침해 대응 시 OAuth client 를 disable 하면 호스트의 OpenClaw·cron·셸 스크립트 등 모든 자동화도 함께 끊김
- 호스트의 gog 는 native Claude·OpenClaw·cron·shell 등 다중 호출자에 의해 공유되므로 침해 폭발 반경이 큼

본 가이드는 **컨테이너 전용 OAuth client + 별도 keyring + 별도 passphrase** 를 두어 위 위험을 분리한다. write 권한이 양쪽에 있어도 정체성이 다르므로 audit·revoke·quota 가 독립.

## 결과물 (이 가이드 완료 시)

| 환경 | OAuth client | gog config dir | keyring passphrase | 비고 |
|---|---|---|---|---|
| 호스트 native Claude | 기존 (`default` 또는 본인 client 명) | `~/.config/gogcli/` | 기존 (Bitwarden "gog keyring passphrase" 추정) | 변경 없음 |
| 컨테이너 Claude (`sb-claude`) | **신규 `claude-container`** | **신규 `~/.config/gogcli-container/`** | **신규 (Bitwarden "gog container keyring passphrase")** | 본 가이드로 셋업 |

## 전제

1. **호스트에 gog 가 이미 설치·인증 완료** — `gog --version` 작동, 한 계정 이상 OAuth 추가됨. 처음이라면 gogcli 의 [README](https://github.com/steipete/gogcli) 또는 (vault 사용자라면) `gog-openclaw-setup.md` 절차로 호스트 셋업을 먼저 끝낼 것.
2. **GCP project 접근** — 호스트에서 사용 중인 OAuth consent screen 이 있는 GCP project 의 owner/editor 권한.
3. **시크릿 매니저** — Bitwarden 또는 1Password 등 (passphrase 두 개를 별도 항목으로 관리하기 위함).
4. **2nd-brain-docker 컨테이너 기동 중** — `make up` 으로 `sb-claude` 가 Up.

## 아키텍처 한눈에

```
┌─ 호스트 (WSL2 native) ─────────────────────────────────┐
│                                                         │
│  /usr/local/bin/gog  (단일 binary, 양쪽 공유)           │
│                                                         │
│  ~/.config/gogcli/         ~/.config/gogcli-container/  │
│  ├── config.json           ├── config.json              │
│  ├── credentials.json      ├── credentials.json         │
│  │   (host client)         │   (container client)       │
│  └── keyring/              └── keyring/                 │
│      (host passphrase)         (container passphrase)   │
│                                                         │
│  사용자: native Claude     │  bind-mount RO              │
│         OpenClaw·cron      ▼                            │
│         shell 등           │                            │
│                            │                            │
└────────────────────────────┼────────────────────────────┘
                             │
              ┌──────────────▼──────────────┐
              │  컨테이너 sb-claude         │
              │  /home/user/.config/gogcli/ │
              │  ← XDG_CONFIG_HOME 트릭     │
              │  GOG_KEYRING_PASSWORD env   │
              └─────────────────────────────┘
```

## Step 1 — GCP 콘솔: 컨테이너 전용 OAuth client 생성

같은 GCP project 안에 OAuth client 를 하나 더 만든다.

1. [Google Cloud Console](https://console.cloud.google.com/) → 호스트 gog 가 사용 중인 project 선택.
2. 좌측 메뉴 **APIs & Services → Credentials**.
3. 상단 **+ CREATE CREDENTIALS → OAuth client ID**.
4. **Application type**: `Desktop app`.
5. **Name**: `claude-container` (식별 가능한 이름이면 무엇이든).
6. **CREATE** 클릭 → **DOWNLOAD JSON** 으로 client secret 파일 받음. 이 파일을 임시로 `~/Downloads/claude-container-client.json` 등에 저장.

> 같은 OAuth consent screen·같은 testing user 풀을 공유하므로 추가 설정은 불필요. project 가 production 상태면 새 client 도 그대로 production.

## Step 2 — Scope 결정 (write 권한 + defense-in-depth)

컨테이너 client 의 OAuth consent 시 동의받을 scope 를 미리 정한다. write 도 가능하도록 하되 **호스트보다 보수적으로** 좁히는 게 권장 패턴.

권장 시작점:

| Scope | 포함? | 이유 |
|---|---|---|
| `gmail.modify` | ✅ | 라벨·archive·draft 작성 (brainify 핵심) |
| `gmail.send` | ❌ | 메일 발송은 사람이 검토 후 수동. `--gmail-no-send` flag 로 이중 차단. |
| `gmail.settings.basic` | ❌ | 필터·서명 변경 불필요 |
| `calendar.events` | ✅ | 일정 조회·생성·수정 |
| `calendar` (full) | ❌ | 캘린더 자체 생성·삭제 권한 불필요 |
| `drive.file` | ✅ | 앱이 만든 파일만 access (전체 Drive 노출 안 됨) |
| `drive` (full) | ❌ | 전체 Drive read·write 는 위험 |
| `docs`, `sheets`, `tasks` | 필요 시 | 사용 워크플로우 따라 |

scope 세부 목록은 [Google API Scopes](https://developers.google.com/identity/protocols/oauth2/scopes) 참조.

## Step 3 — 호스트: 컨테이너 전용 config 디렉토리 생성

```bash
# 1. 디렉토리 생성 (root 외 access 차단)
mkdir -p ~/.config/gogcli-container
chmod 700 ~/.config/gogcli-container

# 2. Step 1 에서 다운로드한 client secret 을 옮김
mv ~/Downloads/claude-container-client.json ~/.config/gogcli-container/client_secret.json
chmod 600 ~/.config/gogcli-container/client_secret.json
```

## Step 4 — 호스트: 컨테이너 client 등록 (1회 OAuth)

`XDG_CONFIG_HOME` 을 임시로 바꿔 별도 config 디렉토리를 사용하게 한다.

```bash
# 별도 keyring passphrase 를 미리 정해두기 (Bitwarden 항목 "gog container keyring passphrase").
# 이 passphrase 가 컨테이너 keyring 을 unlock 할 때 사용됨.
export GOG_KEYRING_PASSWORD='<새 컨테이너 passphrase>'

# 별도 config dir 을 활성화
export XDG_CONFIG_HOME=$HOME/.config
# 위는 명시적 — 사실 default. 실제 분리는 다음 명령에서 폴더 이름으로 함.
# (정확히는 gog 가 $XDG_CONFIG_HOME/gogcli/ 를 보므로,
#  컨테이너 전용으로 쓰려면 host 측에서도 GOG 호출 시 임시 override 함.)

# 호스트의 gog 를 임시로 컨테이너 config 디렉토리로 향하게 해서 client 등록 + OAuth.
GOGCLI_DIR=$HOME/.config/gogcli-container
HOME_FAKE=$(mktemp -d)
ln -s "$GOGCLI_DIR" "$HOME_FAKE/.config" 2>/dev/null || mkdir -p "$HOME_FAKE/.config" && ln -s "$GOGCLI_DIR" "$HOME_FAKE/.config/gogcli"

# 1) Client 등록 — Step 1 의 client_secret 를 'claude-container' 이름으로 등록
HOME=$HOME_FAKE gog auth credentials add \
    --client claude-container \
    --client-secret "$GOGCLI_DIR/client_secret.json"

# 2) OAuth 토큰 추가 — 컨테이너 client 로 본인 Google 계정 인증 (브라우저 열림)
HOME=$HOME_FAKE gog auth add <your-email>@gmail.com \
    --client claude-container

# 브라우저에서 Google 로그인 → consent 화면에서 Step 2 의 scope 들 승인
# 완료 시 keyring 이 새 passphrase 로 암호화되어 ~/.config/gogcli-container/keyring/ 에 저장됨

unset GOG_KEYRING_PASSWORD HOME
```

> 위 `HOME` override 트릭은 gog 가 `$HOME/.config/gogcli/` 를 보는 동작에 맞춰 컨테이너용 디렉토리만 임시로 등록하기 위함. 평소 호스트 gog 작업에는 영향 없음. gog 가 `--config-dir` 플래그를 노출하면 그쪽이 더 깔끔하지만 v0.13.0 시점엔 `XDG_CONFIG_HOME`/`HOME` 경유.

## Step 5 — 시크릿 매니저: passphrase 항목 분리

| Bitwarden 항목 | 값 |
|---|---|
| `gog keyring passphrase` (기존) | 호스트 keyring 용 (변경 없음) |
| `gog container keyring passphrase` (신규) | Step 4 에서 정한 컨테이너 keyring 용 |

두 passphrase 는 **반드시 다른 값** 으로 둘 것. 같은 값이면 한쪽 노출이 양쪽 노출이 됨.

## Step 6 — overlay 파일로 활성화 (compose.yml 직접 수정 안 함)

본 저장소의 `compose.gog.yml` 이 미리 작성되어 있다 — opt-in overlay 패턴.

```yaml
# compose.gog.yml 의 핵심 (참고용, 직접 수정 불필요)
services:
  claude:
    volumes:
      - /usr/local/bin/gog:/usr/local/bin/gog:ro
      - ${HOME}/.config/gogcli-container:/home/user/.config/gogcli:ro
    environment:
      GOG_KEYRING_PASSWORD: ${GOG_CONTAINER_KEYRING_PASSWORD:?...}
```

핵심 결정 사항:

- **별도 overlay 파일** — base `compose.yml` 은 그대로. gog 셋업 안 한 사용자에게 영향 0.
- **gog 바이너리는 RO bind mount** — 호스트 업그레이드 시 컨테이너도 자동 반영. 컨테이너에서 변조 불가 (read-only).
- **컨테이너 전용 config 도 RO bind mount** — 컨테이너 안에서 keyring 변조·새 토큰 추가 시도 차단. 호스트 측에서만 토큰 갱신 가능.
- **passphrase 는 env var** — non-TTY 컨테이너에서 keyring unlock 의 유일한 경로. value 는 `.env` 에서 주입 (다음 step).

## Step 7 — `.env` 에 passphrase 주입

`2nd-brain-docker/.env` (gitignored) 에 추가:

```bash
# 컨테이너 전용 gog keyring passphrase (Bitwarden "gog container keyring passphrase")
GOG_CONTAINER_KEYRING_PASSWORD=<Step 4 에서 정한 값>
```

`.env.example` 에는 placeholder 만 — 실제 값은 secret 이라 검사된 git 에 커밋되지 않게.

## Step 8 — overlay 적용·재기동·검증

```bash
make up-gog       # 또는: make restart-gog
                  # 내부적으로: docker compose -f compose.yml -f compose.gog.yml up -d
```

`make up` (overlay 없는 기본) 으로 다시 돌아가려면 그냥 `make up`. overlay 는 명시적 opt-in 이라 기본 흐름엔 영향 없음.

검증 명령:

```bash
# 1. env 가 컨테이너에 주입됐는지
docker exec sb-claude bash -c 'echo ${GOG_KEYRING_PASSWORD:+set}'   # "set" 나와야 함

# 2. gog 가 컨테이너에서 실행 가능한지
docker exec sb-claude gog --version

# 3. 컨테이너 config 가 보이는지
docker exec sb-claude ls /home/user/.config/gogcli/

# 4. 실제 API 호출
docker exec sb-claude gog calendar events \
    --account <your-email>@gmail.com \
    --client claude-container \
    --week --max 5

# 결과: 일정 목록 출력. passphrase 프롬프트 없이.
```

## Defense-in-depth 권장 옵션

OAuth scope 만으로 부족하면 gog 의 런타임 flag 로 추가 차단:

```bash
# 시스템 wide 로 강제하려면 wrapper script 사용:
# 컨테이너 안 ~/.local/bin/gog 에 다음 작성하고 PATH 우선순위 높임
exec /usr/local/bin/gog \
    --gmail-no-send \
    --disable-commands="gmail.send,drive.delete,drive.permissions" \
    "$@"
```

| Flag | 효과 |
|---|---|
| `--gmail-no-send` | OAuth scope 와 무관하게 Gmail send 차단 (agent safety) |
| `--disable-commands="x,y"` | 특정 subcommand 비활성화 (예: `drive.delete`, `calendar.calendars.delete`) |
| `--no-input` | 대화형 프롬프트 대신 즉시 실패 (CI/non-TTY) |
| `--dry-run` | 실제 변경 없이 의도만 출력 (디버깅) |

## 침해 대응 — Revoke 절차

컨테이너 안에서 의심스런 활동(라벨 폭주·Drive 대량 다운로드 등) 감지 시:

1. [GCP 콘솔 → Credentials](https://console.cloud.google.com/apis/credentials) → `claude-container` OAuth client → **DELETE** 또는 disable.
2. 호스트의 `default` client 는 그대로 작동 — OpenClaw·cron·native Claude 모두 정상.
3. 영향 범위 조사: GCP 콘솔의 [OAuth 활동 로그](https://console.cloud.google.com/iam-admin/audit) 에서 `claude-container` client_id 의 호출만 필터링.
4. 컨테이너 재셋업 시 Step 1 부터 새 client 생성 (이름은 `claude-container-2` 등 버전 식별).

## Troubleshooting

| 증상 | 원인 | 해결 |
|---|---|---|
| `no TTY available for keyring file backend password prompt` | `GOG_KEYRING_PASSWORD` 미주입 | `.env` 에 변수 있는지, `make restart` 했는지 확인 |
| `read token: invalid passphrase` | 호스트 keyring 의 passphrase 와 컨테이너 keyring 의 passphrase 가 다른데 호스트 값을 씀 | Bitwarden 항목 분리 확인 — 컨테이너 항목 값을 .env 에 |
| `client claude-container not found` | Step 4 의 client 등록 실패 | `gog auth credentials list` (HOME override 한 상태로) 로 등록 확인 |
| `OAuth client unauthorized` | scope 미승인 또는 testing user 미등록 | GCP consent screen 에서 본인 이메일이 testing users 에 있나, scope 가 추가되어 있나 확인 |
| 컨테이너 config 디렉토리가 비어 보임 | `~/.config/gogcli-container` 가 호스트에 없는데 mount 시도 | Step 3 디렉토리 생성 빠뜨림. 생성 후 `make restart`. |

## 참고

- [steipete/gogcli](https://github.com/steipete/gogcli) — gog 업스트림
- [Google API Scopes](https://developers.google.com/identity/protocols/oauth2/scopes) — scope 정확한 명칭
- [GCP OAuth client management](https://console.cloud.google.com/apis/credentials)

이 가이드가 다루지 않는 것:
- 호스트의 첫 gog 셋업 (gogcli upstream README 참조)
- OpenClaw 의 systemd env 주입 (별개 운영 흐름)
- 운영 중 scope 추가·축소 (GCP consent screen 갱신 + `gog auth add` 재실행 필요)
