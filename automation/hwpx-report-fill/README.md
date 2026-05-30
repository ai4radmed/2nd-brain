# hwpx-report-fill

채워진 markdown template → hwpx 산출물 — **정방향 워크플로우의 마무리**.

## 동작 요약

1. markdown frontmatter 의 `fillable:` 로 양식 자동 식별
2. **YAML 코드블록** 의 키-값 추출 (multi-line `|` literal 지원)
3. 각 키에 `{{...}}` 자동 wrapping
4. **hwpx-fill** → string replace fill
5. **hwpx-multiline-fixer** → literal `\n` → `<hp:p>` 새 문단 분리
6. 최종 hwpx 산출물

## 워크플로우 위치 (정방향 마무리)

```
fillable.hwpx (양식 권위)
   ↓ hwpx-report-init
markdown template
   ↓ AI agent / Dr. Ben 이 YAML 블록 채움
채워진 markdown
   ↓ [hwpx-report-fill] ← 이 도구
   ↓   1. YAML 블록 추출
   ↓   2. hwpx-fill 호출
   ↓   3. hwpx-multiline-fixer 호출
산출물.hwpx
   ↓ Dr. Ben 한컴 (보안 낮음) → KIRAMS 제출
```

## 설치

PyYAML 필요 (대부분 설치돼 있음). 그 외 표준 라이브러리만.

```bash
chmod +x ~/projects/2nd-brain/automation/hwpx-report-fill/fill.py
python3 -c "import yaml; print(yaml.__version__)"   # 설치 확인
```

## 사용

```bash
# 기본 — frontmatter 의 fillable 자동 사용
fill.py template.md -o output.hwpx

# fillable 명시 override
fill.py template.md -o output.hwpx --fillable other.hwpx

# fixer 생략 (literal \n 그대로 — 한 줄로 표시됨)
fill.py template.md -o output.hwpx --skip-fixer
```

## markdown 형식 — `hwpx-report-init` 가 생성한 것 그대로

```markdown
---
fillable: /path/to/fillable.hwpx
---

\```yaml
사업명: "VLM 활용 핵의학 영상검사품질·환자선량 최적화 플랫폼 개발"
총사업비: "300 백만원"
성과목표: |
  ㅇ 번인 선량 자동추출
    - 비식별 PACS DICOM → 7B VLM OCR
  ㅇ DRL 국가 벤치마킹
2027연구비: "100"
2028연구비: "100"
\```

## 작업 노트
(자유 영역 — fill 시 무시)
```

## 빈 값 처리

YAML 의 `""` 또는 미작성 키는 **빈 문자열로 치환** → 한컴에서 *빈 셀로 표시*. placeholder `{{...}}` 가 *남지 않음*.

부분적으로 채워서 사용 가능:
- 채운 키만 값 표시
- 안 채운 키는 빈 셀 (한컴에서 직접 채우거나 *후속 fill* 로 갱신)

## 한컴 보안 낮음 필수

산출물 hwpx 는 외부 도구로 생성 → 한컴이 *변조 가능성* 으로 차단. **1회** 한컴 *문서 보안 수준 = 낮음* 설정 영구 우회.

→ 한컴 메뉴: **도구 → 환경 설정 → 보안 → 문서 보안 수준 = 낮음**

## 동작 원리

1. **frontmatter 파싱** (`yaml.safe_load`) — `fillable` 경로 추출
2. **첫 ```yaml 코드블록** 파싱 — 키-값 dict
3. None / 빈 값 → `""` 문자열로 변환
4. 각 키에 `{{...}}` wrapping → replacements dict
5. **임시 JSON 생성** → `hwpx-fill --map` 호출
6. **`hwpx-multiline-fixer`** 자동 호출 (skip-fixer 옵션 X)
7. 임시 파일 정리

## 검증 (2026-05-31)

- ✓ KIRAMS 양식 38 키 fill end-to-end
- ✓ multi-line `|` literal 정상 처리 (fixer 가 `<hp:p>` 분리)
- ✓ 빈 값 정상 치환 (잔여 placeholder 0)
- ✓ XML well-formed + 한컴 (보안 낮음) 정상 표시

## 관련 도구

- `hwpx-report-init` — fillable → markdown template (정방향 시작)
- `hwpx-fill` — 결정형 string replace (이 도구가 내부 호출)
- `hwpx-multiline-fixer` — fill 후 `\n` 처리

## 변경 이력

- 2026-05-31 — 신설. KIRAMS 양식 38 키 end-to-end 검증.
