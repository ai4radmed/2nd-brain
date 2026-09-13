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

- **포맷→변환은 파서 권위(전략 재구현 X)**: `parse-docling <파일>` 이 확장자 보고 자동 처리 — doc/rtf/odt→docx · ppt/odp→pptx · xls/ods→xlsx (LibreOffice 변환→docling), pdf·docx·pptx·xlsx 는 docling 직접. PDF 는 LibreOffice 경유 안 함(CJK 글리프 손상). 전략은 호출만.
- **⚠ hwp/hwpx 예외 — 컨테이너 우회, 호스트 추출(2026-07-03)**: 컨테이너의 hwp→docx→docling 경로는 headless soffice user-프로필 미초기화로 대량 실패(inbox 91건 `.parse-error`)했고 hwpx 표를 H2Orestart 가 버렸다. → **hwp/hwpx 는 호스트 `parser-drain/hwp_refine.py` 로 추출**(호스트 LibreOffice+H2Orestart(user 프로필)+pandoc 은 검증됨). hwpx=**OWPML XML 직독**(LibreOffice 완전 우회·무손실 표), hwp=soffice→docx→**pandoc gfm**(병합셀 clean HTML). HWP 는 단일소스(mineru N/A·diff 불가)라 refine 이 no-op → 추출=refine 을 한 번에 하고 `_parse/refined.md` 를 직접 생산(컨테이너·refine 둘 다 우회, brainify `_refined()` 가 소비). 라우팅=`parser-drain.sh`(hwp 전용 호스트 루프). 로직 원본=`radsafety-laws/scripts/_parse_attachments.py`. **잔여 예외**: 일부 구형 hwp 는 H2Orestart 가 "Unspecified Application Error" 로 거부 → 한컴 한글로 `.hwpx` 수동 변환 후 OWPML 경로(radsafety 와 동일한 문서화된 최소 예외).
- **★ 같은 문서가 hwp/hwpx + pdf 로 함께 올 때 — 파싱은 hwpx, PDF 는 보관(2026-09-13 신설)**: 지금까지 "hwpx 우선" 은 *구형 hwp 가 거부될 때의 예외*로만 문서화돼 있었으나, **hwp·pdf 병존은 정상 경로로 규정한다**. 근거는 같은 문서군을 두 경로로 돌린 실측(원안위 원자력안전종합계획 1차 hwpx vs 3차 pdf):
  - **텍스트·표는 hwpx 압승.** PDF 경로 산출물에 ① 글자 사이 공백 삽입(`제 3 차`·`「 원자력안전법 」 제 3 조` → **조문 grep 실패**) ② **읽기 순서 역전**(원문 "5년마다 … 수립" 이 `- 년마다 …` / `- … 위해 5` 두 줄로 쪼개져 뒤집힘 = 문장 파손)이 실재했다. PDF 는 인쇄 포맷이라 읽기순서·표경계·제목레벨을 파서가 *추론*해야 하고 그 추론이 틀린 자리가 이것들이다. OWPML 은 그 정보가 파일에 명시돼 추론이 없다.
  - **비용도 hwpx 가 싸다** — OWPML 직독은 초 단위 CPU, PDF 는 docling+mineru+diff(+diverge 시 Claude 비전검증).
  - **따라서 중요 문서는 한컴에서 `.hwpx` 로 저장해 그쪽을 파싱**하고, PDF 는 *파싱하지 않고 보관*한다(시각 참조용). 원본은 셋 다 같은 사안 폴더에 보존.
  - **단, 원본성(정본)과 파싱 경로는 별개 축** — 확정·서명본이 PDF 뿐이면 정본은 PDF, hwpx 는 파싱용 보조다. 이때 동반 노트 `sources:` 는 PDF, `parse:` 만 hwpx `_parse` 를 가리킨다.
  - 크기 게이트(`is_bulk()`)는 **포맷과 무관** — 24MB hwpx 가 `.parse-skipped` 된 실례가 있다. hwpx 라고 무조건 파싱되지 않는다.
- **★ hwpx 그림 — 마커 + 추출(2026-09-13 구현)**: OWPML 텍스트 추출은 그림을 **소리 없이 버린다**. PDF 경로(docling)가 `<!-- image -->` 를 남기는 것과 달리 흔적조차 없어, **도식이 있었다는 사실 자체를 잃는다** — 실측: 제1차 원자력안전종합계획 hwpx 의 내용 도식 2개(**계획 위상도** · **5개년 로드맵 부록**)가 통째로 유실됐고 `refined.md` 의 이미지 표기는 0건이었다. *못 읽는 것*보다 *놓친 줄 모르는 것*이 진짜 위험이다.
  - → `hwp_refine.py` 가 `Contents/content.hpf` 의 `<opf:item id href>` 매핑으로 **BinData 를 `_parse/images/` 로 추출**하고, 본문 그림 위치에 `<!-- image: images/imageN.jpg 2082×2910 -->` 마커를 남긴다. frontmatter 에 `images: N`.
  - **장식 제외**: 긴 변 `MIN_IMG_PX`(=200px) 미만은 마커를 내지 않는다(파일은 추출). 실측상 72×72 글머리 아이콘 하나가 12번 반복돼 본문을 덮었다. 크기 sniff 실패 시엔 마커를 낸다(놓치는 쪽보다 시끄러운 쪽이 안전).
  - 소비 측: 추출된 이미지는 `Read` 로 직접 볼 수 있다(멀티모달). 즉 **PDF 없이도 도식 복구가 가능**하며, PDF 가 주는 추가 가치는 *페이지 맥락*(그림 주변 텍스트까지 통째)뿐이다.
- **★ hwp(구형) 그림 — 중간 docx 에서 추출(2026-09-13 구현)**: hwp 경로에도 같은 유실이 있으나 **사라지는 지점이 다르다** — soffice 가 만든 docx 에는 그림이 `word/media/` 에 **멀쩡히 남아 있고 pandoc 이 버린다**. LibreOffice 가 그림을 `w:pict` 로 감싸 내보내 pandoc docx 리더가 건너뛰기 때문이며, `--extract-media` 를 줘도 마크다운 참조는 0건이다. → `_docx_images()` 가 `word/_rels` 로 **문서순** 해석해 `_parse/images/` 로 추출한다.
  - **위치는 최대한 살린다**: pandoc 이 일부 그림은 markdown `![]()` 가 아니라 **원시 HTML** `<img src="media/imageN.png">` 로 내보낸다(그래서 `![` grep 이 0건이었다 — 없는 게 아니라 형태가 달랐다). 그 참조를 `images/` 로 **relink** 하면 위치가 그대로 보존된다. 실측 h2: 표 안 그림 포함 2개 전부 인라인 보존, 인벤토리 0.
  - **위치가 안 잡힌 나머지만** 본문 끝 `## 그림 (문서순 · 본문 위치 미상)` 인벤토리로. hwpx 와 달리 앵커가 없어 위치 재현이 불가한 경우가 남는다 — 목적은 위치가 아니라 **"그림이 있었다"는 사실과 실물의 보존**이다.
  - 그림 0 인 문서엔 `images/` 를 만들지 않는다(빈 폴더 금지).
- **★ hwp → hwpx 자동변환은 하지 않는다 (2026-09-13 검토·기각)**: "중요 문서는 hwpx" 규칙 때문에 hwp 를 hwpx 로 자동변환하고 싶어지지만, 실측·논리 모두 부정적이다.
  - **LibreOffice 로는 애초에 못 만든다** — `soffice --convert-to hwpx` = `no export filter`, 명시 필터(`hwpx:HwpX Export`)를 줘도 저장 실패(`Io/Parameter 0x81a`), **odt→hwpx 도 동일**. H2Orestart 는 이름대로 **import 전용**(캐시에 `import_N.log` 만 존재).
  - **설령 됐어도 의미가 없다** — `hwp →(LibreOffice importer)→ hwpx` 는 지금의 `hwp→docx→pandoc` 과 **같은 관문**을 통과하므로 복구되는 정보가 0이고 변환만 한 번 더 낀다. **hwpx 의 값어치는 확장자가 아니라 "한글이 직접 쓴 파일"이라는 데서 나온다.**
  - **한글 COM 은 WSL2 에서 실제로 호출된다** — `HWPFrame.HwpObject` 등록됨(한컴오피스 2024, `13,0,0,564`), WSL interop 으로 `powershell.exe` 경유 생성·`Quit` 정상. 단 ⓐ **UNC(`\\wsl.localhost\...`) 경로는 못 연다** → Windows 로컬 temp 경유 복사 필요, ⓑ `RegisterModule("FilePathCheckDLL","FilePathChecker")` 가 `False` 인 동안 **`SaveAs` 가 예외 없이 조용히 False** 를 돌려준다(보안 DLL `regsvr32` 1회 등록 필요).
  - **무인 자동화엔 넣지 않는다** — 한글은 GUI 앱이라 **Windows 사용자 세션에 의존**한다. parser-drain 은 밤에도 도는 systemd 무인 루프인데 잠금·로그아웃·재부팅 직후엔 COM 이 *조용히* 실패하고, 양 머신(ai4lt·kimbi)에 한글+DLL 이 모두 있어야 결과가 일치한다. → **중요 문서는 Dr. Ben 이 한컴에서 `.hwpx` 로 저장**(기존 수동 예외 유지), 일반 hwp 는 위 docx 이미지 추출로 충분.
- **포맷→엔진정책은 전략 권위**: `mineru` 는 **PDF 전용**(`diff` 도 docling↔mineru 라 PDF 에서만 성립). 따라서 Phase 2 는 포맷 의존:

| 포맷 | Phase 2 엔진 | Phase 3 |
|---|---|---|
| **PDF** | docling + mineru + diff (두 엔진 발산 의미있음) | diff 초과 페이지 Claude 검증 |
| **office·odf·xlsx** (hwp 제외) | docling 단일 (mineru N/A·diff 불가) | 발산신호 없음 → 검증 옵션(표 spot-check) |
| **hwp·hwpx** | **호스트 추출**(컨테이너 우회) — hwpx=OWPML 직독(+그림 `_parse/images/` 추출·위치 마커), hwp=soffice→pandoc(+중간 docx 그림 추출·relink) → `_parse/refined.md` 직접 | 단일소스 → refine no-op(자동 완료). 구형 hwp 거부 시 한컴 hwpx 수동. **pdf 병존 시 hwpx 파싱·pdf 보관** |
| **이미지 (png·jpg·jpeg·webp·tiff)** | 로컬 OCR 단일 — **device-adaptive**(GPU 머신=VLM / CPU 머신=classic, 아래 §) → `_parse/ocr.md` | 단일 출력(diff 불가) → verdict=single 자동승격; 한글 표 의심 시 spot-check |
| **오디오 (m4a·mp3·wav·ogg·opus·aac·amr)** | **호스트 전사**(faster-whisper 로컬 GPU, 아래 §) → `_parse/refined.md` 직접 | 단일소스 → refine no-op(HWP 동형). whisper venv 부재 머신은 루프째 skip |

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
- **상태 (2026-06-24)**: ✅ **구현·배포 완료**. (1) `entrypoint.py` `parse-ocr`(v0.3.0) — MinerU 가 이미지를 1페이지로 받음, 디바이스/엔진은 `PARSER_OCR_BACKEND` env(기본 `pipeline`=CPU, GPU 머신은 `vlm-vllm`/`vlm-transformers`)로 어댑터. (2) ghcr 이미지 발행 — overlay 빌드(검증된 base + 신 entrypoint), `:latest`+`:2026.06.24` push, compose digest 핀 `sha256:96f1919b…` 로 갱신. (3) `parser-drain.sh` 이미지 루프 배선 — png/jpg/jpeg/webp/tiff → parse-ocr → `ocr.json`, `_parse/` 하위(mineru 추출 figure) 제외. 검증: 한글 전국포럼 일정표 PNG end-to-end 드레인 → `ocr:pipeline ocr.json`, 발표자 표 정확. **잔여(선택)**: 타 PC(노트북) `git pull` 로 신 digest 전파 · GPU 머신 vlm 백엔드 env 셋업(pipeline 으로도 충분).

## 오디오 전사 — 로컬 전용 (폰 음성 캡처)

폰(갤럭시 S25 FE) 음성녹음 → SyncThing 단방향 ingress(볼트 밖 receive-only) → inbox 복사 → **로컬 faster-whisper 전사**의 오디오 레인. 문서 포맷 경로(docling/mineru)에 안 물리는 세 번째 레인이다.

- **로컬 전용 — 외부 API 0.** 이미지 OCR 과 동일 원칙: 진료·회의 녹음은 민감 정보라 클라우드 STT(Google·OpenAI API 등) 불채택. faster-whisper `large-v3`(CTranslate2)가 한국어 전사 로컬 최상급.
- **호스트-측 (컨테이너 우회) — HWP 선례.** 오디오는 단일소스(mineru N/A·diff 불가)라 refine 이 no-op → 추출=refine 을 한 번에 하고 `_parse/refined.md`(타임스탬프 라인 전사)를 직접 생산. 실행 = `parser-drain/audio_refine.py`(호스트 `~/.venvs/whisper` venv), 라우팅 = `parser-drain.sh` 오디오 루프.
- **device-adaptive — venv 존재가 어댑터.** 동기 자산에 머신 키워드를 박지 않는다: whisper venv 있는 머신만 루프 실행(GPU 점유 노트북 등은 자동 skip). 모델·디바이스는 env(`WHISPER_MODEL`/`WHISPER_DEVICE`/`WHISPER_COMPUTE`)로 주입, CUDA 실패 시 CPU int8 자동 폴백.
- **ingress 규약**: SyncThing receive-only 폴더(`~/phone-ingress/voice`, 기본값 — `AUDIO_INGRESS` env)에서 **move 금지**(SyncThing 이 복원) → **copy + ledger**(`~/.local/state/audio-ingress.ledger`, `이름:크기` 키 — brainify 가 inbox 밖으로 옮겨도 재복사 안 함). 복사 시 공백→`_` 정규화.
- **선별 게이트**: 동기·전사까지 *자동*(로컬이라 안전), **PARA 편입은 brainify 실행(=Dr. Ben 지시) 시점** — 사적 녹음은 그때 삭제.
- **Meet 녹화 레인 (2026-08-03 추가)**: 폰 ingress 옆에 **Drive ingress** 를 둔다 — 회의 녹화(Google Meet)는 주최자 Drive `Meet Recordings` 에 자동 저장되므로, `drive_meet_ingress.py` 가 그 폴더를 훑어 inbox 로 내린다(fileId ledger 멱등). 전사·편입은 기존 오디오 레인이 그대로 처리 — **경계는 "Drive→inbox" 까지**. 어댑터는 `DRIVE_ACCOUNT` env(미설정 머신은 skip, venv 어댑터와 동일 규약). **비디오(mp4·mkv·webm)를 오디오 루프 확장자에 편입** — faster-whisper 가 PyAV 로 오디오 트랙을 직접 디코드하므로 ffmpeg 추출 단계는 불필요. 파일명은 vault frontmatter `meet_link:` 역인덱스로 회의 코드→회의체를 풀어 `YYYY-MM-DD_<회의체>_녹화.mp4` 로 정규화(매핑 실패 시 코드 그대로 — 유입은 막지 않음).
- **상태 (2026-07-13)**: ✅ kimbi 구현·검증 완료 — RTX 5080(Blackwell sm_120)에서 CTranslate2 4.8.1 정상, 한국어 테스트(의학 용어 포함) 전사 무결, ingress→inbox→refined.md 드레인 end-to-end 통과. 잔여: 폰 Syncthing-Fork 페어링(Dr. Ben), 실녹음 1건 end-to-end.

## 관련

- [`2nd-brain-parser-setup.md`](2nd-brain-parser-setup.md) · `brainify` 스킬(실행 권위)
- 실측 수치·decouple 기록 = 각 vault `knowledge/02_areas/brain-system/`(개인 운영, 공개 repo 엔 없음)
