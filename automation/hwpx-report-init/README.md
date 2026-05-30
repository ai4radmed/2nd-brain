# hwpx-report-init

fillable.hwpx 를 읽어 **markdown template 자동 생성** — 정방향 워크플로우의 시작점.

## 왜 정방향인가

역방향 (markdown 먼저 → JSON 매핑) 의 함정:
- 양식 (fillable) 변경 시 markdown 수동 재구성
- placeholder 누락 가능 (markdown 작성자가 모를 수 있음)
- 양식별 markdown 양식 따로 만들어야

**정방향 (fillable = 권위 원본)**:
- fillable 갱신 → init 재실행하면 template 자동 동기
- 모든 placeholder *사전 표시* → 누락 0
- AI agent 가 *완전한 슬롯 목록* 보고 채움 — 추측 X
- 양식 (KIRAMS·KSNM·KARP) 1개 → template 자동 (동일 패턴)

상세 정책 → vault 메모리 `project_hwpx_first_policy`.

## 워크플로우 위치

```
fillable.hwpx                          ← 양식 권위
   ↓ [hwpx-report-init] ← 이 도구
markdown template (YAML 코드블록 + 본문 자유)
   ↓ AI agent / Dr. Ben 채움
채워진 markdown
   ↓ hwpx-report-fill (다른 도구)
   ↓ hwpx-fill + hwpx-multiline-fixer
산출물.hwpx
```

## 설치

표준 라이브러리만 (Python 3.10+ zipfile + 정규식).

```bash
chmod +x ~/projects/2nd-brain/automation/hwpx-report-init/init.py
```

## 사용

```bash
init.py fillable.hwpx                       # → fillable.template.md
init.py fillable.hwpx -o report.md
init.py fillable.hwpx -o report.md --overwrite

# 가이드 명시 (또는 자동 발견)
init.py fillable.hwpx -o report.md --guide knowledge/.../양식.md
```

## 형식 가이드 (Key 명세표)

양식 동반 노트의 **Key 명세표** 가 *권위* — 각 키의 *형식 가이드* 가 YAML 주석으로 자동 포함됨. 명세표 행 형식:

```markdown
| 키 | 양식 필드 | 형식 가이드 |
|---|---|---|
| `{{사업명}}` | 사업명(가칭) | 자유 텍스트 (한 줄) |
| `{{총사업비}}` | 총사업비 | `"XXX억원 (국비: YYY억원)"` 형식 필수 |
| `{{성과목표}}` | [성과목표] | multi-line (`\|`): ㅇ 헤더 + - 하위 |
```

→ 생성된 template 의 YAML 주석:

```yaml
사업명: ""  # 자유 텍스트 (한 줄)
총사업비: ""  # `"XXX억원 (국비: YYY억원)"` 형식 필수
성과목표: ""  # multi-line (`|`): ㅇ 헤더 + - 하위
```

### 가이드 자동 발견 (vault 컨벤션)

`--guide` 미지정 시 vault 경로 패턴으로 자동 추정:

```
sources/<...>/<양식폴더>/fillable.hwpx
   → knowledge/<...>/<양식폴더>.md
```

예: `sources/03_resources/한국원자력의학원/신규과제기획보고서양식/2026_..._fillable.hwpx`
→ `knowledge/03_resources/한국원자력의학원/신규과제기획보고서양식.md` 자동 발견

자동 발견 실패 시 `--guide` 명시.

## 생성되는 markdown 형식

```markdown
---
template_for: <fillable 이름>
fillable: <fillable 경로>
placeholders: 38
status: empty
---

# Fillable 양식 채움 — <name>

> 각 placeholder 의 값을 아래 YAML 코드블록에 작성하세요.
> multi-line 값은 `|` literal block scalar 사용 — 들여쓰기·줄바꿈 보존.
> 들여쓰기 규약: `ㅇ 헤더\n  - 하위` (반각 2칸 hanging).

## 값 (YAML)

\```yaml
# === Outer 셀 (메인 양식) ===
사업명: ""
총사업비: ""
…

# === Nested 표 (소요예산·연구개발 목표 등) ===
2027연구비: ""  # depth=1
…
\```

## 작업 노트 (자유)

(참고 자료·문맥·인용 등을 자유롭게. fill 시 무시됨.)
```

## 동작 원리

1. `Contents/section0.xml` 의 `{{key}}` 모두 추출 (unique, 등장 순)
2. **표 깊이 분석** — 각 placeholder 가 어느 표에 속하는지:
   - depth 0 = 외곽 표 (메인 양식 셀)
   - depth ≥ 1 = nested 표 (소요예산·연구개발·연구성과 등)
3. **셀 라벨 추정** — placeholder 앞 500자 내 `[라벨]` 패턴 (예: `[성과목표]`)
4. markdown template 생성 — outer / nested 그룹화, 셀 라벨을 주석으로

## 멀티 라인 값 작성 예

YAML 의 `|` literal block scalar 사용:

```yaml
성과목표: |
  ㅇ 번인 선량 자동추출
    - 비식별 PACS DICOM → 7B VLM OCR
    - 물리·통계 이중검증
  ㅇ DRL 국가 벤치마킹
```

→ hwpx-report-fill 이 *literal `\n` 그대로* hwpx-fill 에 전달, 이후 fixer 가 `<hp:p>` 새 문단 분리.

## 검증 (2026-05-31)

- ✓ KIRAMS 신규과제 기획보고서 양식 38 키 모두 추출
- ✓ outer 12 + nested 26 정확 분류 (depth 알고리즘 검증)
- ✓ 셀 라벨 (`[성과목표]`·`[필요성]` 등) 자동 인식

## 관련 도구

- `hwpx-report-fill` — 채워진 markdown → hwpx 산출물 (정방향 마무리)
- `hwpx-fill` — 결정형 string replace (report-fill 이 내부 호출)
- `hwpx-multiline-fixer` — fill 후 `\n` → `<hp:p>` 분리

## 변경 이력

- 2026-05-31 — 신설. KIRAMS 양식 38 키 검증. depth 알고리즘 (외곽=0, nested=1) 정합.
