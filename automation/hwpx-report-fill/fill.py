#!/usr/bin/env python3
r"""hwpx-report-fill — markdown template → hwpx 산출물 (정방향 마무리)

목적
-----
``hwpx-report-init`` 가 생성한 markdown template 의 YAML 코드블록에서 값들을
추출해 ``hwpx-fill`` + ``hwpx-multiline-fixer`` 를 자동 호출 → 최종 hwpx 산출물.

워크플로우 (HWPX 우선 정책 옵션 1, 정방향)
--------------------------------------------
1. fillable.hwpx (Dr. Ben 양식)
2. hwpx-report-init → markdown template (slot 정의)
3. AI agent / Dr. Ben 이 markdown 채움 (작업 표면)
4. **hwpx-report-fill** (이 도구) → hwpx 산출물
5. 한컴 (보안 낮음) 검토 → 제출

설계
-----
- markdown frontmatter 의 ``fillable:`` 필드로 양식 자동 식별
- YAML 코드블록 (첫 ``\`\`\`yaml`` ~ ``\`\`\``` 사이) 의 키-값 추출
- 각 키에 ``{{...}}`` 자동 wrapping
- multi-line 값 (YAML 의 ``|`` literal) 그대로 보존 → fixer 가 ``<hp:p>`` 분리
- ``hwpx-fill`` + ``hwpx-multiline-fixer`` 순차 호출
- 빈 값 (``""``) 은 그대로 치환 → 한컴에서 빈 셀로 표시

사용 예
--------
  fill.py template.md -o output.hwpx
  fill.py template.md -o output.hwpx --fillable override.hwpx
  fill.py template.md --in-place-md             # output 미지정 시 <md>.hwpx
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

# 도구 위치 (영구 자산)
ROOT = Path.home() / "projects/2nd-brain/automation"
FILL_TOOL = ROOT / "hwpx-fill/fill.py"
FIXER_TOOL = ROOT / "hwpx-multiline-fixer/fixer.py"


def extract_from_markdown(md_path: Path) -> tuple[dict, Path | None]:
    """markdown 의 frontmatter + YAML 코드블록 → (replacements, fillable_path)."""
    content = md_path.read_text(encoding="utf-8")

    # frontmatter (--- ... ---)
    fillable_path: Path | None = None
    fm_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if fm_match:
        fm = yaml.safe_load(fm_match.group(1)) or {}
        if "fillable" in fm:
            fillable_path = Path(fm["fillable"])

    # YAML 코드블록 — 첫 ```yaml ... ``` 만 사용
    block_match = re.search(r"```yaml\n(.*?)\n```", content, re.DOTALL)
    if not block_match:
        raise ValueError("No ```yaml code block found in markdown")
    values_raw = yaml.safe_load(block_match.group(1))
    if not isinstance(values_raw, dict):
        raise ValueError("YAML block must be a mapping (key: value)")

    # {{key}} wrapping + None → ""
    replacements = {
        f"{{{{{k}}}}}": (str(v) if v is not None else "")
        for k, v in values_raw.items()
    }

    return replacements, fillable_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("markdown", type=Path, help="Input markdown template")
    parser.add_argument("-o", "--output", type=Path, help="Output hwpx (default: <markdown>.hwpx)")
    parser.add_argument("--fillable", type=Path, help="Override fillable.hwpx path (default: from frontmatter)")
    parser.add_argument("--skip-fixer", action="store_true", help="Skip multiline-fixer step (literal \\n 그대로)")
    args = parser.parse_args()

    if not args.markdown.exists():
        print(f"error: markdown not found: {args.markdown}", file=sys.stderr)
        return 1
    if not FILL_TOOL.exists():
        print(f"error: hwpx-fill not found: {FILL_TOOL}", file=sys.stderr)
        return 3
    if not FIXER_TOOL.exists():
        print(f"error: hwpx-multiline-fixer not found: {FIXER_TOOL}", file=sys.stderr)
        return 3

    try:
        replacements, default_fillable = extract_from_markdown(args.markdown)
    except (ValueError, yaml.YAMLError) as e:
        print(f"error: parse failed: {e}", file=sys.stderr)
        return 4

    fillable = args.fillable or default_fillable
    if fillable is None:
        print("error: fillable not specified (frontmatter `fillable:` or --fillable)", file=sys.stderr)
        return 5
    if not fillable.exists():
        print(f"error: fillable not found: {fillable}", file=sys.stderr)
        return 6

    output = args.output or args.markdown.with_suffix(".hwpx")

    # 1. hwpx-fill — JSON 임시 파일 경유
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(replacements, f, ensure_ascii=False)
        json_path = Path(f.name)

    try:
        if args.skip_fixer:
            subprocess.run(
                ["python3", str(FILL_TOOL), str(fillable), "--map", str(json_path), "-o", str(output)],
                check=True,
            )
            print(f"  → fill only: {output}", file=sys.stderr)
        else:
            tmp_filled = output.with_suffix(".filled.hwpx")
            subprocess.run(
                ["python3", str(FILL_TOOL), str(fillable), "--map", str(json_path), "-o", str(tmp_filled)],
                check=True,
            )
            subprocess.run(
                ["python3", str(FIXER_TOOL), str(tmp_filled), "-o", str(output)],
                check=True,
            )
            tmp_filled.unlink()
            print(f"  → fill + fixer: {output}", file=sys.stderr)
    finally:
        json_path.unlink()

    print(f"Replaced {len(replacements)} keys; fillable={fillable.name}", file=sys.stderr)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
