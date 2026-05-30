#!/usr/bin/env python3
r"""hwpx-fill — 순수 string-replace 기반 hwpx placeholder 채움

목적
-----
hwp-mcp v0.1.1 의 ``fill_hwp_template`` 는 *nested table 안 placeholder* 치환
시 표 구조 일부를 깨뜨려 한컴이 파일 거부 ("문서가 손상되었거나 변조되었을
가능성", 2026-05-30 실측).

이 도구는 **순수 zipfile + 정규식 string replace** 로 *XML 구조에 일체 손대지
않고* ``{{key}}`` 만 치환. nested table·표 셀·문단 구조 모두 100% 원본 보존.

설계 — fill_hwp_template 와의 차이
------------------------------------
| 항목 | fill_hwp_template | hwpx-fill (이 도구) |
| --- | --- | --- |
| 동작 | hwp 문서 모델 read → modify → write | zipfile + section*.xml 안 string replace |
| nested table | ✗ 깨뜨림 (실측) | ✓ 무관 (텍스트 차원만) |
| 원본 ZipInfo | 부분 손실 (47KB→41KB) | 100% 보존 |
| 멱등성 | (호출마다 결과 동일) | ✓ |
| 특수문자 escape | (라이브러리가 처리) | ⚠️ ``<``, ``>``, ``&`` 는 ``&lt;``, ``&gt;``, ``&amp;`` 로 변환 필요 |

사용 예
--------
  fill.py input.hwpx --map values.json -o output.hwpx
  fill.py input.hwpx --map values.json --in-place
  fill.py input.hwpx --json '{"{{사업명}}": "..."}' -o output.hwpx

JSON 형식
----------
키는 ``{{key}}`` 형태 *전체* (괄호 포함, fill_hwp_template 와 동일 convention).
값은 multi-line 가능 (``\n`` 그대로 포함). 한컴 호환 multi-line 표시는 이후
``hwpx-multiline-fixer`` 로 후처리.

권장 워크플로우
----------------
  fillable.hwpx (셀당 1 키)
     ↓ hwpx-fill (순수 string replace)
  filled.hwpx (literal \n 잔존, nested 구조 100% 보존)
     ↓ hwpx-multiline-fixer (\n → <hp:p> 새 문단)
  final.hwpx (한컴 정상 표시)
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path


# XML escape — HWPX 의 <hp:t> 텍스트 컨텐츠 안에 <, >, & 가 있으면 XML 깨짐
def xml_escape(text: str) -> str:
    """XML 텍스트 컨텐츠 escape (& 먼저, 그 후 <, >)."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fill_section_xml(xml_text: str, replacements: dict[str, str]) -> tuple[str, dict[str, int]]:
    """section XML 안 placeholder 치환. (XML 안 텍스트라 escape 처리)"""
    counts: dict[str, int] = {}
    for key, value in replacements.items():
        # 키 자체는 {{...}} — XML 안 일반 텍스트라 그대로 검색
        n = xml_text.count(key)
        if n > 0:
            counts[key] = n
            xml_text = xml_text.replace(key, xml_escape(value))
    return xml_text, counts


def fill_hwpx(input_path: Path, output_path: Path, replacements: dict[str, str]) -> dict[str, int]:
    """hwpx 의 Contents/section*.xml 만 처리 — 원본 ZipInfo 통째 보존."""
    total: dict[str, int] = {}
    with zipfile.ZipFile(input_path, "r") as zin:
        entries: list[tuple[zipfile.ZipInfo, bytes]] = []
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.startswith("Contents/section") and info.filename.endswith(".xml"):
                text = data.decode("utf-8")
                new_text, counts = fill_section_xml(text, replacements)
                for k, v in counts.items():
                    total[k] = total.get(k, 0) + v
                data = new_text.encode("utf-8")
            entries.append((info, data))

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
    parser.add_argument("-o", "--output", type=Path, help="Output hwpx (default: <input>.filled.hwpx)")
    parser.add_argument("--in-place", action="store_true", help="Overwrite input (creates <input>.bak first)")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--map", type=Path, help="JSON file: {\"{{key}}\": \"value\", ...}")
    src.add_argument("--json", help="Inline JSON string")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 1
    if args.output and args.in_place:
        print("error: --output and --in-place are mutually exclusive", file=sys.stderr)
        return 2

    if args.map:
        replacements = json.loads(args.map.read_text(encoding="utf-8"))
    else:
        replacements = json.loads(args.json)

    if not isinstance(replacements, dict):
        print("error: replacements must be a JSON object", file=sys.stderr)
        return 3

    if args.in_place:
        backup = args.input.with_suffix(args.input.suffix + ".bak")
        shutil.copy2(args.input, backup)
        output_path = args.input
        print(f"backup: {backup}", file=sys.stderr)
    else:
        output_path = args.output or args.input.with_suffix(".filled.hwpx")

    counts = fill_hwpx(args.input, output_path, replacements)

    total = sum(counts.values())
    print(f"Replaced {total} occurrence(s) across {len(counts)} key(s)", file=sys.stderr)
    not_found = [k for k in replacements if k not in counts]
    if not_found:
        print(f"  Keys not found ({len(not_found)}): {not_found[:5]}{' ...' if len(not_found) > 5 else ''}", file=sys.stderr)

    print(output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
