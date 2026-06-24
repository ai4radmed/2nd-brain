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
| 3 AI 검증 | diff 초과 페이지만 Claude 판정(docling.md↔mineru.md 비교, 필요 시 페이지 이미지) → `refined.md` | **Claude Code (`refine` 스킬)** | **미적용** | `_parse/refined.md` |
| 4 지식화 | refined.md → PARA 분류·동반 노트·링크 | **Claude Code (`brainify` 스킬)** | **미적용** | `knowledge/<para>/<name>.md` |

- **이름 = `2nd-brain-parser`(우산) = extract(pre) + refine(post)**. extract=결정형(docling+mineru+diff, 컨테이너+parser-drain host timer), refine=비결정형(diverge 비전검증→refined.md, Claude Code 스킬). refine 까지가 "파싱"의 경계 — 그 다음 PARA·노트화는 brainify. (2026-05-26 분리: Phase 2=extract, Phase 3=refine, Phase 4=brainify.)
- **핸드오프 = 파일 마커**: extract → `_parse/{docling,mineru,diff}.json`(이미지는 `_parse/ocr.md`, §이미지 OCR) / refine → `_parse/refined.md`(멱등 완료 마커) / brainify → 동반 노트 frontmatter `parse:`. 각 단계는 앞 단계의 산출 파일 존재만 보고 재개(중단·다기기 동기 안전).
- verdict=match/single 은 refine 이 docling 자동승격(LLM 0), diverge 만 Claude 비전검증. diverge 는 보수적 임계(false-positive 흔함) → **턴당 1문서**로 fan-out 차단.
- **자동화 단계**: extract 는 이미 무인(parser-drain systemd timer). refine·brainify 무인화는 **`brain-drain` host timer**(`automation/brain-drain/`, 2026-05-26 구축) — extract 와 대칭. Phase R: refine `match/single`=`refine.py promote`(LLM 0), `diverge`=`claude -p "/refine --headless"`(vision). Phase B: `claude -p "/brainify --headless"`. 항목당+드레인당 비용상한, `/cron` 토글. **opt-in**: 검증 후 `systemctl --user enable --now brain-drain.timer` 하기 전까진 수동(`/refine`→`/brainify`)이 그대로 유효.
- ※ 현재 `gmail-label-actions` 는 **capture-only**(스레드 `_thread.md` + 첨부 *원본* 저장; 파싱·앵커 0). 표 Phase 1 의 `parse: pending` 앵커는 *목표* 추가분.
- ※ 구 `brainify-inbox` 스킬이 extract+refine+brainify 를 단일 스킬로 통합 수행했음(2026-05-13). refine 로직(refined.md 규약)의 원본 — 위 3-스킬 분리로 대체됨(supersede 예정).
- Phase 2(결정형, 추론 0) = 게이트웨이 밖 데몬. 상한 없는 (A)가 감시 없는 표면에선 합법.
- Phase 3(품질 검증) = 게이트웨이 아닌 Claude Code 가 제자리. 게이트웨이 역할은 감지·큐잉·알림으로 축소.

## 포맷별 엔진 — 파서 vs 전략 경계

- **포맷→변환은 파서 권위(전략 재구현 X)**: `parse-docling <파일>` 이 확장자 보고 자동 처리 — hwp/doc/rtf/odt→docx · ppt/odp→pptx · xls/ods→xlsx (LibreOffice 변환→docling), pdf·docx·pptx·xlsx 는 docling 직접. PDF 는 LibreOffice 경유 안 함(CJK 글리프 손상). 전략은 호출만.
- **포맷→엔진정책은 전략 권위**: `mineru` 는 **PDF 전용**(`diff` 도 docling↔mineru 라 PDF 에서만 성립). 따라서 Phase 2 는 포맷 의존:

| 포맷 | Phase 2 엔진 | Phase 3 |
|---|---|---|
| **PDF** | docling + mineru + diff (두 엔진 발산 의미있음) | diff 초과 페이지 Claude 검증 |
| **office·hwp·odf·xlsx** | docling 단일 (mineru N/A·diff 불가) | 발산신호 없음 → 검증 옵션(표 spot-check) |
| **이미지 (png·jpg·jpeg·webp·tiff)** | 로컬 OCR 단일 — **device-adaptive**(GPU 머신=VLM / CPU 머신=classic, 아래 §) → `_parse/ocr.md` | 단일 출력(diff 불가) → verdict=single 자동승격; 한글 표 의심 시 spot-check |

**핸드오프**: 동반 노트 frontmatter `parse:` 상태기계 — `(없음)→pending→parsed-pending-verify→<경로 확정>`. 각 단계는 앵커만 보고 재개(멱등, 중단·다기기 동기 안전).

**잔여 위험**: Phase 3 가 게이트웨이 턴이면 diff 임계 헐거울 때 fan-out 재발 → **턴당 1문서 + 앵커 게이트**, 또는 Claude Code 로 빼면 소멸.

## 이미지 OCR — device-adaptive (로컬 전용)

낱장 이미지(스캔본·캡처·사진의 일정표/공문/표)는 문서 포맷 경로(docling/mineru)에 안 물린다 — **별도 OCR 레인**으로 처리한다. 파서에 `parse-ocr <이미지>` 능력을 두고(파서 권위), 전략은 엔진·디바이스 정책만 정한다.

- **로컬 전용 — 외부 API 0.** `2nd-brain-parser` 의 air-gap 원칙(재무·민감 자료 leak 방지)을 OCR 레인도 그대로 따른다. 클라우드 OCR(Upstage·Gemini·Google·Azure 등)은 **불채택** — 무료 티어라도 (1) 외부 전송, (2) Gemini 무료티어는 데이터 *학습* 사용, (3) Pro·증량·학습제외가 유료(유료 가능성)라 air-gap·"유료 가능성 배제" 두 원칙에 위배. 로컬 OSS OCR 이 2026 기준 한글 표에서 클라우드와 사실상 동급(OmniDocBench 96점대)이라 성능 손실도 미미.
- **device-adaptive — 같은 코드, 디바이스만 머신별 주입.** 동기 자산(이 문서·compose·SKILL)엔 GPU/디바이스/엔진을 박지 않는다(머신-specific 키워드 금지). 디바이스·엔진은 **머신별 env/로컬 설정으로 주입**(gog keyring·`/cron` 토글이 머신로컬인 것과 동일 패턴).

| 머신 클래스 | 디바이스 | 권장 엔진 | 특성 |
|---|---|---|---|
| **GPU 머신** | `cuda` | **VLM** (PaddleOCR-VL 등) | 한글 표 최강·빠름(초 단위). VRAM 점유 시 CPU 폴백 |
| **CPU 머신** (GPU 부재·타 모델 점유) | `cpu` | **classic** (PP-StructureV3 / docling+EasyOCR) | VLM 보다 CPU 에서 훨씬 가벼움(장당 수 초). VLM 도 돌지만 느림(장당 수십 초~분) |

- **비동기라 속도는 비차단.** OCR 은 extract 단계(parser-drain/brain-drain 타이머)에서 돌므로 CPU 머신의 느림이 대화형 UX 를 막지 않는다. 보통은 단일발화 머신에서 처리되고, GPU 머신이 발화 머신이면 자동으로 빠른 경로.
- **산출·핸드오프**: 이미지 extract → `_parse/ocr.md`(단일 엔진, diff 불가 — office docling 단일과 동형). 이후 refine 가 `verdict=single` 로 자동승격(→`refined.md`), 한글 표 의심 시에만 spot-check. brainify 는 동일하게 `refined.md` 소비.
- **호출**: `brain-pdf parse-ocr <이미지>` (CLI 콘솔명 = `brain-pdf`, setup 문서의 `2nd-brain-parser <cmd>` 표기는 outdated). 산출 dict 는 parse-mineru 동형(engine=`ocr:<backend>`).
- **상태 (2026-06-24)**: ✅ **entrypoint.py 에 `parse-ocr` 구현·검증** — MinerU 가 이미지를 1페이지로 받음. 한글 전국포럼 일정표 PNG(831×1183)로 검증: CPU pipeline 28초, 발표자 표 정확 추출(비전 다운스케일로 막혔던 그 파일). 디바이스/엔진은 `PARSER_OCR_BACKEND` env(기본 `pipeline`=CPU, GPU 머신은 `vlm-vllm`/`vlm-transformers` 주입)로 어댑터. **잔여**: (1) ghcr 이미지 rebuild+push(현재 prebuilt 는 구버전 entrypoint — 임시로 수정 entrypoint.py bind-mount 로 사용 가능), (2) parser-drain 에 이미지 확장자→parse-ocr 배선(현재 capture-only), (3) GPU 머신 vlm 백엔드 env 셋업(선택, pipeline 으로도 충분).

## 관련

- [`2nd-brain-parser-setup.md`](2nd-brain-parser-setup.md) · `brainify` 스킬(실행 권위)
- 실측 수치·decouple 기록 = 각 vault `knowledge/02_areas/brain-system/`(개인 운영, 공개 repo 엔 없음)
