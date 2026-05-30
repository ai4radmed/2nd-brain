# hwpx-fill

순수 string-replace 기반 HWPX placeholder 채움. **hwp-mcp 의 `fill_hwp_template` 가 nested 표 구조를 깨뜨리는 문제 우회**.

## 왜 필요한가

hwp-mcp v0.1.1 의 `fill_hwp_template` 는 hwp 문서 모델로 *read → modify → write* 방식. nested table 안 placeholder 치환 시 *셀 구조 부정합* 발생 → 한컴이 *변조 가능성* 으로 거부 (실측, 2026-05-30).

이 도구는 **순수 zipfile + 정규식 string replace** 로 *XML 구조에 일체 손대지 않고* `{{key}}` 만 치환. nested table·표 셀·문단 구조 모두 100% 원본 보존.

## fill_hwp_template 와의 차이

| 항목 | fill_hwp_template (hwp-mcp v0.1.1) | hwpx-fill (이 도구) |
|---|---|---|
| 방식 | hwp 문서 모델 read → modify → write | zipfile + section*.xml string replace |
| nested table | ✗ 깨뜨림 (실측, 한컴 거부) | ✓ 무관 (텍스트 차원만) |
| 원본 ZipInfo | 부분 손실 (47KB → 41KB) | 100% 보존 |
| 특수문자 escape | (라이브러리 처리) | `<`, `>`, `&` 자동 escape |
| MCP 호환 | ✓ Claude Code 도구로 직접 호출 가능 | ✗ CLI 만 — Bash 도구로 호출 |

## 설치

표준 라이브러리만 (Python 3.10+, zipfile). 추가 설치 0.

```bash
chmod +x ~/projects/2nd-brain/automation/hwpx-fill/fill.py
```

## 사용

```bash
# JSON 파일로
fill.py input.hwpx --map values.json -o output.hwpx
fill.py input.hwpx --map values.json --in-place

# inline JSON
fill.py input.hwpx --json '{"{{사업명}}": "..."}' -o output.hwpx
```

### JSON 형식

```json
{
  "{{사업명}}": "VLM 활용 핵의학 영상검사품질·환자선량 최적화 플랫폼 개발",
  "{{성과목표}}": "ㅇ 번인 선량 자동추출\n  - 비식별 PACS DICOM → 7B VLM OCR\n  - 물리·통계 이중검증\nㅇ DRL 국가 벤치마킹",
  "{{2027연구비}}": "100"
}
```

- 키는 `{{...}}` 전체 (괄호 포함)
- 값은 multi-line 가능 (`\n` 그대로). 한컴 표시는 *hwpx-multiline-fixer* 후처리로
- **들여쓰기 규약**: 반각 2칸 hanging — `"ㅇ 헤더\n  - 하위"` (검증된 패턴, 2026-05-31)

## 완전 워크플로우 (HWPX 우선 정책 옵션 1)

```bash
# 1. fill — fillable 의 셀당 1 키에 값 매핑
python3 ~/projects/2nd-brain/automation/hwpx-fill/fill.py \
    fillable.hwpx --map values.json -o filled.hwpx

# 2. fixer — literal \n → <hp:p> 새 문단 분리 (한컴 호환)
python3 ~/projects/2nd-brain/automation/hwpx-multiline-fixer/fixer.py \
    filled.hwpx --in-place

# 3. 한컴에서 열기 — 보안 낮음 설정 필요 (외부 도구 hwpx 신뢰)
```

상세 정책 → vault 메모리 `project_hwpx_first_policy`.

## 한컴 보안 설정 필수

외부 도구로 생성한 HWPX 는 한컴이 *변조 가능성* 으로 차단. **한 번** 한컴의 *문서 보안 수준* 을 **낮음** 으로 설정하면 영구 적용.

→ 한컴 메뉴: **도구 → 환경 설정 → 보안 → 문서 보안 수준 = 낮음**

## 동작 원리

1. hwpx zip 안 `Contents/section*.xml` 순회
2. 각 section 의 텍스트에 `{{key}} → value` string replace
3. 값에 XML 특수문자 (`<`, `>`, `&`) 자동 escape
4. 원본 ZipInfo 통째 보존 (mimetype STORED, entry 순서·압축 모드)

## 검증 (2026-05-31)

- ✓ KIRAMS 신규과제 기획보고서 양식 38 키 전체 fill 정상
- ✓ Outer + Nested + 셀 내 ㅇ 텍스트 + nested 표 공존 모두 안전
- ✓ Multi-line 값 처리 (fixer 후처리 조합)
- ✓ XML well-formed + 표 구조 100% 보존
- ✓ 한컴 (보안 낮음) 에서 정상 표시

## 관련 도구

- `~/projects/2nd-brain/automation/hwpx-multiline-fixer/` — fill 후 `\n` → `<hp:p>` 분리 (필수 후처리)
- `~/projects/2nd-brain/automation/hwpx-unfilled-cleaner/` — 표 밖 미사용 placeholder 정리 (다른 한국 양식 대비)

## 변경 이력

- 2026-05-30 — 신설. hwp-mcp 의 fill_hwp_template 가 nested table 깨뜨리는 문제 회피용. 실측 검증 후 채택.
- 2026-05-31 — KIRAMS 양식 1호 38 키 전체 fill end-to-end 검증 완료.
