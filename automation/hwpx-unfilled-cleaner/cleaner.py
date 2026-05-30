#!/usr/bin/env python3
r"""hwpx-unfilled-cleaner — 사전할당 + 사후삭제 패턴 (옵션 Y) 지원 도구

목적
-----
한국 양식 HWPX 의 *fillable 사본* 에 *표 밖에* 사전할당된 placeholder 중
*채워지지 않은* ``{{key}}`` 만 포함한 문단(``<hp:p>`` 노드) 을 hwpx 안에서
통째로 삭제. **표 셀 안의 placeholder 는 *건드리지 않음*** (표 구조 보존).

배경
-----
한국 R&D 기획보고서 등의 양식은 *ㅇ 헤더 + - 하위* 가변 구조라 hwp-mcp v0.1.1
의 ``fill_hwp_template`` 처럼 string-replace 만으로는 문단 동적 추가가 불가.
우회 패턴 (옵션 Y, 2026-05-30 결정):

  1. 양식 fillable 사본의 *표 밖* 서술형 필드에 *최대치* placeholder 사전할당
     (예: 5 헤더 × 3 하위 = 성과목표만 ~20 키)
  2. ``fill_hwp_template`` 로 *실제 채울 만큼* 만 값 채움
  3. 채워지지 않은 ``{{key}}`` 만 남은 문단을 이 도구로 삭제
  4. 최종 hwpx 가 *깔끔한 산출물*

표 안 placeholder 는 cleaner 대상 외 — 철학
-----------------------------------------------
- **표 셀 안** (예: 사업명·총사업비·연도별 연구비 셀) = *고정 슬롯*. 모든 셀
  채워야 정상. 빈 채로 남는 건 *fill 매핑 누락* 의 신호 — cleaner 가 정리할
  영역이 아님.
- **표 밖 서술형** (예: 성과목표 ㅇ 헤더 + - 하위) = *가변 리스트*. N개
  사전할당 중 일부만 사용 → 미사용분 통째 제거가 cleaner 의 본업.

또한 표 셀 안 ``<hp:p>`` 통째 제거는 HWPX 의 표 구조
(``<hp:tbl>/<hp:tr>/<hp:tc>/<hp:subList>/<hp:p>``) 의 *셀당 최소 1 문단* 요구를
위반 → 한컴이 파일 거부. cleaner 는 표 블록을 *마스킹* 한 뒤 표 밖만 처리.

설계 — 정규식 기반 (XML 파싱 X)
--------------------------------
ElementTree 기반 XML 파싱·재serialize 는 한컴 hwpx 와 호환되지 않음:
- 원본 ``section0.xml`` 의 14+개 namespace 선언이 *2개만* 보존됨
  (ET 는 *실제 사용된* prefix 만 register 자동 유지, 나머지 폐기)
- XML declaration 형식 변경 (``encoding="UTF-8"`` → ``encoding='utf-8'``)
- 한컴은 *모든 prefix 가 유효 선언* 되어야 정상 파싱 — 위 변화로 파일 거부

→ 정규식으로 ``<hp:tbl>...</hp:tbl>`` 을 *임시 마스킹* 후 ``<hp:p>...</hp:p>``
블록만 찾아 *표 밖에서만* 통째 삭제, XML 의 다른 부분은 *일체 손대지 않음*.
원본 namespace·declaration·서식 100% 보존.

zip 재패킹 — 원본 메타 보존
----------------------------
- ``mimetype`` STORED (✓)
- ``version.xml`` STORED (원본 그대로)
- ``Preview/PrvImage.png`` STORED (이미지 — 재압축 무의미)
- **entry 순서**: 원본 그대로 (zipfile.ZipInfo 통째 복사 후 writestr)
- 각 entry 의 ``compress_type`` 도 원본 그대로

사용 예
--------
  cleaner.py input.hwpx                               # → input.cleaned.hwpx
  cleaner.py input.hwpx -o output.hwpx
  cleaner.py input.hwpx --in-place                    # 원본 덮어쓰기 (백업 .bak 생성)
  cleaner.py input.hwpx --dry-run                     # 어떤 노드 삭제될지 보기만
  cleaner.py input.hwpx --pattern '\{\{성과목표\d+(헤더|하위\d+)?\}\}'
"""
from __future__ import annotations
import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

# <hp:p ...>...</hp:p> 블록 (nested 없음 가정 — hwpx 표준)
# 시작 태그 ~ 닫는 태그까지 lazy 매칭
P_BLOCK_PATTERN = re.compile(
    r"<hp:p\b[^>]*>.*?</hp:p>",
    re.DOTALL,
)

# <hp:tbl ...>...</hp:tbl> 표 블록 (cleaner 가 *표 안* 은 건드리지 않게 마스킹용)
TBL_BLOCK_PATTERN = re.compile(
    r"<hp:tbl\b.*?</hp:tbl>",
    re.DOTALL,
)

# <hp:t ...>...</hp:t> 안의 텍스트 추출용
T_TEXT_PATTERN = re.compile(r"<hp:t\b[^>]*>([^<]*)</hp:t>")

# 빈 placeholder: 텍스트가 [선택적 글머리표] + {{...}} 만
# - 글머리표 ㅇ·○·-·•·· (한국 양식의 ㅇ 헤더 + - 하위 패턴 수용)
# - 들여쓰기·공백·연속 placeholder 허용
DEFAULT_PATTERN = re.compile(r"^\s*[ㅇ○\-•·]*\s*(?:\{\{[^}]+\}\}\s*)+\s*$")

# 표 블록 마스킹 — 충돌 회피용 고유 토큰 (XML 에 등장 불가)
TBL_MASK_FMT = "\x00HWPX_TBL_{}\x00"
TBL_MASK_RE = re.compile(r"\x00HWPX_TBL_(\d+)\x00")


def extract_block_text(block: str) -> str:
    """<hp:p> 블록 안의 모든 <hp:t> 텍스트를 이어붙임."""
    texts = T_TEXT_PATTERN.findall(block)
    return "".join(texts)


def clean_section_xml(xml_text: str, pattern: re.Pattern, dry_run: bool) -> tuple[str, list[str]]:
    """section XML 안 *표 밖 빈 placeholder 만 있는* <hp:p> 블록 삭제.

    표 셀 안 <hp:p> 는 한컴의 표 구조 (<hp:tbl>/<hp:tr>/<hp:tc>/<hp:subList>/<hp:p>) 의
    *셀당 최소 1 문단* 요구를 위반하지 않도록 *마스킹 후* 표 밖만 처리한다.
    """
    removed: list[str] = []

    # 1. 표 블록 임시 마스킹 — 표 안 <hp:p> 가 P_BLOCK_PATTERN 매칭에 안 잡히게
    tbl_blocks: list[str] = []

    def mask_tbl(m: re.Match) -> str:
        tbl_blocks.append(m.group(0))
        return TBL_MASK_FMT.format(len(tbl_blocks) - 1)

    masked = TBL_BLOCK_PATTERN.sub(mask_tbl, xml_text)

    # 2. 표 밖에서만 빈 <hp:p> 식별·제거
    def replacer(m: re.Match) -> str:
        block = m.group(0)
        text = extract_block_text(block).strip()
        if text and pattern.match(text):
            removed.append(text)
            return "" if not dry_run else block
        return block

    cleaned_masked = P_BLOCK_PATTERN.sub(replacer, masked)

    # 3. 표 블록 복원
    def unmask(m: re.Match) -> str:
        idx = int(m.group(1))
        return tbl_blocks[idx]

    cleaned = TBL_MASK_RE.sub(unmask, cleaned_masked)

    if dry_run:
        return xml_text, removed
    return cleaned, removed


def clean_hwpx(input_path: Path, output_path: Path | None, pattern: re.Pattern, dry_run: bool) -> list[str]:
    """hwpx zip 처리 — 원본 entry 순서·압축 모드 보존, section*.xml 만 수정."""
    all_removed: list[str] = []

    with zipfile.ZipFile(input_path, "r") as zin:
        infolist = zin.infolist()
        # 모든 entry 데이터 사전 읽기 (dry-run 도 동일 흐름)
        entries: list[tuple[zipfile.ZipInfo, bytes]] = []
        for info in infolist:
            data = zin.read(info.filename)
            if info.filename.startswith("Contents/section") and info.filename.endswith(".xml"):
                text = data.decode("utf-8")
                cleaned_text, removed = clean_section_xml(text, pattern, dry_run)
                all_removed.extend(removed)
                if not dry_run:
                    data = cleaned_text.encode("utf-8")
            entries.append((info, data))

    if dry_run or output_path is None:
        return all_removed

    # 원본 ZipInfo 그대로 사용 (compress_type·date_time·external_attr 등 메타 통째 보존)
    with zipfile.ZipFile(output_path, "w") as zout:
        for info, data in entries:
            zout.writestr(info, data)

    return all_removed


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", type=Path, help="Input hwpx file")
    parser.add_argument("-o", "--output", type=Path, help="Output hwpx (default: <input>.cleaned.hwpx)")
    parser.add_argument("--in-place", action="store_true", help="Overwrite input (creates <input>.bak first)")
    parser.add_argument("--pattern", help="Custom regex for empty placeholders (default: {{...}} only)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be removed without writing output")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 1
    if args.output and args.in_place:
        print("error: --output and --in-place are mutually exclusive", file=sys.stderr)
        return 2

    pattern = re.compile(args.pattern) if args.pattern else DEFAULT_PATTERN

    if args.dry_run:
        removed = clean_hwpx(args.input, None, pattern, dry_run=True)
        output_path = None
    else:
        if args.in_place:
            backup = args.input.with_suffix(args.input.suffix + ".bak")
            shutil.copy2(args.input, backup)
            output_path = args.input
            print(f"backup: {backup}", file=sys.stderr)
        else:
            output_path = args.output or args.input.with_suffix(".cleaned.hwpx")
        removed = clean_hwpx(args.input, output_path, pattern, dry_run=False)

    label = "[dry-run] " if args.dry_run else ""
    print(f"{label}Removed {len(removed)} empty placeholder paragraph(s)", file=sys.stderr)
    for text in removed[:10]:
        preview = text[:60] + ("..." if len(text) > 60 else "")
        print(f"  - {preview!r}", file=sys.stderr)
    if len(removed) > 10:
        print(f"  ... and {len(removed) - 10} more", file=sys.stderr)

    if output_path is not None:
        print(output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
