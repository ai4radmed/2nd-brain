# Claude Code 호스트 설치 가이드 — WSL2 native

WSL2 ext4 native 환경에 Claude Code 를 공식 권장 방법 (`install.sh`) 으로 설치하는 가이드. 컨테이너 (`sb-claude`) 도 같은 방법을 사용 — 호스트·컨테이너 인지 부하 통일.

## 전제

- **WSL2 ext4 native** (Ubuntu/Debian 계열)
- **curl** 설치됨 — 검증:
  ```bash
  command -v curl || sudo apt install -y curl
  ```
- 인터넷 outbound HTTPS (`claude.ai`, `downloads.claude.ai`)
- **Claude Pro/Max 구독** 또는 OAuth 가능 계정

> **Node 불필요** — Claude Code 는 Bun 으로 컴파일된 self-contained native binary (240MB). 시스템에 Node·npm 0 의존성.

## Step 1 — 공식 install.sh 실행

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

스크립트 자동 처리:
- 플랫폼 감지 (`uname` → linux-x64 등)
- 최신 manifest.json 다운로드
- platform 별 SHA256 체크섬 추출 + 무결성 검증
- native binary 다운로드 → `~/.local/share/claude/versions/<ver>/`
- `~/.local/bin/claude` symlink 생성

## Step 2 — PATH 활성화

```bash
grep -q '\.local/bin' ~/.bashrc || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
exec bash
```

## Step 3 — 검증

```bash
which claude                                # /home/<user>/.local/bin/claude
claude --version                            # 2.1.x (Claude Code)
ls -la ~/.local/bin/claude                  # symlink → versions/<ver>
ls ~/.local/share/claude/versions/          # 설치된 버전들
```

## Step 4 — 첫 실행 + OAuth 로그인

```bash
claude
```

브라우저 OAuth 흐름:
1. 터미널에 URL 출력 → 브라우저로 열기
2. claude.ai 에서 로그인 + 권한 동의
3. 콜백 코드 터미널에 paste
4. `~/.claude/.credentials.json` (chmod 600) 에 access·refresh·expires 저장

## Step 5 — 자동 업데이트 (default 활성, 손대지 않음)

native install 의 자동 업데이트는 **기본 활성**. 새 release 가 나오면 background 에서 다운로드 → `~/.local/share/claude/versions/<new>/` 에 추가 → symlink 갱신.

확인 (시간 지난 후):
```bash
ls -t ~/.local/share/claude/versions/    # 새 버전이 들어왔는지 (mtime 최근)
readlink ~/.local/bin/claude              # symlink 가 최신을 가리키는지
```

자동 업데이트를 끄고 싶을 때만 `~/.claude/settings.json` 에:
```json
{ "env": { "DISABLE_AUTOUPDATER": "1" } }
```

## 참고 — 컨테이너 (`sb-claude`) 와의 관계

같은 `install.sh` 사용 (Dockerfile 의 `bash -s ${CLAUDE_CODE_VERSION}`) — 단 컨테이너는 **버전 핀** + **자동 업데이트 차단**:

| 측면 | 호스트 | 컨테이너 |
|---|---|---|
| install 명령 | `bash` (latest) | `bash -s ${CLAUDE_CODE_VERSION}` (특정 버전) |
| 버전 결정 | latest 자동 추종 | `.env` 의 `CLAUDE_CODE_VERSION` 으로 명시 핀 |
| 자동 업데이트 | ✓ default 활성 | ✗ `DISABLE_AUTOUPDATER=1` (compose.yml) |
| 갱신 방법 | 알아서 (자동) | `make sync && make restart` (의도적) |

자세한 컨테이너 흐름·트러블슈팅: [`container-update-guide.md`](container-update-guide.md).

## 트러블슈팅

**`claude: command not found` (설치 후 새 셸)**: PATH 미적용. Step 2 의 `~/.bashrc` 추가 + `exec bash`.

**자동 업데이트가 안 됨**: 수동 트리거
```bash
claude update                       # 또는 install.sh 재실행
```

**디스크 누적 (옛 버전들)**: active 와 최근 1-2 개만 남기고 정리 (롤백 가능성 보존)
```bash
readlink ~/.local/bin/claude        # 현재 active 확인
ls -t ~/.local/share/claude/versions/ | tail -n +3 | \
  xargs -I {} rm -rf ~/.local/share/claude/versions/{}
```

**비-TTY 환경 (Claude Code 의 도구 호출 등) 에서 OAuth 실패**: 본인 셸에서 직접 `claude` 실행해 OAuth 완료 → `~/.claude/.credentials.json` 영속화. 이후 비-TTY 호출도 작동.

## 변경 이력

- **2026-05-06**: 초안 — 옵션 A·B 분리, 광범위 트러블슈팅, 다중 기기 운영 등 포괄.
- **2026-05-06**: 옵션 A 단일로 단순화 — 공식 권장만 기술. 컨테이너 Dockerfile 도 같은 흐름으로 통일됨에 따라 가이드도 통일.
