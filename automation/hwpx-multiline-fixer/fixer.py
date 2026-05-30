#!/usr/bin/env python3
r"""hwpx-multiline-fixer — fill 후 literal `\n` → `<hp:p>` 새 문단 분리

목적
-----
hwp-mcp 의 ``fill_hwp_template`` 는 multi-line 값 안의 ``\n`` 을 *literal 문자*
로 그대로 ``<hp:t>`` 안에 넣음. 한컴은 *literal newline 도 ``<hp:lineBreak/>``
도 무시* — 결과물에서 모든 줄이 *한 줄로 뭉쳐* 표시됨 (실측 검증, 2026-05-30).

해결: **각 줄을 별도 `<hp:p>` 새 문단으로 분리** — 부모 `<hp:p>` 의 모든 속성·
``<hp:run>`` 의 charPrIDRef 등 그대로 복제. 한컴이 *문단 단위* 로 자연 줄바꿈.

변환 예
--------
Before::

  <hp:p paraPrIDRef="X" ...><hp:run charPrIDRef="Z"><hp:t> ㅇ 헤더1
    - 하위1
  ㅇ 헤더2</hp:t></hp:run><hp:linesegarray>...</hp:linesegarray></hp:p>

After (3 줄 → 3 <hp:p>)::

  <hp:p paraPrIDRef="X" ...><hp:run charPrIDRef="Z"><hp:t> ㅇ 헤더1</hp:t></hp:run><hp:linesegarray>...</hp:linesegarray></hp:p>
  <hp:p paraPrIDRef="X" ...><hp:run charPrIDRef="Z"><hp:t>  - 하위1</hp:t></hp:run><hp:linesegarray>...</hp:linesegarray></hp:p>
  <hp:p paraPrIDRef="X" ...><hp:run charPrIDRef="Z"><hp:t>ㅇ 헤더2</hp:t></hp:run><hp:linesegarray>...</hp:linesegarray></hp:p>

→ 각 줄이 *같은 paraPrIDRef·charPrIDRef* 의 독립 문단. 한컴이 글머리표 스타일
보존 가능성도 ↑ (각 문단이 같은 paraPr 상속).

설계 — 정규식 기반 (XML 파싱 X)
---------------------------------
- 원본 namespace·declaration 100% 보존
- 원본 ZipInfo 보존 (mimetype STORED, entry 순서, 압축 모드)
- 멱등: 변환 후 ``<hp:t>`` 안 ``\n`` 없음 → 재실행 시 0

전제
-----
``<hp:p>`` 안에 ``<hp:t>`` 가 *1개만* 있고 그 안 텍스트에 ``\n`` 있는 케이스를
처리. fill_hwp_template 의 출력은 일반적으로 이 구조. 다중 ``<hp:t>`` 가 한
``<hp:p>`` 안에 있는 경우 (예: 양식이 원래 그런 구조) 는 *변환 skip*.

한계
-----
- ``<hp:linesegarray>`` 는 원본 문단의 *layout 캐시* — 한컴이 *읽고 자동 재계산*
  하는 게 일반적. 복제된 모든 문단이 같은 linesegarray 가져도 *시각적 표시는
  올바름* (한컴이 layout 다시 계산).
- 표 셀 안 ``<hp:subList>`` 내 ``<hp:p>`` 분리도 안전 (한컴이 셀 높이 자동 조정).

사용 예
--------
  fixer.py input.hwpx                     # → input.fixed.hwpx
  fixer.py input.hwpx -o output.hwpx
  fixer.py input.hwpx --in-place          # 원본 덮어쓰기 (백업 .bak)
  fixer.py input.hwpx --dry-run           # 변환 대상 카운트만
"""
from __future__ import annotations
import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

# <hp:p ...>...</hp:p> 전체 블록 (nested 없음 가정)
P_BLOCK_PATTERN = re.compile(
    r"(<hp:p\b[^>]*>)(.*?)(</hp:p>)",
    re.DOTALL,
)

# <hp:t [attrs]>multi-line</hp:t>
T_WITH_NEWLINE = re.compile(
    r"(<hp:t\b[^>]*>)([^<]*\n[^<]*)(</hp:t>)",
)


def split_paragraph_by_newlines(m: re.Match) -> str:
    """<hp:p> 안 <hp:t> 의 multi-line 텍스트를 줄당 1 <hp:p> 로 복제."""
    p_open = m.group(1)
    p_inner = m.group(2)
    p_close = m.group(3)

    t_match = T_WITH_NEWLINE.search(p_inner)
    if not t_match:
        return m.group(0)

    t_open = t_match.group(1)
    text = t_match.group(2)
    t_close = t_match.group(3)

    lines = text.split("\n")
    if len(lines) <= 1:
        return m.group(0)

    # <hp:t> 자리에 한 줄씩 채운 N 개 <hp:p> 생성
    paragraphs: list[str] = []
    for line in lines:
        new_t = t_open + line + t_close
        new_inner = p_inner[: t_match.start()] + new_t + p_inner[t_match.end():]
        paragraphs.append(p_open + new_inner + p_close)
    return "".join(paragraphs)


def count_multiline_paragraphs(xml_text: str) -> int:
    """변환 대상 <hp:p> 수 (dry-run 보고용) — 내부 <hp:t> 가 multi-line."""
    count = 0
    for m in P_BLOCK_PATTERN.finditer(xml_text):
        if T_WITH_NEWLINE.search(m.group(2)):
            count += 1
    return count


def fix_section_xml(xml_text: str, dry_run: bool) -> tuple[str, int]:
    """section XML 의 multi-line <hp:p> → N 개 <hp:p> 복제."""
    count = count_multiline_paragraphs(xml_text)
    if dry_run:
        return xml_text, count
    fixed = P_BLOCK_PATTERN.sub(split_paragraph_by_newlines, xml_text)
    return fixed, count


def fix_hwpx(input_path: Path, output_path: Path | None, dry_run: bool) -> int:
    total_fixed = 0
    with zipfile.ZipFile(input_path, "r") as zin:
        entries: list[tuple[zipfile.ZipInfo, bytes]] = []
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.startswith("Contents/section") and info.filename.endswith(".xml"):
                text = data.decode("utf-8")
                fixed_text, n = fix_section_xml(text, dry_run)
                total_fixed += n
                if not dry_run:
                    data = fixed_text.encode("utf-8")
            entries.append((info, data))

    if dry_run or output_path is None:
        return total_fixed

    with zipfile.ZipFile(output_path, "w") as zout:
        for info, data in entries:
            zout.writestr(info, data)

    return total_fixed


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", type=Path, help="Input hwpx file")
    parser.add_argument("-o", "--output", type=Path, help="Output hwpx (default: <input>.fixed.hwpx)")
    parser.add_argument("--in-place", action="store_true", help="Overwrite input (creates <input>.bak first)")
    parser.add_argument("--dry-run", action="store_true", help="Show count of multi-line <hp:p> to split")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 1
    if args.output and args.in_place:
        print("error: --output and --in-place are mutually exclusive", file=sys.stderr)
        return 2

    if args.dry_run:
        n = fix_hwpx(args.input, None, dry_run=True)
        output_path = None
    else:
        if args.in_place:
            backup = args.input.with_suffix(args.input.suffix + ".bak")
            shutil.copy2(args.input, backup)
            output_path = args.input
            print(f"backup: {backup}", file=sys.stderr)
        else:
            output_path = args.output or args.input.with_suffix(".fixed.hwpx")
        n = fix_hwpx(args.input, output_path, dry_run=False)

    label = "[dry-run] " if args.dry_run else ""
    print(f"{label}Fixed {n} multi-line <hp:p>(s) (literal \\n → 새 문단 분리)", file=sys.stderr)

    if output_path is not None:
        print(output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
