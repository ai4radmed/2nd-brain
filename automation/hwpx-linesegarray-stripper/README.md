# hwpx-linesegarray-stripper

fill 후 layout 캐시 (`<hp:linesegarray>`) 제거 → 한컴 자동 재계산 강제. **자동 줄바꿈 복원 도구**.

## 왜 필요한가

HWPX 의 `<hp:linesegarray>` = 한컴이 저장 시 계산한 *line layout 캐시* (글자 위치·줄 폭·줄 높이 등). `hwpx-fill` 로 placeholder 값을 교체하면:
- 텍스트 길이 변경 (예: `{{사업명}}` 6자 → 50자)
- 그러나 `<hp:linesegarray>` 는 *원본 6자 기준 캐시* 유지
- 한컴이 *stale 캐시 따라 그림* → **자동 줄바꿈 안 됨**, 셀 폭 초과 시 글자 중첩

증상 실측 (2026-05-31, KIRAMS 양식 7B-VLM 산출물): 사업명 셀의 50자 텍스트가 한 줄로 흘러나가 중첩 표시.

해결: `<hp:linesegarray>` 모두 제거 → 한컴이 *layout 재계산* → 자동 줄바꿈·셀 높이 자동 조정 모두 정상 복원.

## 정방향 워크플로우 위치

```
fillable.hwpx
   ↓ hwpx-fill (string replace)
filled.hwpx (literal \n, stale linesegarray)
   ↓ hwpx-multiline-fixer (\n → <hp:p> 새 문단)
fixed.hwpx (stale linesegarray)
   ↓ [hwpx-linesegarray-stripper] ← 이 도구
final.hwpx (한컴 layout 재계산)
   ↓ 한컴 (보안 낮음)
KIRAMS 제출
```

`hwpx-report-fill` 의 워크플로우 마지막 단계로 자동 호출.

## 설치

표준 라이브러리만 (Python 3.10+, zipfile + 정규식).

```bash
chmod +x ~/projects/2nd-brain/automation/hwpx-linesegarray-stripper/stripper.py
```

## 사용

```bash
stripper.py input.hwpx                     # → input.stripped.hwpx
stripper.py input.hwpx -o output.hwpx
stripper.py input.hwpx --in-place          # 원본 덮어쓰기 (백업 .bak)
stripper.py input.hwpx --dry-run           # 제거될 노드 수만
```

## 동작 원리

1. hwpx zip 안 `Contents/section*.xml` 순회
2. `<hp:linesegarray>...</hp:linesegarray>` 블록 모두 정규식 매칭
3. 통째 삭제 — XML 의 다른 부분은 일체 손대지 않음 (namespace·declaration 100% 보존)
4. 원본 ZipInfo 통째 보존

## 멱등성

이미 제거된 hwpx 에 재실행 → `Stripped 0`. 안전하게 반복 가능.

## 검증 (2026-05-31)

- KIRAMS 신규과제 양식 7B-VLM 산출물: linesegarray **212개** 제거
- 한컴 (보안 낮음) 에서:
  - 사업명 셀 *자동 줄바꿈 복원* ✓
  - 다른 셀 (multi-line·표·들여쓰기) 모두 정상 ✓
  - 셀 높이 자동 조정 ✓

## 한컴이 layout 재계산하는 이유

HWPX 표준상 `<hp:linesegarray>` 는 *optional* (없어도 valid). 한컴이 *파일 열기 시 layout 캐시 없으면 자동 재계산* 하는 *fallback 동작* 활용. 이는 *정규식 기반 우회* — 한컴 API 호출 X.

## 관련 도구

- `hwpx-fill` — 순수 string replace fill (이 도구 입력 생성)
- `hwpx-multiline-fixer` — `\n` → `<hp:p>` (stripper 이전 단계)
- `hwpx-report-fill` — 정방향 마무리 orchestration (stripper 자동 호출)

## 변경 이력

- 2026-05-31 — 신설. KIRAMS 양식 7B-VLM 산출물 자동 줄바꿈 안 됨 증상 진단 후 채택. linesegarray 제거가 한컴 layout 재계산 강제 → 자동 wrap·셀 높이 조정 모두 복원.
