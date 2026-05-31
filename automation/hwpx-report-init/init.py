#!/usr/bin/env python3
r"""hwpx-report-init — fillable.hwpx → markdown template (정방향 시작)

목적
-----
fillable.hwpx 의 placeholder 목록을 추출해 **YAML 코드블록 + 본문 자유** 형식의
markdown template 생성. AI agent / 사용자가 *각 키의 값을 작성하는 작업 표면*.

설계 — fillable 이 권위 원본
------------------------------
역방향 (markdown 먼저, JSON 매핑) 의 함정:
- 양식 변경 시 markdown 수동 재구성 필요
- placeholder 누락 가능

정방향 (fillable 먼저, markdown derivative) 의 이득:
- fillable 갱신 → init 재실행하면 template 자동 동기
- 모든 placeholder *사전 표시* → 누락 0
- AI agent 가 *완전한 슬롯 목록* 보고 채움 — 추측 X

markdown template 형식
-----------------------
- YAML 코드블록 안에 ``key: ""`` 형태로 모든 placeholder 표시
- multi-line 값은 YAML 의 ``|`` literal block scalar (들여쓰기·줄바꿈 보존)
- 본문은 자유 (참고자료·문맥·인용 등 — fill 시 무시)
- frontmatter 에 ``template_for``, ``fillable``, ``placeholders`` count

표 위치 정보 (depth=0 vs depth=1 nested) 도 추출해 YAML 블록 안 주석으로 표시
— 사용자가 *외곽 vs nested* 구분 가능.

사용 예
--------
  init.py fillable.hwpx
    → <fillable-stem>_fillable.md 생성 (이미 _fillable 로 끝나면 중복 안 함)

  init.py fillable.hwpx -o knowledge/01_projects/<proj>/<과제명>_fillable.md
    → 권장: <과제명>_fillable.md 명명 (vault 내 fillable 입력임을 표시)

명명 규약 (2026-05-31 v2 — 출처 추적형)
----------------------------------------
fillable 입력 markdown 은 **`<참조-기획보고서-stem>_fillable.md`** suffix 사용:
- 참조 기획보고서의 파일명을 *그대로 prefix* 로 박아 provenance 추적
- 예: 참조 `7B-VLM-의료영상품질·환자선량-최적화플랫폼.md`
      → fillable `7B-VLM-의료영상품질·환자선량-최적화플랫폼_fillable.md`
- `_fillable.hwpx` (양식) 와 짝 — 같은 형용사
- 프로젝트 폴더 내 다른 .md (기획·조사·MOC) 와 grep/시각 식별
- 기획보고서 rename 시 fillable 도 함께 갱신 필요

산출 hwpx: `<날짜>_<출처>_<과제명>_<양식종류>.hwpx` (vault 이벤트 명명, sources/ 아래).
"""
from __future__ import annotations
import argparse
import re
import sys
import zipfile
from pathlib import Path


# 가이드 markdown 의 표 행 형식: | `{{key}}` | 양식 필드 | 형식 가이드 |
GUIDE_ROW = re.compile(r"^\|\s*`\{\{([^}]+)\}\}`\s*\|[^|]*\|\s*(.*?)\s*\|\s*$")


def parse_guide_md(guide_path: Path) -> dict[str, str]:
    """가이드 markdown 에서 키 → 형식 가이드 매핑 추출.

    표 행 형식 (3 컬럼 이상): | `{{key}}` | 양식 필드 | 형식 가이드 |
    """
    if not guide_path.exists():
        return {}
    guide: dict[str, str] = {}
    for line in guide_path.read_text(encoding="utf-8").splitlines():
        m = GUIDE_ROW.match(line)
        if m:
            key = m.group(1)
            hint = m.group(2).strip()
            if hint:
                guide[key] = hint
    return guide


def extract_placeholders_with_context(fillable_path: Path) -> list[dict]:
    """fillable.hwpx 의 모든 placeholder + 표 깊이·셀 컨텍스트 추출."""
    with zipfile.ZipFile(fillable_path) as zf:
        content = zf.read("Contents/section0.xml").decode("utf-8", errors="replace")

    # 표 깊이 매핑 — 각 표의 (start, end, depth)
    # depth 의미: 외곽 표(최상위) = 0, 그 안 nested = 1, 더 안쪽 = 2...
    depth_at_pos: list[tuple[int, int, int]] = []
    depth = 0  # *현재 진입 깊이* (1-based 카운터). 표 진입 직후 +1, 종료 직후 -1
    tbl_stack: list[int] = []
    for m in re.finditer(r"<hp:tbl\b|</hp:tbl>", content):
        if m.group(0).startswith("<hp:tbl"):
            tbl_stack.append(m.start())
            depth += 1
        else:
            start = tbl_stack.pop()
            # 이 표의 depth = 진입 카운터 - 1 (0-based: 외곽 표 = 0)
            depth_at_pos.append((start, m.end(), depth - 1))
            depth -= 1
    depth_at_pos.sort()

    def find_depth(pos: int) -> int:
        """위치가 속한 가장 깊은 표의 depth. (0 = 외곽, 1 = nested, ...)"""
        max_d = -1
        for s, e, d in depth_at_pos:
            if s <= pos < e and d > max_d:
                max_d = d
        return max_d if max_d >= 0 else 0

    # placeholder 추출 (unique, 등장 순)
    seen = set()
    placeholders = []
    for m in re.finditer(r"\{\{([^}]+)\}\}", content):
        key = m.group(1)
        if key in seen:
            continue
        seen.add(key)
        pos = m.start()
        d = find_depth(pos)
        # 셀 라벨 추정 — pos 이전 500자 안 [라벨] 패턴
        before = content[max(0, pos - 500) : pos]
        labels = re.findall(r"\[([^\]]+)\]", before)
        label = labels[-1] if labels else None
        placeholders.append({"key": key, "depth": d, "cell_label": label, "pos": pos})

    return placeholders


def generate_template(fillable_path: Path, placeholders: list[dict], guide: dict[str, str]) -> str:
    """markdown template 생성. guide 가 있으면 YAML 주석으로 포함."""
    name = fillable_path.stem
    n = len(placeholders)

    # depth 별 그룹화 — outer 먼저, nested 다음
    outer = [p for p in placeholders if p["depth"] == 0]
    nested = [p for p in placeholders if p["depth"] >= 1]

    def hint_comment(p: dict) -> str:
        """우선순위: 형식 가이드 > 셀 라벨 > depth"""
        if p["key"] in guide:
            return f"  # {guide[p['key']]}"
        if p["cell_label"]:
            return f"  # [{p['cell_label']}]"
        return f"  # depth={p['depth']}" if p["depth"] > 0 else ""

    lines = [
        "---",
        f"template_for: {name}",
        f"fillable: {fillable_path}",
        f"placeholders: {n}",
        f"guide_keys: {len(guide)}",
        "status: empty",
        "---",
        "",
        f"# Fillable 양식 채움 — {name}",
        "",
        "> 각 placeholder 의 값을 아래 YAML 코드블록에 작성하세요.",
        "> multi-line 값은 `|` literal block scalar 사용 — 들여쓰기·줄바꿈 보존.",
        "> 들여쓰기 규약: `ㅇ 헤더\\n  - 하위` (반각 2칸 hanging).",
        ">",
        "> **각 키의 형식 가이드는 YAML 주석 `#` 참조** (가이드 출처: 양식 동반 노트).",
        "> 빈 `\"\"` 또는 `|` 블록을 채우기. 본문은 자유 (작업 노트·참고자료).",
        ">",
        "> 완성되면 `hwpx-report-fill <이 파일>` 으로 hwpx 산출물 생성.",
        "",
        "## 값 (YAML)",
        "",
        "```yaml",
    ]

    # outer 먼저
    if outer:
        lines.append("# === Outer 셀 (메인 양식) ===")
        for p in outer:
            lines.append(f'{p["key"]}: ""{hint_comment(p)}')

    # nested
    if nested:
        lines.append("")
        lines.append("# === Nested 표 (소요예산·연구개발 목표·연구 성과 등) ===")
        for p in nested:
            lines.append(f'{p["key"]}: ""{hint_comment(p)}')

    lines.extend(
        [
            "```",
            "",
            "## 작업 노트 (자유)",
            "",
            "(참고 자료·문맥·인용 등을 자유롭게 작성. fill 시 무시됨.)",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("fillable", type=Path, help="Input fillable.hwpx")
    parser.add_argument("-o", "--output", type=Path, help="Output markdown (default: <fillable-stem>_fillable.md). 권장: -o <task>_fillable.md (예: 7B-VLM-요약본_fillable.md) — 작업 표면임을 폴더 내 다른 .md 와 grep/시각 식별")
    parser.add_argument("--guide", type=Path, help="Guide markdown with Key 명세표 (형식 가이드 컬럼). Auto-discovered from vault if omitted.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output")
    args = parser.parse_args()

    if not args.fillable.exists():
        print(f"error: fillable not found: {args.fillable}", file=sys.stderr)
        return 1

    # default: <fillable-stem>_fillable.md (예: form_fillable.hwpx → form_fillable_fillable.md 는 어색해 .stem 에서 _fillable 트림)
    if args.output:
        output = args.output
    else:
        stem = args.fillable.stem
        if stem.endswith("_fillable"):
            stem = stem[: -len("_fillable")]
        output = args.fillable.with_name(f"{stem}_fillable.md")
    if output.exists() and not args.overwrite:
        print(f"error: output exists (use --overwrite): {output}", file=sys.stderr)
        return 2

    # 가이드 자동 발견: vault 의 sources/<...>/<양식>/fillable.hwpx → knowledge/<...>/<양식>.md
    guide_path = args.guide
    if guide_path is None:
        # sources → knowledge 매핑 + 폴더 이름과 일치하는 md 추정
        fp_str = str(args.fillable.resolve())
        if "/sources/" in fp_str:
            cand = Path(fp_str.replace("/sources/", "/knowledge/", 1)).parent.with_suffix(".md")
            if cand.exists():
                guide_path = cand

    guide = parse_guide_md(guide_path) if guide_path else {}
    placeholders = extract_placeholders_with_context(args.fillable)
    template = generate_template(args.fillable, placeholders, guide)
    output.write_text(template, encoding="utf-8")

    outer = sum(1 for p in placeholders if p["depth"] == 0)
    nested = sum(1 for p in placeholders if p["depth"] >= 1)
    matched = sum(1 for p in placeholders if p["key"] in guide)
    print(f"Generated: {output}", file=sys.stderr)
    print(f"  placeholders: {len(placeholders)} (outer {outer}, nested {nested})", file=sys.stderr)
    if guide_path:
        print(f"  guide: {guide_path}  ({matched}/{len(placeholders)} keys matched, {len(guide)} guide entries total)", file=sys.stderr)
    else:
        print(f"  guide: (none — no --guide and vault auto-discovery failed)", file=sys.stderr)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
