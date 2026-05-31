#!/usr/bin/env python3
r"""hwpx-linesegarray-stripper — fill 후 layout 캐시 제거 → 한컴 자동 재계산 강제

목적
-----
HWPX 의 ``<hp:linesegarray>`` 는 *한컴이 저장 시 계산한 line layout 캐시*.
``hwpx-fill`` 로 placeholder 값을 교체하면 *텍스트 길이* 가 변하지만 캐시는
원본 placeholder (예: ``{{사업명}}`` 6자) 기준이라 *stale* 상태.

증상: 셀 폭을 초과하는 긴 텍스트가 *자동 줄바꿈 안 되고* 한 줄로 흘러나가
중첩 표시 (실측, 2026-05-31).

해결: ``<hp:linesegarray>`` 노드를 모두 제거 — 한컴이 *layout 을 다시 계산*
하여 자동 줄바꿈·셀 높이 자동 조정·들여쓰기 모두 정상 복원.

설계 (cleaner·fixer 와 동일 철학)
-----------------------------------
- 정규식 기반 — XML 파싱 X, 원본 namespace·declaration·서식 100% 보존
- 원본 ZipInfo 통째 보존 (mimetype STORED, entry 순서·압축 모드)
- 멱등 — 이미 제거된 hwpx 재실행 시 0 removed

위치
----
정방향 워크플로우의 **마지막 단계**:

  fill → fixer → **stripper** → 한컴 (보안 낮음)

``hwpx-report-fill`` 이 자동 호출. CLI 로 단독 호출도 가능.

사용 예
--------
  stripper.py input.hwpx                     # → input.stripped.hwpx
  stripper.py input.hwpx -o output.hwpx
  stripper.py input.hwpx --in-place          # 원본 덮어쓰기 (백업 .bak)
  stripper.py input.hwpx --dry-run           # 제거될 노드 수만 보기

검증 (2026-05-31)
-------------------
- KIRAMS 양식 7B-VLM 산출물: linesegarray 212개 제거 → 한컴 자동 줄바꿈 복원 ✓
- 다른 셀 (multi-line·표 구조·들여쓰기) 모두 정상 (한컴 재계산)
"""
from __future__ import annotations
import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

LINESEG_PATTERN = re.compile(r"<hp:linesegarray\b.*?</hp:linesegarray>", re.DOTALL)


def strip_section_xml(xml_text: str, dry_run: bool) -> tuple[str, int]:
    """section XML 의 <hp:linesegarray> 모두 제거."""
    count = len(LINESEG_PATTERN.findall(xml_text))
    if dry_run:
        return xml_text, count
    return LINESEG_PATTERN.sub("", xml_text), count


def strip_hwpx(input_path: Path, output_path: Path | None, dry_run: bool) -> int:
    """hwpx zip 처리 — 원본 entry 순서·압축 모드 보존."""
    total = 0
    with zipfile.ZipFile(input_path, "r") as zin:
        entries: list[tuple[zipfile.ZipInfo, bytes]] = []
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.startswith("Contents/section") and info.filename.endswith(".xml"):
                text = data.decode("utf-8")
                new_text, count = strip_section_xml(text, dry_run)
                total += count
                if not dry_run:
                    data = new_text.encode("utf-8")
            entries.append((info, data))

    if dry_run or output_path is None:
        return total

    with zipfile.ZipFile(output_path, "w") as zout:
        for info, data in entries:
            zout.writestr(info, data)

    return total


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", type=Path, help="Input hwpx file")
    parser.add_argument("-o", "--output", type=Path, help="Output hwpx (default: <input>.stripped.hwpx)")
    parser.add_argument("--in-place", action="store_true", help="Overwrite input (creates <input>.bak first)")
    parser.add_argument("--dry-run", action="store_true", help="Show count of <hp:linesegarray> nodes to strip")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 1
    if args.output and args.in_place:
        print("error: --output and --in-place are mutually exclusive", file=sys.stderr)
        return 2

    if args.dry_run:
        n = strip_hwpx(args.input, None, dry_run=True)
        output_path = None
    else:
        if args.in_place:
            backup = args.input.with_suffix(args.input.suffix + ".bak")
            shutil.copy2(args.input, backup)
            output_path = args.input
            print(f"backup: {backup}", file=sys.stderr)
        else:
            output_path = args.output or args.input.with_suffix(".stripped.hwpx")
        n = strip_hwpx(args.input, output_path, dry_run=False)

    label = "[dry-run] " if args.dry_run else ""
    print(f"{label}Stripped {n} <hp:linesegarray> node(s) (한컴 layout 재계산 강제)", file=sys.stderr)

    if output_path is not None:
        print(output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
