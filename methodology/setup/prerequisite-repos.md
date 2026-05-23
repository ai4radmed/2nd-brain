# 선결 저장소 — brain-system 셋업 시 필요한 repo 카테고리

이 가이드의 권장 셋업으로 second-brain 을 굴리려면 vault 외에 다음 **카테고리** 의 저장소들을 자기 환경에 두는 것을 권장한다. 각자의 운영 상태(실제 URL·계정·경로) 는 자기 vault 안 `knowledge/02_areas/brain-system/repos.md` 에 인스턴스 표로 기록한다 — 그것이 사용자의 권위 원본이고, 본 문서는 *왜 어떤 카테고리가 필요한지* 만 설명하는 일반화 부분.

## 왜 인벤토리를 별도 문서로 두는가

- second-brain 운영에 필요한 저장소는 한 곳에 모이지 않고 여러 디렉토리에 흩어진다 (`~/projects/`·`~/.claude/`·`~/.openclaw/` 등).
- 단순 자동 탐색은 *경로 한 줄이 빠지면* 통째로 누락된다 — 실제로 `~/.openclaw/workspace` 가 그렇게 누락된 사례가 있었음.
- 단일 인벤토리 + 카테고리 분류 + (보조) 자동 탐색 sanity check 조합으로 *누락이 구조적으로 차단* 된다.

## 권장 카테고리

| 카테고리 | 역할 | 일반적 위치 | 일반적 가시성 | 일반적 동기 |
|---|---|---|---|---|
| **vault** | 실제 PKM 데이터 (knowledge + sources). 본인의 노트·원본 자료. | `~/projects/2nd-brain-vault` | 비공개 | SyncThing + 클라우드 (git 비친화적 — 대용량 바이너리·잦은 변경) |
| **vault-guide** *(본 저장소)* | 운영 방법론·템플릿·빈 PARA 골격. 일반화된 매뉴얼. | `~/projects/2nd-brain-vault-guide` | 공개 | git |
| **docker 환경** | 격리 실행환경 (Claude CLI · Gemini · OpenClaw · MCP 서버) 컨테이너. | `~/projects/2nd-brain-docker` | 공개 가능 | git |
| **Claude Code 슬래시 명령** | 자기 워크플로우 슬래시 명령 모음 (예: `/git-routine`). | `~/.claude/commands` | 보통 비공개 — 개인 운영 패턴이 드러남 | git |
| **Claude Code 스킬** | 자기 skill 정의 모음. | `~/.claude/skills` | 보통 비공개 | git |
| **OpenClaw 설정** | `openclaw.json` 등 control plane 설정 권위 원본. | `~/projects/openclaw-config` 또는 유사 | **비공개 필수** — 토큰·인증 정보 포함 가능 | git |
| **OpenClaw workspace** | 에이전트의 home — 메모리·soul·workspace skill. | `~/.openclaw/workspace` | **비공개 필수** — 개인 메모리·에이전트 인격 | git |
| **(선택) Claude Code 컨테이너 빌드** | Claude CLI 도커 이미지 빌드 자산. | `~/projects/claude-cli-docker` 또는 유사 | 공개 가능 | git |

## 가시성·동기 정책 일반 원칙

- **공개 / 비공개** 분리는 가시성(정보 누설 가능성) 기준이다 — 토큰·개인 메모리·에이전트 soul 은 비공개. 위 표의 가시성 권장값은 *최소 안전선* 이며 더 엄격해도 무방.
- **git push/pull 동기** vs **SyncThing 동기**:
  - 코드·설정 자산: git. 변경이 의미 단위로 잡히고, 충돌 해결이 명시적.
  - vault 데이터 (마크다운 노트 + 바이너리): SyncThing + 클라우드 백업. git 은 대용량·잦은 변경에 부적합.
- **단일 권위 원본 원칙**: 자기 인스턴스의 실제 목록·URL 은 vault 안 `knowledge/02_areas/brain-system/repos.md` 에 표로 보관. 본 가이드는 *그 표를 어떻게 채울지의 카테고리 정의* 만 제공.

## 추천 인벤토리 스키마

자기 vault 안 `repos.md` 의 표 형식 예시:

| 카테고리 | 경로 | 원격 | 역할 | 가시성 | 동기 |
|---|---|---|---|---|---|
| docker | `~/projects/2nd-brain-docker` | (자기 fork URL) | 격리 실행환경 | 공개 | git |
| openclaw-config | `~/projects/openclaw-config` | (자기 private repo URL) | OpenClaw 설정 | 비공개 | git |
| ... | ... | ... | ... | ... | ... |

해당 표를 단일 권위 원본으로 두고, 슬래시 명령(`/git-routine` 등) 이 그 표를 입력으로 읽어 일괄 동기하는 패턴을 권장한다. 슬래시 명령 구현은 자기 `~/.claude/commands/` 안에서 정의 (이 저장소엔 일반화된 명령 본은 두지 않음 — 명령은 가시성·운영 정책에 종속적).

## 새 PC 셋업 시 흐름

1. 본 카테고리 표를 보고 자기에게 필요한 항목 결정 (vault·docker·vault-guide 는 거의 필수, 나머지는 선택).
2. 각 카테고리의 실제 fork·자기 repo URL 을 정해 clone.
3. 자기 vault 의 `knowledge/02_areas/brain-system/repos.md` 에 인스턴스 표 채우기 (없으면 생성).
4. 자기 `~/.claude/commands/` 에 `git-routine.md` 같은 일괄 동기 명령 두기 (선택).

## 메타

- 2026-05-12 — 최초 생성. 누락 방지 인벤토리 분업 (방법론은 vault-guide, 인스턴스는 vault) 패턴 확립.
