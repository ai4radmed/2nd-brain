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

## 설치방법 (사용자)

1. Windows 에서 WSL2 활성화
2. WSL2에서 Git 설치
3. WSL2에서 docker 및 docker-compose 설치
4. WSL2에서 Claude Code CLI 설치
5. Telegram 설치 및 Bot 토큰 만들기
6. OpenClaw Docker 컨테이너 설치: [docs/openclaw-docker-container.md](./docs/openclaw-docker-container.md)
7. 설치 후 기본 스킬·활용: [docs/openclaw-skills.md](./docs/openclaw-skills.md)
8. (선택) gog 로 Google Workspace(메일·일정·할일) 연계: [docs/openclaw-docker-gog.md](./docs/openclaw-docker-gog.md)
9. 내 vault 만들기: `./bootstrap.sh` 실행 — 빈 PARA 골격(knowledge/ + sources/) + 가이드를 `@`-import 하는 얇은 `CLAUDE.md` 자동 생성. 이후 운영 방법론은 [methodology/](./methodology/) 참조, 자료 흡수는 brainify.

## 설치방법 (AI Agent)

- 이 프로젝트를 클론한 로컬저장소에서 Claude Code CLI를 실행
- 로컬저장소의 `CLAUDE.md` 를 통해 Claude Code CLI가 이 프로젝트를 인식
- 이후 "단계별로 설치를 진행해줘" 라고 하면 대화형으로 설치 가능
- 사용자가 설치하는 과정의 질문이나 오류에 대한 대책을 제안받는 데에도 사용 가능
