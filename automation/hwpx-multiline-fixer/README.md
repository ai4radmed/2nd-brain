# hwpx-multiline-fixer

hwp-mcp `fill_hwp_template` 후처리 도구. **`<hp:t>` 안 literal `\n` 을 `<hp:p>` 새 문단으로 분리** — 한컴에서 multi-line 정상 표시.

## 왜 필요한가

`fill_hwp_template` 가 multi-line 값 (예: 성과목표의 ㅇ/- 리스트) 의 `\n` 을 *literal 줄바꿈 문자* 로 그대로 `<hp:t>` 안에 넣는다. 한컴은 이를 *무시* — **모든 줄이 한 줄로 뭉쳐 표시**됨.

실측 결과 (2026-05-30):
- ① `<hp:t>` 안 literal `\n` → 한컴 무시 ✗
- ② `<hp:lineBreak/>` 삽입 → 한컴 무시 ✗
- ③ **`<hp:p>` 새 문단 분리 → 한컴 정상 multi-line 표시 ✓**

→ 셋 중 ③ 만 작동. fixer.py 가 ③ 변환.

## 워크플로우 위치

HWPX 우선 정책 옵션 1 (셀당 1 키 통합) 의 *결정적 후처리*:

```
fillable.hwpx (셀당 1 키)
   ↓ fill_hwp_template (multi-line 값 매핑)
filled.hwpx (literal \n 잔존)
   ↓ fixer.py (\n → <hp:p> 새 문단 분리)
final.hwpx (한컴 정상 multi-line + 스타일 보존)
```

상세 정책 → vault 메모리 `project_hwpx_first_policy`.

## 설치

표준 라이브러리만 (Python 3.10+, zipfile). 추가 설치 0.

```bash
chmod +x ~/projects/2nd-brain/automation/hwpx-multiline-fixer/fixer.py
```

## 사용

```bash
fixer.py input.hwpx                  # → input.fixed.hwpx
fixer.py input.hwpx -o output.hwpx
fixer.py input.hwpx --in-place       # 원본 덮어쓰기 (input.hwpx.bak 자동 생성)
fixer.py input.hwpx --dry-run        # 변환 대상 카운트만
```

## 동작 원리

1. hwpx zip 안 `Contents/section*.xml` 순회
2. 각 `<hp:p>...</hp:p>` 블록의 내부 `<hp:t>` 안 텍스트에 `\n` 있나 검사
3. 있으면 **줄 단위로 `<hp:p>` 노드 복제** — 부모 문단의 모든 속성 (paraPrIDRef·styleIDRef) 과 `<hp:run>` 의 charPrIDRef 그대로 전파
4. 원본 ZipInfo 통째 보존 (mimetype STORED, entry 순서, 압축 모드)

### 변환 예

Before (1 문단, multi-line 텍스트):
```xml
<hp:p paraPrIDRef="73">
  <hp:run charPrIDRef="82">
    <hp:t> ㅇ 헤더1
  - 하위1
ㅇ 헤더2</hp:t>
  </hp:run>
  <hp:linesegarray>...</hp:linesegarray>
</hp:p>
```

After (3 문단, 각 줄 독립 + 모든 속성 복제):
```xml
<hp:p paraPrIDRef="73"><hp:run charPrIDRef="82"><hp:t> ㅇ 헤더1</hp:t></hp:run>...</hp:p>
<hp:p paraPrIDRef="73"><hp:run charPrIDRef="82"><hp:t>  - 하위1</hp:t></hp:run>...</hp:p>
<hp:p paraPrIDRef="73"><hp:run charPrIDRef="82"><hp:t>ㅇ 헤더2</hp:t></hp:run>...</hp:p>
```

## 멱등성

이미 분리된 hwpx 에 재실행 → `Fixed 0`. 안전하게 반복 호출 가능.

## 한계

- **`<hp:p>` 안 `<hp:t>` 가 *2개 이상*** 인 경우 (양식이 원래 그런 구조) 는 *변환 skip* — fill_hwp_template 출력은 보통 1개라 안전.
- **`<hp:t>` 안에 XML escape** (`&`, `<`, `>`) 가 있으면 정규식이 깨질 위험. 일반 한국어 텍스트는 안전.
- **글머리표 *자동 스타일* (들여쓰기·기호 자동)** 은 한컴이 paraPrIDRef 따라 결정 — *원본 paraPr 이 글머리표 스타일이면* 모든 복제 문단에도 자동 적용. 아니면 plain text 표시.

## 검증 (2026-05-30)

- ✓ 단위 디버그: 1 `<hp:p>` multi-line → N 개 분리 정확
- ✓ Dr. Ben 시연: 5 multi-line `<hp:p>` → 분리 후 한컴 정상 multi-line 표시
- ✓ 멱등성: 재실행 0
- ✓ XML well-formed
- ✓ 한컴 파일 열기 정상 + 들여쓰기 보존

## 관련 도구

- `~/projects/2nd-brain/automation/hwpx-unfilled-cleaner/` — 옵션 Y (표 밖 미사용 placeholder 정리). 본 fixer 와 *별도* 워크플로우.

## 변경 이력

- 2026-05-30 — 신설. KIRAMS 신규과제 양식 1호 도입. linebreak 전략 시도 → 한컴 무시 → paragraph 분리 전략으로 전환 (실측 검증). 정책 권위 = vault 메모리 [[project_hwpx_first_policy]].
