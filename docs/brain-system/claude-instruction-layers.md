---
title: Claude Code 지침 계층 · 토큰 예산
date: 2026-04-24
tags: [claude-code, context-window, brain-system, meta]
---

# Claude Code 지침 계층 · 토큰 예산

Claude Code CLI 가 세션 시작 시 합쳐서 프롬프트로 전달하는 지침 계층과, "lost in the middle" 을 방지하기 위한 토큰 예산 가이드.

## 한 줄 요약

사용자가 통제 가능한 지침(CLAUDE.md + memory)의 **합계를 5–10K 토큰, 경고선 20K 토큰** 으로 유지해야 규칙 준수 집중력이 살아있다.

---

## 지침 계층 (7층)

넓은 범위 → 좁은 범위, 충돌 시 좁은 범위 우선. 덮어쓰기가 아니라 연결(concatenate).

| # | 층 | 위치 | 비고 |
|---|---|---|---|
| 1 | **System prompt** | Claude Code 내장 | 불변, 수정 불가 |
| 2 | **Enterprise managed** | 조직 배포 policy | 조직이 있는 경우만, 개인이 제외 불가 |
| 3 | **User memory** | `~/.claude/CLAUDE.md` | 당신의 모든 프로젝트 공통 |
| 4 | **Auto memory** | `~/.claude/projects/<프로젝트>/memory/` | Claude 가 자동 학습·저장 (MEMORY.md 인덱스 + 개별 파일) |
| 5 | **Project memory** | 프로젝트 루트 `CLAUDE.md` | git tracked, 팀 공유 |
| 6 | **Local memory** | `CLAUDE.local.md` | gitignore, 개인용. 현재는 deprecated, `@import` 로 대체 권장 |
| 7 | **Subdirectory CLAUDE.md** | 하위 폴더의 `CLAUDE.md` | 해당 폴더에서 작업 시 on-demand 로드 |

### 보조 메커니즘

- **`@경로` import** — CLAUDE.md 안에서 `@./docs/style.md` 같은 식으로 다른 파일 참조. 최대 5단계 재귀.
- **`/memory` 명령어** — 현재 세션에 로드된 CLAUDE.md 파일 목록 조회·즉시 편집.
- **Auto memory 토글** — `/memory` 에서 on/off 가능 (기본 on).

---

## 세션 "고정 오버헤드"

사용자가 직접 통제할 수 없는 부분만 이미 상당한 크기.

| 구성요소 | 대략 토큰 | 통제 가능? |
|---|---:|---|
| System prompt (Claude Code 내장) | ~8–12K | ❌ |
| Tool 정의 (MCP 포함) | ~15–25K | 일부 (MCP·서브에이전트 정리) |
| CLAUDE.md 전 층 | 가변 | ✅ |
| Auto memory (MEMORY.md + 활성 항목) | 가변 | ✅ |
| 대화 기록·도구 결과 | 가변 | 부분적 |

**고정 오버헤드만 해도 30K 내외**. 사용자가 손댈 수 있는 건 CLAUDE.md·memory·불필요한 도구 결과 누적 회피 정도.

---

## 집중력과 컨텍스트 크기

경험칙 (Claude 계열 모델 기준):

| 총 context | 집중도·지시 준수 |
|---|---|
| **~20K 이하** | 최적. 모든 줄이 "살아있음" |
| **20K–50K** | 아직 매우 좋음. 실무 스위트 스팟 |
| **50K–200K** | 준수하나 "중간 위치" 지시는 희석됨 (lost-in-the-middle) |
| **200K–500K** | 긴 코드 탐색·요약엔 OK, 세세한 규약 준수는 약화 |
| **500K–1M** | 검색·회상은 되지만 **규칙 엄수·우선순위 판단은 신뢰도 하락** |

> Opus 4.7 의 1M 창은 "담을 수 있는 한도" 이지 "집중할 수 있는 한도" 가 아니다.

---

## 권장치 (CLAUDE.md + memory 합계)

- **이상적**: 총 **5K 토큰 이하**
- **허용**: **10K 토큰**
- **경고선**: **20K 토큰** 초과 — 규칙 많아질수록 모순·중복 증가, 모델이 우선순위 혼동

한글은 영어 대비 1.3–1.5배 토큰 소모. 한글 3500자 ≈ 4–5K 토큰.

---

## 비대화 대응 4가지

1. **계층 분리** — CLAUDE.md 는 "상시 필요한 규약" 만. 상세 워크플로우는 `workflows/*.md` 로 이관하고 필요 시 `@import` 또는 Read.
2. **하위디렉토리 CLAUDE.md** — 특정 영역 전용 규칙은 그 폴더에 두면 해당 폴더 작업 시에만 로드됨. 예: `knowledge/03_resources/PET/CLAUDE.md`.
3. **`@import`** — 큰 문서는 본 CLAUDE.md 밖에 두고 필요한 섹션만 import.
4. **Memory 청소** — `/memory` 로 주기적으로 오래된·틀린 항목 제거. MEMORY.md 인덱스 200줄 제한 주의.

---

## 관련 노트

- [[README]] — brain-system 개요 및 진화 기록
