# BenKorea's 2nd-brain

- 개인 자료를 AI agent 가 다루기 좋은 형식으로 가공하고, 클라우드(메일·일정·연락처)와 연계해 지식화하는 PKM 프로젝트의 **공개 운영 저장소**
— 보안강화를 위해 OpenClaw를 Docker Container로 설치 운영

## Second Brain이란?

- **Tiago Forte** 가 제안한 PKM (Personal Knowledge Management) 프레임워크
- 자료의 저장위치를 PARA로 분류
  > - **P**roject(기한이 정해진 업무/자료)
  > - **A**rea(자신의 전문영역에 해당하는 업무/자료)
  > - **R**esource(그 이외의 자료/주제)
  > - **A**rchive(완료되었거나 보관할 업무/자료)
- 자료를 다루는 흐름을 CODE로 파악
  > - **C**apture(머릿속에 공명한 것만 수집)
  > - **O**rganize(PARA 기준으로 실행 가능성에 따라 정리)
  > - **D**istill(노트로 돌아올 때마다 핵심을 점진적으로 요약·농축)
  > - **E**xpress(모은 것을 실제 작품·결정·산출물로 표현)
- PARA 가 *자료를 어디에 둘 것인가* 의 framework 라면, CODE 는 *자료를 어떻게 흐르게 할 것인가* 의 framework — 노트 축적 자체가 아니라 *표현·창작* 이 최종 목적이라는 점이 BASB (Building a Second Brain)의 핵심 강조점입니다.

## BenKorea's 2nd-brain이란?

- PC의 개인자료를 AI agent가 분석하기에 좋은 형식으로 가공하고, 클라우드의 메일/일정/연락처 등과 연계하여 지식화하는 저자의 PKM 프로젝트
- AI agent는 클라우드 모델을 사용하며, 정액요금제로 운영이 가능한 Claude를 사용함
- 자료를 저장하고 지식화하는 과정을 자동화하기 위해, AI agent를 제어할 수 있는 OpenClaw 오픈소스를 사용함

## AI Agent가 인식하기에 좋은 자료저장형식은?

- 다양한 형식의 수백 GB 이상의 개인자료를 단순히 AI Agent에게 검색시키면 정확도가 떨어짐
- 저자는 자료/지식의 저장단위인 노트(마크다운 형식)마다, 검색에 필요한 인덱스성 정보(메타데이터)를 서두에 기록하는 방식을 채택함
- *.hwp, *.doc 등 기존 문서파일들의 원본을 보관하고, 요약노트에 해당하는 마크다운 문서를 링크하는 방식을 채택함

## 2nd-brain의 자료저장구조 vault
- 2nd-brain은 2nd-brain-vault에 자료를 저장하며
- 자료의 원본은 sources/{inbox; project; area; resource; archive} 폴더에 저장됨
- 지식화된 노트들은 knowledge/{inbox; project; area; resource; archive} 폴더에 저장됨

## 클라우드의 메일/일정/연락처 등과 연계하는 방법은?

- 구글 지메일/캘린더/연락처/할일 등을 내 컴퓨터에서 제어할 수 있는 **gog CLI** 서비스를 사용함

## 다른 사람도 2nd-brain을 사용할 수 있나요?

- 원하시는 누구나 사용 가능합니다 (MIT License). 저자의 추천 환경은:
  - **WSL2** 운영체제에
    - Git 설치 (이 원격저장소를 클론하는 데 필요)
    - docker 및 docker-compose 설치 (OpenClaw를 container로 설치)
    - Claude Code CLI (OpenClaw가 제어할 AI agent이자, 설치를 대행하거나 오류 시 대책을 제안하는 역할)
    - OpenClaw 및 Telegram 설치

## 저장소 모델·권위 (구조 이해)

### 3-tier
| tier | 저장소 | 내용 | 가시성 |
|---|---|---|---|
| **공개 설치킷** *(이곳)* | `ai4radmed/2nd-brain` | 설치문서·방법론·템플릿·골격·bootstrap | 공개 |
| **데이터·운영** | `2nd-brain-vault` | knowledge + sources + 운영 `CLAUDE.md`(inline·self-sufficient·사용자 소유) | 비공개(SyncThing) |
| **개인 운영** | `~/.claude/skills`·`~/.claude/commands`·`~/.openclaw/workspace` 등 | 개인 스킬·슬래시명령·config | 비공개 |

원리: **데이터(무엇을 안다) / 코드·방법론(어떻게 한다, 공유가능) / 설정(나는 누구다, 개인)** 분리. 이 repo = *코드·방법론* tier.

### upstream/downstream — 사용자는 pull-only, 개발자만 편집
- **개발자**(저자): 여기서 *편집·commit·push*. **사용자**: clone 1회 → 버전업 시 `git pull` 만, **이 repo 편집 ✗**(편집 시 pull 충돌). 자기 작업물(개인 스킬·config·vault)은 *자기 repo* 로.
- install 스크립트가 `templates/` 를 사용자 개인 위치로 *복사*. "개발자 것 ≠ 내 것을 같은 repo 에" 는 **canonical 출처 층**에서 성립 — 런타임 스킬 dir 은 dev-복사본+개인 스킬이 섞이며 둘 다 *사용자 소유*(정상).
- **install 규율**: 멱등·비파괴(기존 사용자 파일 덮기 전 확인/스킵). 설치된 dev-스킬은 **직접 편집 말고 이름 바꿔 포크** → 다음 버전업이 내 커스터마이즈를 안 덮는다.

### 권위 위계
| 영역 | 정본 |
|---|---|
| 컴포넌트 설치 절차 | 이 repo `docs/` |
| 공개 방법론 (PARA·companion note·brainify 일반론) | 이 repo `docs/brain-system/` |
| **운영(개인) 규약 — 일상 권위** | **`2nd-brain-vault/CLAUDE.md`** (inline·self-sufficient, 본 repo `@`-import ✗) |
| 다기기 동기 | 전략=`docs/setup/prerequisite-repos.md`·실행=`docs/multi-device-sync.md`; **repo 목록 권위=vault `repos.md`**, 실행=`/git-routine` |
| OpenClaw 자체 | 공식 <https://docs.openclaw.ai> |

> 이력: `2nd-brain-setup`→`2nd-brain` rename(2026-05-23) + 구 `2nd-brain-vault-guide`·`2nd-brain-docker` 흡수(2026-05-25, 공개 단일 입구 통합). 2026-05-27 `CLAUDE.md` 를 설치 전담으로 린화 + `@`-import fiction 제거(vault `CLAUDE.md` 는 inline·self-sufficient).

## 설치방법 (사용자)

1. Windows 에서 WSL2 활성화
2. WSL2에서 Git 설치
3. WSL2에서 docker 및 docker-compose 설치
4. WSL2에서 Claude Code CLI 설치
5. Telegram 설치 및 Bot 토큰 만들기
6. 이 저장소(2nd-brain) 클론
```bash
git clone https://github.com/ai4radmed/2nd-brain.git ~/projects/2nd-brain
```
7. **내 vault 먼저 만들기**: `./bootstrap.sh` 실행 — 빈 PARA 골격(`knowledge/` + `sources/`) + 운영 `CLAUDE.md` 생성. ⚠️ **OpenClaw·파서 등 도커 구동보다 *먼저* 실행해야 한다** — 도커 bind 마운트 대상 폴더가 구동 시점에 없으면 Docker 가 *root 소유 빈 폴더*를 자동생성해 권한문제가 생긴다(특히 파서 컨테이너(12)가 vault 를 마운트). bootstrap 은 docker·OpenClaw 의존이 없어 클론 직후 가능하다. 운영 방법론은 [docs/brain-system/](./docs/brain-system/), 자료 흡수는 brainify.
8. OpenClaw docker 설치: [docs/openclaw-docker-install.md](./docs/openclaw-docker-install.md)
9. 설치 후 기본 스킬·활용: [docs/openclaw-skills.md](./docs/openclaw-skills.md)
10. (선택) **커스텀 스킬 템플릿 설치** — 복사해서 쓰는 스킬 예제(예: `gmail-label-actions` = 라벨 기반 메일 자동처리)를 워크스페이스로 설치: [templates/skills/](./templates/skills/) (런타임별 설치 대상·절차는 [templates/skills/README.md](./templates/skills/README.md))
11. (선택) gog 로 Google Workspace(메일·일정·할일) 연계: [docs/openclaw-docker-add-gog.md](./docs/openclaw-docker-add-gog.md)
12. (선택) 문서 파서 컨테이너 — PDF·docx·xlsx 를 **로컬에서 markdown 으로** 변환(외부 API 0, 재무·민감자료 leak 방지): [docs/2nd-brain-parser-setup.md](./docs/2nd-brain-parser-setup.md). `docker pull ghcr.io/benkorea/2nd-brain-parser` 로 prebuilt 이미지를 받아 구동하며, 자료 흡수(brainify)의 **선행 파서**다. **vault(7)를 마운트하므로 7 이 선행돼야 한다.** 어디서 돌릴지(watchdog 회피 배치)=[docs/2nd-brain-parser-strategy.md](./docs/2nd-brain-parser-strategy.md).

## 설치방법 (AI Agent)

- 이 프로젝트를 클론한 로컬저장소에서 Claude Code CLI를 실행
- 로컬저장소의 `CLAUDE.md` 를 통해 Claude Code CLI가 이 프로젝트를 인식
- 이후 "단계별로 설치를 진행해줘" 라고 하면 대화형으로 설치 가능
- 사용자가 설치하는 과정의 질문이나 오류에 대한 대책을 제안받는 데에도 사용 가능
