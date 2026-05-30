# hwpx-unfilled-cleaner

한국 양식 HWPX 의 *사전할당된 placeholder 중 채워지지 않은 `{{key}}`* 만 포함한 문단을 hwpx 안에서 통째 삭제. **옵션 Y (사전할당 + 사후삭제) 패턴의 핵심 후처리 도구**.

## 왜 필요한가

한국 R&D 기획보고서·연구계획서 등 양식의 *서술형 필드* (성과목표·필요성·추진배경 등) 는 **ㅇ 헤더 + - 하위** 가변 구조다. 채울 개수가 *과제마다 다름*. 

기존 `hwp-mcp` v0.1.1 의 `fill_hwp_template` 은 string-replace 방식이라 *문단 동적 추가가 불가*. 우회:

```
1. 양식 fillable 사본에 *최대치* placeholder 사전할당
   예: 성과목표 = 5 헤더 × 3 하위 = ~20 키
2. fill_hwp_template 로 *실제 채울 만큼* 만 값 채움
3. 채워지지 않은 {{key}} 만 남은 문단을 이 도구로 삭제
4. 최종 hwpx 가 깔끔한 산출물
```

상세 결정 근거 → vault 메모리 `project_hwpx_first_policy`.

## 설치

표준 라이브러리만 사용 (Python 3.10+, zipfile + xml.etree). 추가 설치 0.

```bash
chmod +x ~/projects/2nd-brain/automation/hwpx-unfilled-cleaner/cleaner.py
```

## 사용

### 기본 — 빈 placeholder 모두 정리

```bash
cleaner.py input.hwpx                  # → input.cleaned.hwpx
cleaner.py input.hwpx -o output.hwpx   # 출력 경로 지정
cleaner.py input.hwpx --in-place       # 원본 덮어쓰기 (input.hwpx.bak 자동 생성)
```

### Dry-run — 어떤 문단 삭제될지 미리 보기

```bash
cleaner.py input.hwpx --dry-run
```

출력:
```
[dry-run] Removed 7 empty placeholder paragraph(s)
  - '{{성과목표5헤더}}'
  - '{{성과목표4하위3}}'
  ...
```

### 특정 패턴만 삭제

기본 패턴 = `{{...}}` 만 있는 문단 (앞뒤 공백·연속 placeholder 허용). 특정 키만 대상:

```bash
cleaner.py input.hwpx --pattern '\{\{성과목표\d+(헤더|하위\d+)?\}\}'
```

## 동작 원리

1. hwpx = zip → unzip
2. `Contents/section*.xml` 의 `<hp:p>` 문단 노드 순회
3. 각 문단의 *모든 텍스트* 추출 (`itertext()`)
4. 텍스트가 *순수 빈 placeholder 패턴* 이면 그 노드 통째 삭제
5. mimetype 을 *첫 entry + uncompressed* 로 재zip (한컴 호환)

## 멱등성

이미 정리된 hwpx 에 재실행 → `Removed 0 empty placeholder paragraph(s)`. 안전하게 반복 호출 가능.

## 워크플로우 (옵션 Y 전체)

```bash
# 1. fill_hwp_template (또는 hwp-mcp) 로 _fillable.hwpx 채우기
#    → 결과: 일부 {{key}} 가 빈 채로 남음

# 2. 빈 키 정리
cleaner.py filled.hwpx -o final.hwpx

# 3. (선택) 검증
cleaner.py final.hwpx --dry-run    # → "0 removed" 여야 정상
```

## 한계

- **hwpx 만** (hwp 5.0 바이너리 미지원 — hwpx 의 XML 구조에 의존)
- **문단 단위 삭제만** — `<hp:p>` 안 일부 텍스트만 제거는 X (그건 fill 단계의 책임)
- **표 셀 안 placeholder**: `<hp:p>` 가 표 셀 안에 있을 때 *문단 삭제 시 빈 셀 남음*. 양식 설계 시 *표 셀의 가변 행* 은 다른 방법 (행 단위 처리) 필요. 단순 ㅇ/- 리스트 처리엔 적합.

## 변경 이력

- 2026-05-30 — 신설. KIRAMS 신규과제 기획보고서 양식 (`sources/03_resources/한국원자력의학원/신규과제기획보고서양식/`) 의 fillable 사본 정리 용도로 1호 도입. 양식 namespace = `hp = http://www.hancom.co.kr/hwpml/2011/paragraph` 확인됨.
