#!/usr/bin/env python3
"""xlsx_refine — 엑셀을 표준 라이브러리만으로 markdown 표로 추출해 `refined.md` 를 만든다.

    python3 xlsx_refine.py <파일.xlsx> [...]

**docling 폴백**이다. docling 이 xlsx 를 못 읽는 경우가 실재한다(2026-08-07 실측 2건:
`ZeroDivisionError: float division by zero`, `ConversionError: not valid`). 둘 다 zip 구조·시트·
sharedStrings 가 멀쩡한 정상 엑셀이었다 — 파일이 아니라 **파서 쪽 한계**다. 그런 파일이
`.parse-error` 로 영구 정체하면, 내용은 멀쩡히 읽을 수 있는데 vault 는 못 읽는 상태가 된다.

경량 추출은 brainify SKILL.md 가 원래 xlsx 파악 경로로 지정해 둔 그 방법이다
(`zipfile` → `sharedStrings.xml` → 셀 텍스트). deps·모델·docker 0, 수십 ms.

한계(의도적):
  · 수식은 **계산 결과값**(`<v>`)을 쓴다. 원본 수식 문자열은 버린다 — 읽는 사람에게 필요한 건 값이다.
  · 서식·병합·차트·이미지는 버린다. 표의 *내용*만 남긴다.
  · 날짜는 엑셀 시리얼 숫자로 남을 수 있다(스타일을 안 보므로). 원본이 sources/ 에 있으니
    정확한 표시가 필요하면 원본을 연다.
"""
from __future__ import annotations

import datetime
import pathlib
import re
import socket
import sys
import xml.etree.ElementTree as ET
import zipfile

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
MAX_ROWS = int(__import__("os").environ.get("XLSX_MAX_ROWS", "2000"))   # 시트당 행 상한


def _col_index(ref: str) -> int:
    """셀 참조(A1, BC12) → 0-based 열 번호."""
    letters = re.match(r"([A-Z]+)", ref or "")
    if not letters:
        return 0
    n = 0
    for ch in letters.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    out = []
    for si in root.findall(f"{NS}si"):
        # <si> 안에 <t> 가 여러 개(리치텍스트 런)일 수 있어 전부 이어 붙인다.
        out.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
    return out


def _sheet_names(z: zipfile.ZipFile) -> dict[str, str]:
    """sheetId·r:id 대신 순서로 맞춘다 — workbook.xml 의 <sheet> 순서 = sheet1.xml, sheet2.xml …"""
    try:
        root = ET.fromstring(z.read("xl/workbook.xml"))
        return {f"sheet{i}.xml": (s.get("name") or f"Sheet{i}")
                for i, s in enumerate(root.iter(f"{NS}sheet"), 1)}
    except Exception:
        return {}


def _cell_text(c, shared: list[str]) -> str:
    t = c.get("t")
    if t == "s":                                    # sharedStrings 인덱스
        v = c.find(f"{NS}v")
        try:
            return shared[int(v.text)] if v is not None else ""
        except (ValueError, IndexError):
            return ""
    if t == "inlineStr":
        return "".join(x.text or "" for x in c.iter(f"{NS}t"))
    v = c.find(f"{NS}v")                            # 숫자·불리언·수식 결과
    return (v.text or "") if v is not None else ""


def _sheet_rows(z: zipfile.ZipFile, path: str, shared: list[str]) -> list[list[str]]:
    rows, truncated = [], False
    root = ET.fromstring(z.read(path))
    for r in root.iter(f"{NS}row"):
        if len(rows) >= MAX_ROWS:
            truncated = True
            break
        cells: dict[int, str] = {}
        for c in r.findall(f"{NS}c"):
            txt = _cell_text(c, shared).strip()
            if txt:
                cells[_col_index(c.get("r", ""))] = txt
        rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
    while rows and not any(rows[-1]):                # 꼬리 빈 행 제거
        rows.pop()
    if truncated:
        rows.append([f"…({MAX_ROWS}행 초과분 생략 — 원본을 열 것)"])
    return rows


def _md_table(rows: list[list[str]]) -> str:
    rows = [r for r in rows if any(r)]
    if not rows:
        return "_(빈 시트)_\n"
    width = max(len(r) for r in rows)
    def line(r):
        cells = [(r[i] if i < len(r) else "").replace("|", "\\|").replace("\n", " ") for i in range(width)]
        return "| " + " | ".join(cells) + " |"
    out = [line(rows[0]), "|" + "---|" * width]
    out += [line(r) for r in rows[1:]]
    return "\n".join(out) + "\n"


def refine(path: pathlib.Path) -> tuple[bool, str]:
    out_dir = path.parent / (path.name + "_parse")
    out = out_dir / "refined.md"
    try:
        with zipfile.ZipFile(path) as z:
            shared = _shared_strings(z)
            names = _sheet_names(z)
            sheets = sorted(n for n in z.namelist()
                            if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
            if not sheets:
                return False, "워크시트 없음"
            body = []
            for s in sheets:
                title = names.get(s.rsplit("/", 1)[-1], s.rsplit("/", 1)[-1])
                body.append(f"## {title}\n")
                body.append(_md_table(_sheet_rows(z, s, shared)))
                body.append("")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

    out_dir.mkdir(parents=True, exist_ok=True)
    fm = [
        "---",
        f"source_pdf: {path}",
        "base_engine: xlsx-stdlib",          # refine.py 규약의 base_engine 자리
        'corrections: []',
        f"generated: {datetime.date.today().isoformat()}",
        f"host: {socket.gethostname()}",
        "refine_confidence: ok",
        "note: docling 폴백 — zipfile+sharedStrings 경량 추출(서식·수식문자열 제외, 값만)",
        "---",
        "",
    ]
    out.write_text("\n".join(fm) + "\n".join(body).rstrip("\n") + "\n", encoding="utf-8")
    return True, str(out)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[2]); return 2
    ok = fail = 0
    for a in argv:
        p = pathlib.Path(a)
        good, msg = refine(p)
        if good:
            ok += 1; print(f"  ok(xlsx-stdlib): {p.name} → {msg}")
        else:
            fail += 1
            print(f"  ✗ {p.name}: {msg}", file=sys.stderr)
            (p.parent / (p.name + "_parse")).mkdir(parents=True, exist_ok=True)
    print(f"[xlsx_refine] 성공 {ok} / 실패 {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
