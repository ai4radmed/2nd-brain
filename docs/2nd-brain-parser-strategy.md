# 2nd-brain 파싱 전략 — 무제한 작업을 watchdog 뒤에 두지 않기

> 파서를 *어디서 돌릴지*. 띄우는 법=[`2nd-brain-parser-setup.md`](2nd-brain-parser-setup.md), 분류·노트화=`brainify` 스킬.

**원칙**: 상한 없는 작업을 watchdog(자동발화 게이트웨이) 뒤에 두지 않는다. 일을 예측 가능한 표면으로 밀어 감시 목록에서 지운다.

**왜**: watchdog 은 LLM 백엔드 JSONL 하트비트를 본다. 셸 서브프로세스는 *끝나야* surface → 실행 중 출력 0 → 죽는다. 범인은 "AI 추론"이 아니라 **침묵하는 블로킹 자식**. 파싱은 페이지 수에 비례해 상한이 없으니 timeout 을 키워도 언젠가 넘긴다.

| "길다"의 종류 | watchdog |
|---|---|
| (A) 침묵 블로킹 서브프로세스 (docling/mineru) | **걸림** |
| (B) 최상위 에이전트 추론 (토큰 계속 출력) | 안 걸림 |
| (C) 중첩 LLM 자식 (`--print`) | **걸림** |

**기각**: timeout↑(상한 없어 무의미·진짜 행 늦게 잡음) · 건수 예산(단건 latency 못 막음) · 하트비트 주입(서브프로세스 stdout 전파 안 됨).

## 3-phase 배치

| Phase | 일 | 표면 | watchdog | 앵커 결과 |
|---|---|---|---|---|
| 1 트리거 | inbox 신규 감지 → 앵커만 찍고 종료 | gmail=label-actions 인라인 · 수동드롭=host 스캔 | 노출되나 초 단위 | `parse: pending` |
| 2 기계 파싱 | 포맷별 파싱(PDF=docling+mineru, 그외=docling) → `_parse/{docling,mineru,diff}` | systemd 타이머 + warm 데몬 | **미적용** | `parse: parsed-pending-verify` |
| 3 AI 검증 | diff 초과 페이지만 Claude 판정(docling.md↔mineru.md 비교, 필요 시 페이지 이미지) → `refined.md` + 동반 노트 | **Claude Code** | **미적용** | `_parse` 경로 확정 |

- **현 단계 = Phase 2+3 를 `brainify`(Claude Code, attended)에서 병합 실행**(지연·검증). Phase 1·2 의 자동화(게이트웨이 cron + systemd 데몬 분리)는 inbox 볼륨이 실제 병목일 때 — 그때까지 위 표는 *목표 배치도*다. (추론 0 파서는 정확도 미보장 → 검증 필수, 그 검증을 attended brainify 가 이미 수행하므로 자동 분리는 아직 불필요.)
- Phase 2(결정형, 추론 0) = 게이트웨이 밖 데몬. 상한 없는 (A)가 감시 없는 표면에선 합법.
- Phase 3(품질 검증) = 게이트웨이 아닌 Claude Code 가 제자리. 게이트웨이 역할은 감지·큐잉·알림으로 축소.

## 포맷별 엔진 — 파서 vs 전략 경계

- **포맷→변환은 파서 권위(전략 재구현 X)**: `parse-docling <파일>` 이 확장자 보고 자동 처리 — hwp/doc/rtf/odt→docx · ppt/odp→pptx · xls/ods→xlsx (LibreOffice 변환→docling), pdf·docx·pptx·xlsx 는 docling 직접. PDF 는 LibreOffice 경유 안 함(CJK 글리프 손상). 전략은 호출만.
- **포맷→엔진정책은 전략 권위**: `mineru` 는 **PDF 전용**(`diff` 도 docling↔mineru 라 PDF 에서만 성립). 따라서 Phase 2 는 포맷 의존:

| 포맷 | Phase 2 엔진 | Phase 3 |
|---|---|---|
| **PDF** | docling + mineru + diff (두 엔진 발산 의미있음) | diff 초과 페이지 Claude 검증 |
| **office·hwp·odf·xlsx** | docling 단일 (mineru N/A·diff 불가) | 발산신호 없음 → 검증 옵션(표 spot-check) |

**핸드오프**: 동반 노트 frontmatter `parse:` 상태기계 — `(없음)→pending→parsed-pending-verify→<경로 확정>`. 각 단계는 앵커만 보고 재개(멱등, 중단·다기기 동기 안전).

**잔여 위험**: Phase 3 가 게이트웨이 턴이면 diff 임계 헐거울 때 fan-out 재발 → **턴당 1문서 + 앵커 게이트**, 또는 Claude Code 로 빼면 소멸.

## 관련

- [`2nd-brain-parser-setup.md`](2nd-brain-parser-setup.md) · `brainify` 스킬(실행 권위)
- 실측 수치·decouple 기록 = 각 vault `knowledge/02_areas/brain-system/`(개인 운영, 공개 repo 엔 없음)
