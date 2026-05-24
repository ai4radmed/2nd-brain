#!/usr/bin/env python3
"""brain-pdf — Docling + MinerU dual PDF parser CLI.

Subcommands:
  parse-docling <pdf>    Parse PDF with Docling. Stdout: JSON.
  parse-mineru  <pdf>    Parse PDF with MinerU. Stdout: JSON.
  diff <a> <b>           Compare two parser JSON outputs. Stdout: structured diff.

Phase 0~1 stubs — actual parser logic lands in P1.4 / P1.5 / P2.x per
brainify-inbox PROGRESS.md governance.
"""
import argparse
import json
import sys

VERSION = "0.2.0"

EX_NOT_IMPLEMENTED = 78  # sysexits.h EX_CONFIG — configuration / not-yet-built


def parse_docling(pdf_path: str) -> dict:
    # Imports are local so `--version`, `--help`, and other subcommands don't
    # pay the docling import cost (~3s+) or trigger model probes.
    import contextlib
    import sys
    import time
    from docling.document_converter import DocumentConverter

    # docling/rapidocr emit INFO logs to stdout via print/logging at import and
    # convert time. Redirect to stderr so this function's stdout contract stays
    # clean JSON for the diff module (P2.3) to consume.
    # runtime_sec spans converter init + convert — that's the per-call cost an
    # operator pays when invoking `parse-docling` ephemerally, which is the
    # Phase 1 default. Daemon mode (warm converter) would report a different
    # number; we'll revisit if/when that ships.
    t0 = time.perf_counter()
    with contextlib.redirect_stdout(sys.stderr):
        converter = DocumentConverter()
        result = converter.convert(pdf_path)
    runtime_sec = time.perf_counter() - t0

    doc = result.document
    return {
        "engine": "docling",
        "pdf_path": pdf_path,
        "pages": len(doc.pages),
        "runtime_sec": round(runtime_sec, 3),
        "markdown": doc.export_to_markdown(),
        "doctags": doc.export_to_doctags(),
        "json_structure": doc.export_to_dict(),
    }


def parse_mineru(pdf_path: str) -> dict:
    # Local imports keep --version/--help cheap, matching parse_docling.
    import json as _json
    import subprocess
    import sys
    import tempfile
    import time
    from pathlib import Path

    pdf = Path(pdf_path)
    if not pdf.is_file():
        raise FileNotFoundError(pdf_path)

    # MinerU CLI writes a tree of artifacts under <output_dir>/<stem>/auto/.
    # Use a tempdir and only keep what we need in the returned dict.
    # Backend = "pipeline": validated on Korean accounting PDFs at P1.5.
    # vlm/hybrid-* backends are not exercised in Phase 1.
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="mineru-") as out_dir:
        proc = subprocess.run(
            ["mineru", "-p", str(pdf), "-o", out_dir,
             "-b", "pipeline", "-l", "korean"],
            capture_output=True,
            text=True,
        )
        # MinerU's CLI prints progress + FastAPI logs to both stdout and stderr.
        # Forward to our stderr so this function's stdout stays JSON-only.
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        if proc.returncode != 0:
            raise RuntimeError(
                f"mineru exited {proc.returncode} for {pdf_path!r}"
            )

        stem = pdf.stem
        auto = Path(out_dir) / stem / "auto"
        markdown = (auto / f"{stem}.md").read_text(encoding="utf-8")
        middle = _json.loads(
            (auto / f"{stem}_middle.json").read_text(encoding="utf-8")
        )
        runtime_sec = time.perf_counter() - t0

    return {
        "engine": "mineru",
        "pdf_path": str(pdf),
        # middle.json's pdf_info is the per-page block list. Falling back to
        # 0 would mask a bug; len() will raise if the schema changes.
        "pages": len(middle["pdf_info"]),
        "runtime_sec": round(runtime_sec, 3),
        "markdown": markdown,
        # No doctags-equivalent format in MinerU. Kept in the schema as null
        # so diff (P2.3) can detect and skip the doctags comparison.
        "doctags": None,
        # middle.json carries the richest structural view (layout blocks per
        # page with bboxes + types). Closest analog to docling's
        # export_to_dict(). content_list_v2.json is also available but flatter.
        "json_structure": middle,
    }


_DIFF_THRESHOLDS = {
    "heading_overlap": 0.8,      # min acceptable
    "paragraph_count_delta": 0.2, # max acceptable
    "table_count_match": 0.8,    # min acceptable
    "numeric_cell_match": 0.95,  # min acceptable
}
_DIFF_DETAIL_CAP = 10


def _normalize_markdown(md: str) -> dict:
    """Pull headings, paragraphs, and tables out of either docling-style
    (pipe tables) or mineru-style (HTML tables) markdown into one shape:
    {headings: [(level, text)], paragraphs: [text], tables: [[[cell]]]}.
    """
    import re
    from bs4 import BeautifulSoup

    tables: list[list[list[str]]] = []

    # 1. Mineru-style HTML tables — extract then mask out.
    for html in re.findall(r"<table.*?</table>", md, flags=re.DOTALL):
        soup = BeautifulSoup(html, "html.parser")
        rows = []
        for tr in soup.find_all("tr"):
            rows.append([c.get_text(strip=True) for c in tr.find_all(["td", "th"])])
        if rows:
            tables.append(rows)
    md_no_html = re.sub(r"<table.*?</table>", "<<TABLE>>", md, flags=re.DOTALL)

    # 2. Docling-style pipe tables — walk line by line.
    headings: list[tuple[int, str]] = []
    paragraphs: list[str] = []
    buf: list[str] = []
    lines = md_no_html.splitlines()

    def flush():
        if buf:
            paragraphs.append(" ".join(buf).strip())
            buf.clear()

    i = 0
    sep_re = re.compile(r"^\|[\s\-:|]+\|$")
    head_re = re.compile(r"^(#+)\s+(.*)")
    while i < len(lines):
        line = lines[i].rstrip()
        if (line.startswith("|") and i + 1 < len(lines)
                and sep_re.match(lines[i + 1].rstrip())):
            flush()
            rows = [line]
            j = i + 1
            while j < len(lines) and lines[j].startswith("|"):
                rows.append(lines[j])
                j += 1
            # Drop the alignment-separator row at index 1.
            parsed = []
            for tline in [rows[0]] + rows[2:]:
                cells = [c.strip() for c in tline.strip("|").split("|")]
                parsed.append(cells)
            tables.append(parsed)
            i = j
            continue
        if line.startswith("<<TABLE>>"):
            flush()
        elif (m := head_re.match(line)):
            flush()
            headings.append((len(m.group(1)), m.group(2).strip()))
        elif not line.strip():
            flush()
        else:
            buf.append(line.strip())
        i += 1
    flush()

    return {"headings": headings, "paragraphs": paragraphs, "tables": tables}


def _extract_numeric_cells(tables: list) -> list[str]:
    """Numeric-looking cell values across all tables, normalized to a
    canonical string form (commas/spaces/percent stripped). Cells that
    aren't purely numeric (e.g. "2021년", "-", "출연금") are skipped —
    they are stable text and don't drive diff signal.
    """
    import re
    pure = re.compile(r"-?\d+(?:\.\d+)?")
    out = []
    for table in tables:
        for row in table:
            for cell in row:
                if not isinstance(cell, str):
                    continue
                s = re.sub(r"[,\s%]", "", cell)
                if pure.fullmatch(s):
                    out.append(s)
    return out


def diff_outputs(a_path: str, b_path: str) -> dict:
    import json as _json
    from collections import Counter
    from pathlib import Path

    a = _json.loads(Path(a_path).read_text(encoding="utf-8"))
    b = _json.loads(Path(b_path).read_text(encoding="utf-8"))

    a_n = _normalize_markdown(a["markdown"])
    b_n = _normalize_markdown(b["markdown"])

    # heading_overlap — level-agnostic set comparison on heading text.
    a_h = {h[1] for h in a_n["headings"]}
    b_h = {h[1] for h in b_n["headings"]}
    only_a = a_h - b_h
    only_b = b_h - a_h
    if a_h or b_h:
        heading_overlap = len(a_h & b_h) / max(len(a_h), len(b_h))
    else:
        heading_overlap = 1.0

    pa, pb = len(a_n["paragraphs"]), len(b_n["paragraphs"])
    paragraph_count_delta = (
        abs(pa - pb) / max(pa, pb) if max(pa, pb) > 0 else 0.0
    )

    ta, tb = len(a_n["tables"]), len(b_n["tables"])
    table_count_match = (
        min(ta, tb) / max(ta, tb) if max(ta, tb) > 0 else 1.0
    )

    a_nums = Counter(_extract_numeric_cells(a_n["tables"]))
    b_nums = Counter(_extract_numeric_cells(b_n["tables"]))
    common_nums = sum((a_nums & b_nums).values())
    total_nums = max(sum(a_nums.values()), sum(b_nums.values()))
    numeric_cell_match = common_nums / total_nums if total_nums > 0 else 1.0

    verdict = (
        "agree"
        if (
            heading_overlap >= _DIFF_THRESHOLDS["heading_overlap"]
            and paragraph_count_delta <= _DIFF_THRESHOLDS["paragraph_count_delta"]
            and table_count_match >= _DIFF_THRESHOLDS["table_count_match"]
            and numeric_cell_match >= _DIFF_THRESHOLDS["numeric_cell_match"]
        )
        else "diverge"
    )

    # Numeric mismatches: top-N by occurrence, mixing both directions but
    # capping the combined list at _DIFF_DETAIL_CAP so reports stay scannable.
    a_only_nums = (a_nums - b_nums).most_common()
    b_only_nums = (b_nums - a_nums).most_common()
    numeric_mismatches = []
    for v, c in a_only_nums:
        numeric_mismatches.append({"value": v, "side": "a_only", "count": c})
    for v, c in b_only_nums:
        numeric_mismatches.append({"value": v, "side": "b_only", "count": c})
    numeric_mismatches.sort(key=lambda x: x["count"], reverse=True)
    numeric_mismatches = numeric_mismatches[:_DIFF_DETAIL_CAP]

    return {
        "a": {"engine": a["engine"], "pdf_path": a["pdf_path"], "pages": a["pages"]},
        "b": {"engine": b["engine"], "pdf_path": b["pdf_path"], "pages": b["pages"]},
        "metrics": {
            "heading_overlap": round(heading_overlap, 3),
            "paragraph_count_delta": round(paragraph_count_delta, 3),
            "table_count_match": round(table_count_match, 3),
            "numeric_cell_match": round(numeric_cell_match, 3),
            "heading_count": {"a": len(a_h), "b": len(b_h)},
            "paragraph_count": {"a": pa, "b": pb},
            "table_count": {"a": ta, "b": tb},
            "numeric_cell_count": {
                "a": sum(a_nums.values()),
                "b": sum(b_nums.values()),
            },
        },
        "thresholds": _DIFF_THRESHOLDS,
        "verdict": verdict,
        "details": {
            "headings_only_in_a": sorted(only_a)[:_DIFF_DETAIL_CAP],
            "headings_only_in_b": sorted(only_b)[:_DIFF_DETAIL_CAP],
            "numeric_mismatches": numeric_mismatches,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="brain-pdf",
        description="2nd-brain Docling+MinerU dual PDF parser",
    )
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_docling = sub.add_parser("parse-docling", help="Parse PDF with Docling")
    p_docling.add_argument("pdf")

    p_mineru = sub.add_parser("parse-mineru", help="Parse PDF with MinerU")
    p_mineru.add_argument("pdf")

    p_diff = sub.add_parser("diff", help="Compare two parser outputs")
    p_diff.add_argument("a", help="Docling JSON output path")
    p_diff.add_argument("b", help="MinerU JSON output path")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "parse-docling":
            result = parse_docling(args.pdf)
        elif args.cmd == "parse-mineru":
            result = parse_mineru(args.pdf)
        elif args.cmd == "diff":
            result = diff_outputs(args.a, args.b)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except NotImplementedError as e:
        print(f"[brain-pdf] {e}", file=sys.stderr)
        return EX_NOT_IMPLEMENTED


if __name__ == "__main__":
    sys.exit(main())
