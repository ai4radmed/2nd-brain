# 2nd-brain 이란?

"Second Brain" 개념은 미국의 productivity expert **Tiago Forte** 가 2017년 무렵 온라인 강의 *Building a Second Brain* (BASB) 으로 정리하기 시작해, 2022년 동명의 단행본 (Atria Books) 으로 출간된 PKM (Personal Knowledge Management) 프레임워크입니다. 그가 제안한 Second Brain에서는 자료를 Project(기한이 정해진 일 또는 자료), Area(자신의 전문영역에 해당하는 일 또는 자료), Resource(그 이외의 자료 또는 주제), Archive(완료되었거나 보관할 자료)로 분류하였습니다. 또한 자료를 다루는 작업 흐름으로 **CODE** — Capture(머릿속에 공명한 것만 수집), Organize(PARA 기준으로 실행 가능성에 따라 정리), Distill(노트로 돌아올 때마다 핵심을 점진적으로 요약·농축), Express(모은 것을 실제 작품·결정·산출물로 표현) — 네 단계를 함께 제시했습니다. PARA 가 *자료를 어디에 둘 것인가* 의 framework 라면, CODE 는 *자료를 어떻게 흐르게 할 것인가* 의 framework — 노트 축적 자체가 아니라 *표현·창작* 이 최종 목적이라는 점이 BASB 의 핵심 강조점입니다.

저자는 생산성을 극대화하기 위해 자신의 로컬 하드 또는 클라우드에 저장된 모든 형태의 자료를 AI가 분석하기에 적합하도록 운영하는 프로젝트를 만들기로 했으며 위에서 많은 부분들을 차용했기에 이를 **2nd-brain**이라 명명하였습니다. **2nd-brain**은 원하는 사용자들이 따라 할 수 있도록 노력하고 있지만 저자는 이 분야의 전문가가 아니여서 때로 오류로 작동하지 않는 부분이 있더라도 너그러이 이해해 주시기를 부탁드립니다.

## 2nd-brain 폴더구조
위 PARA를 차용하였습니다. 그런데 자료가 2nd-brain 시스템에 유입될 때 분류소에 해당하는 inbox 폴더가 실용적일 것이라는 판단으로 추가했습니다.

## AI가 인식하기에 좋은 자료저장형식은?
저는 *.hwp, *.doc, *.ppt, *.xls 형식의 파일들을 주로 저장하고 있었습니다. 하지만 이런 형식의 파일들은 AI의 인식률이 좋지 않으며, 파일이 많아지면 검색속도가 느려지기 때문에 많은 자료를 저장하는 데에는 부적합합니다. 그래서 저자는 모든 자료에 대해서 1:1 매칭이 되는 **Markdown 형식의 요약파일**을 만드는 방법을 선택했습니다. 이에 따라 PARA의 상위폴더를 원본에 해당하는 sources와 Markdown 파일로 구성된 knowledge 로 나누었습니다. 그리고 Markdown 파일의 서두에 잘 구조화된 요약을 기술하였습니다. 이를 Markdown의 metadata라 부르며 검색시에는 metadata만 검색하여 속도를 향상시키는 방법을 채택하였습니다.

## 지식을 연결하는 방법
Markdown 파일을 단순히 PARA로 저장하는 것 이외에 지식을 연결하는 방법으로 관련된 Markdown 파일의 말미에 상호링크를 추가하는 방법을 사용하였습니다. 이는 옵시디언과 같은 오픈소스를 이용하면 각 Markdown이 = node들이 어떤 연결을 가지는지 그래프로 볼 수 있어 장점이 많습니다.


# 브레인화 (Brainify)
새로운 정보가 2nd-brain 시스템으로 유입될 때, 원본은 sources{PARA} 그리고 Markdown은 knowledge/{PARA}에 적절하게 저장되어야 합니다. 이는 Tiago Forte가 제안했던 CODE(Capture → Organize → Distill → Express)와 매우 유사한 과정이 필요합니다. 자료의 Capture는 지메일을 자동으로 다운로드 하고, Organize와 Distill 단계는 Cloud AI로 추론하여 Markdown 파일로 만들어 적합한 PARA에 저장하는 과정입니다. (Express단계는 사용자의 요청을 knowledge 폴더에서 적합한 내용을 검색하고 추론하여 대응하는 것입니다.). 저는 이 저장하는 단계까지는 브레인화(Brainfy)라 불렀습니다. (Openclaw/Claude Code/Gemini CLI 등에서는 자연어로 AI Agent에게 지시하기 때문에 이러한 약속어를 사용하면 효율적이라 저자는 이러한 실행을 Brainify 라고 정의해서 사용했습니다.) 


---

이 저장소는 2nd-brain 시스템의 *전체 지도* 와 *컴포넌트 설치 안내*입니다.


## 2. 컴포넌트 단면도

2nd-brain system은 데이터 유입이 되는 entry point, routing과 api에 헤당하는 gog cli, 추론을 담당하여 브레인화를 담당, 마지막에 data 저장소가 있는 4개의 게층으로 이루어져 있습니다.

```
       [Telegram]    [Obsidian]    [Claude Code CLI]      ← Entry
            │             │                │
            └─────────────┼────────────────┘
                          ▼
              ┌──────────────────────────┐
              │  OpenClaw + gog CLI      │              ← Runtime (control plane)
              └──────────────────────────┘
                          │
                          ▼
              ┌──────────────────────────┐
              │  PARA + 동반 노트         │              ← Methodology
              │  + 브레인화               │
              └──────────────────────────┘
                          │
                          ▼
              ┌──────────────────────────┐
              │  knowledge/ + sources/   │              ← Data
              └──────────────────────────┘
```

| 층 | 본 시스템에서의 선택 |
|---|---|
| **Data** | `knowledge/` (Markdown — Obsidian vault) + `sources/` (PDF·docx·xlsx·이미지 원본). 동일한 PARA 구조로 미러링된 짝 폴더. |
| **Methodology** | PARA + 동반 노트 패턴 + 브레인화 워크플로우. [vault-guide](https://github.com/ai4radmed/2nd-brain-vault-guide) 가 권위. |
| **Runtime** | **OpenClaw** — self-hosted gateway, control plane (Telegram·cron·skill·다중 에이전트). **gog CLI** — Google Workspace 결정형 백엔드 (Gmail·Calendar·Drive·Docs·Sheets). |
| **Entry** | **Obsidian** (편집·그래프 시각화) + **Claude Code CLI** (AI 매개 편집·자동화) + **Telegram bot** (메시징 매개, OpenClaw 경유). |

## 3. 저장소 지도

5개 저장소가 역할별로 분리되어 있다.

| 저장소 | 역할 | 공개 |
|---|---|---|
| **2nd-brain-setup** (이곳) | 시스템 overview + 컴포넌트 설치 안내 (native·container 두 옵션) | 공개 |
| **[2nd-brain-vault-guide](https://github.com/ai4radmed/2nd-brain-vault-guide)** | PARA 운영 방법론·템플릿·빈 vault 골격 — *깔린 뒤* 의 운영 | 공개 |
| **2nd-brain-vault** | 각자의 knowledge·sources 데이터 — 개인 저장소 (Syncthing 동기 권장) | 비공개 (개인) |
| **[openclaw-docker](https://github.com/ai4radmed/openclaw-docker)** | OpenClaw 본가 fork — container 모드 자산 (Dockerfile·compose·setup.sh) | 공개 |
| **[2nd-brain-docker](https://github.com/ai4radmed/2nd-brain-docker)** | 과거 Claude Code 컨테이너화 시도의 박물관 보관 자산 (참고용) | 공개 |

비유:

- **setup** = 건물을 짓는 절차서
- **vault-guide** = 건물 안에서의 생활 규칙
- **vault** = 그 건물에서 살아가는 한 사람의 살림살이
- **openclaw-docker** = 건물의 *컨테이너 변형* 설계도 (선택 옵션)
- **2nd-brain-docker** = *과거 시도의 박물관* (대비 자료)

## 4. 컴포넌트 설치

| 컴포넌트 | 역할 | 설치 안내 |
|---|---|---|
| **OpenClaw 게이트웨이** | Runtime control plane — Telegram 입구·cron·다중 에이전트 워크스페이스 통합 | [native](./openclaw-native.md) · [container](./openclaw-container.md) |

향후 추가 예정: brain-pdf (PDF 파서)·webmail-watch 등.

### OpenClaw — native vs container 결정 가이드

둘 다 같은 게이트웨이를 띄우지만 셋업 비용과 격리 수준이 다르다.

|  | native | container |
|---|---|---|
| **셋업 비용** | 가장 빠름 — 한 줄 인스톨러 | Docker 설치 + 이미지 빌드 (~수 분) |
| **격리** | 호스트 fs·네트워크 직접 사용 | 컨테이너 boundary |
| **데이터 위치** | `~/.openclaw/` (호스트) | `~/.openclaw/` (호스트, bind-mount) |
| **업데이트** | `openclaw update` | 이미지 재빌드 |
| **권장 상황** | 본인 머신, 영속 운영, *낮은 진입장벽 우선* | 데모·테스트·다중 인스턴스, *호스트 오염 회피 우선* |

처음 깔아 본다면 **native** 가 가장 단순하다. 컨테이너는 prod 환경을 흔들지 않고 데모·테스트 해보고 싶거나 공유 호스트 (VPS 등) 에서 깔끔한 boundary 가 필요할 때 적합.

## 5. 더 깊이

| 주제 | 위치 |
|---|---|
| PARA·동반 노트·브레인화 운영 방법론 | [2nd-brain-vault-guide](https://github.com/ai4radmed/2nd-brain-vault-guide) |
| OpenClaw 공식 문서 | <https://docs.openclaw.ai> |
| OpenClaw 본가 fork (container 자산 정본) | [ai4radmed/openclaw-docker](https://github.com/ai4radmed/openclaw-docker) |
| BASB 원전 | Tiago Forte, *Building a Second Brain* (Atria Books, 2022) |

## 작성 약속

각 안내 문서의 명령은 모두 **한 줄씩 그대로 복사·붙여넣기 가능** 한 형태로 작성한다 (`\` 줄바꿈 없음).
