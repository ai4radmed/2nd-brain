#!/usr/bin/env python3
"""zip_refine — 압축 첨부(.zip)를 풀어 구성원을 파싱하고 `<원본.zip>_parse/refined.md` 하나로 모은다.

배경(2026-10-16): parser-drain 화이트리스트에 zip 이 없어 `Country Reports.zip`(RAS6097 14개국 docx 보고서)
은 `_parse` 가 영영 안 생겼고, brainify 는 "첨부는 있는데 파싱이 없다"로 `parse_confidence:low` 를 찍었다.
renote-scan 은 `_parse` 0개라 no_source 로 분류해 영구 대기, 무인 드레인 보고가 매 틱 "파싱오류 stub"
으로 셌다 — 2026-08-05 첨부 0건 스레드의 "영원히 안 풀리는 플래그" 와 같은 모양의 zip 판. 선택지는
둘(내용 보존 vs n/a 플래그)이었고 **풀어서 파싱하는 쪽**이 내용 보존에 맞아 이 경로를 택했다.

    python3 zip_refine.py <a.zip> [<b.zip> ...]

레이아웃 (브레인 규약 `<원본>_parse/` 유지 — brainify `_refined_targets` 가 최상위 `*_parse/refined.md` 만 본다):
    <a.zip>_parse/
      members/<구성원 그대로>           ← 안전 추출(경로 탈출·__MACOSX·숨김 제외, 총량·개수 상한)
      members/<구성원>_parse/refined.md ← 구성원별 파싱 산출(동일 규약, 디버그·재파싱용)
      refined.md                        ← 구성원 refined 를 순서대로 이어붙인 **단일 소비 지점**

구성원 파싱 경로(parser-drain 의 포맷별 루프와 같은 잣대):
    hwp/hwpx → hwp_refine.py · xls → xls_refine.py · rtf → rtf_refine.py (호스트)
    pdf/docx/pptx/xlsx → 컨테이너 `docker exec 2nd-brain-parser brain-pdf parse-docling` (단일 엔진 —
      zip 안의 PDF 까지 mineru 듀얼을 돌리진 않는다; 거의 docx 보고서이고 스캔 PDF 면 저신뢰로 표시)
      xlsx 는 docling 실패 시 xlsx_refine.py 폴백
    txt/md/csv → 그대로
    그 외(이미지·오디오·exe·중첩 zip …) → 목록만 남기고 건너뜀(이미지는 별도 OCR 루프 대상이 아니다 —
      `_parse/` 하위는 parser-drain candidates() 가 제외하므로 자동 OCR 이 안 붙는다. 필요하면 수동.)

멱등: `<zip>_parse/refined.md` 가 있으면 호출자(parser-drain)가 부르지 않는다. 구성원 단위로도 refined.md
가 있으면 재파싱하지 않는다(실패 재시도 시 성공분은 보존).
종료코드: 0 = refined.md 작성(일부 실패면 frontmatter 에 low + 목록), 1 = 구성원 하나도 못 읽음 또는 추출 실패.

환경변수: SB_DATA(vault), CMNT(컨테이너 마운트 경로), PARSER_CLI(brain-pdf), PARSER_CONTAINER(2nd-brain-parser),
          ENGINE_TIMEOUT(초), ZIP_MAX_MEMBERS(500), ZIP_MAX_BYTES(500MB)
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import socket
import subprocess
import sys
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
SB_DATA = pathlib.Path(os.environ.get("SB_DATA", os.path.expanduser("~/projects/2nd-brain-vault")))
CMNT = os.environ.get("CMNT", "/home/user/projects/2nd-brain-vault")
PARSER_CLI = os.environ.get("PARSER_CLI", "brain-pdf")
PARSER_CONTAINER = os.environ.get("PARSER_CONTAINER", "2nd-brain-parser")
ENGINE_TIMEOUT = int(os.environ.get("ENGINE_TIMEOUT", "900"))
MAX_MEMBERS = int(os.environ.get("ZIP_MAX_MEMBERS", "500"))
MAX_BYTES = int(os.environ.get("ZIP_MAX_BYTES", str(500 * 1024 * 1024)))

HOST_REFINE = {".hwp": "hwp_refine.py", ".hwpx": "hwp_refine.py", ".xls": "xls_refine.py", ".rtf": "rtf_refine.py"}
CONTAINER_EXT = {".pdf", ".docx", ".pptx", ".xlsx"}
TEXT_EXT = {".txt", ".md", ".csv"}


def log(msg: str) -> None:
    print(f"[zip_refine] {msg}", flush=True)


def _member_name(info: zipfile.ZipInfo) -> str:
    """zip 안 파일명 복원. UTF-8 플래그(0x800)가 없으면 cp437 로 잘못 디코드된 상태라 cp949 로 되돌린다
    (한국 Windows 탐색기 압축의 전형)."""
    name = info.filename
    if info.flag_bits & 0x800:
        return name
    try:
        return name.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def extract(zpath: pathlib.Path, members_dir: pathlib.Path) -> list[pathlib.Path]:
    """안전 추출. 이미 풀려 있으면(마커) 디스크의 파일 목록만 돌려준다."""
    marker = members_dir / ".extracted"
    if marker.exists():
        return sorted(p for p in members_dir.rglob("*") if p.is_file() and "_parse" not in p.parts and p.name != ".extracted")
    members_dir.mkdir(parents=True, exist_ok=True)
    out: list[pathlib.Path] = []
    total = 0
    with zipfile.ZipFile(zpath) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > MAX_MEMBERS:
            raise RuntimeError(f"구성원 {len(infos)}개 > 상한 {MAX_MEMBERS}")
        for info in infos:
            name = _member_name(info)
            parts = pathlib.PurePosixPath(name.replace("\\", "/")).parts
            if not parts or any(p in ("..", "") for p in parts) or name.startswith("/"):
                log(f"skip(경로 탈출): {name}"); continue
            if parts[0] == "__MACOSX" or any(p.startswith(".") for p in parts):
                continue
            total += info.file_size
            if total > MAX_BYTES:
                raise RuntimeError(f"추출 총량 > 상한 {MAX_BYTES // 1048576}MB")
            dest = members_dir.joinpath(*parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(dest, "wb") as dst:
                dst.write(src.read())
            out.append(dest)
    marker.write_text(f"{datetime.datetime.now().isoformat(timespec='seconds')} {len(out)} files\n", encoding="utf-8")
    return sorted(out)


def _front(source: pathlib.Path, engine: str, conf: str, corrections: list[str]) -> str:
    rel = source.relative_to(SB_DATA) if source.is_relative_to(SB_DATA) else source
    lines = ["---", f"source_pdf: {rel}", f"base_engine: {engine}"]
    if corrections:
        lines.append("corrections:")
        lines += [f'  - "{c}"' for c in corrections]
    else:
        lines.append("corrections: []")
    lines += [f"generated: {datetime.date.today().isoformat()}", f"host: {socket.gethostname()}",
              f"refine_confidence: {conf}", "---", ""]
    return "\n".join(lines)


def _strip_front(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


def _write_member_refined(m: pathlib.Path, engine: str, md: str, conf: str, corrections: list[str]) -> pathlib.Path:
    pd = m.parent / (m.name + "_parse")
    pd.mkdir(parents=True, exist_ok=True)
    out = pd / "refined.md"
    out.write_text(_front(m, engine, conf, corrections) + md.rstrip("\n") + "\n", encoding="utf-8")
    return out


def _container_docling(m: pathlib.Path) -> tuple[str | None, str]:
    """컨테이너 docling 1회. 반환 (markdown | None, 오류/비고)."""
    cpath = str(m).replace(str(SB_DATA), CMNT, 1)
    try:
        p = subprocess.run(["docker", "exec", PARSER_CONTAINER, PARSER_CLI, "parse-docling", cpath],
                           capture_output=True, text=True, timeout=ENGINE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None, f"timeout {ENGINE_TIMEOUT}s"
    if p.returncode != 0 or not p.stdout.strip():
        err = (p.stderr or "").strip().splitlines()
        return None, (err[-1] if err else f"rc={p.returncode}")[:200]
    try:
        d = json.loads(p.stdout)
    except json.JSONDecodeError as e:
        return None, f"docling JSON 파싱 실패: {e}"
    pd = m.parent / (m.name + "_parse")
    pd.mkdir(parents=True, exist_ok=True)
    (pd / "docling.json").write_text(p.stdout, encoding="utf-8")
    return d.get("markdown", "") or "", ""


def parse_member(m: pathlib.Path) -> tuple[str, pathlib.Path | None, str]:
    """구성원 1개. 반환 (상태: ok|skip|fail, refined 경로, 비고)."""
    ext = m.suffix.lower()
    pd = m.parent / (m.name + "_parse")
    if (pd / "refined.md").is_file():
        return "ok", pd / "refined.md", "기존 refined 재사용"
    if ext in TEXT_EXT:
        try:
            txt = m.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return "fail", None, str(e)[:200]
        return "ok", _write_member_refined(m, "plain-text", txt, "ok", []), ""
    if ext in HOST_REFINE:
        script = HERE / HOST_REFINE[ext]
        if not script.is_file():
            return "fail", None, f"{script.name} 없음"
        try:
            subprocess.run([sys.executable, str(script), str(m)], capture_output=True, text=True,
                           timeout=ENGINE_TIMEOUT, check=True)
        except Exception as e:  # noqa: BLE001
            return "fail", None, f"{script.name} 실패: {str(e)[-200:]}"
        return ("ok", pd / "refined.md", "") if (pd / "refined.md").is_file() else ("fail", None, f"{script.name}: refined 없음")
    if ext in CONTAINER_EXT:
        md, err = _container_docling(m)
        if md is None and ext == ".xlsx" and (HERE / "xlsx_refine.py").is_file():
            try:
                subprocess.run([sys.executable, str(HERE / "xlsx_refine.py"), str(m)], capture_output=True,
                               text=True, timeout=ENGINE_TIMEOUT, check=True)
                if (pd / "refined.md").is_file():
                    return "ok", pd / "refined.md", "docling 실패 → xlsx-stdlib 폴백"
            except Exception:  # noqa: BLE001
                pass
        if md is None:
            return "fail", None, err
        conf = "ok" if len(md.strip()) >= 20 else "low"
        note = ["zip 구성원 — docling 단일 엔진(mineru 듀얼 미적용)"] if ext == ".pdf" else []
        return "ok", _write_member_refined(m, "docling", md, conf, note), ""
    return "skip", None, f"미지원 확장자 {ext or '(없음)'}"


def refine_zip(zpath: pathlib.Path) -> bool:
    out = zpath.parent / (zpath.name + "_parse")
    members_dir = out / "members"
    try:
        members = extract(zpath, members_dir)
    except (zipfile.BadZipFile, RuntimeError, OSError) as e:
        log(f"✗ 추출 실패: {zpath.name} — {e}")
        return False
    rows: list[tuple[str, pathlib.Path, pathlib.Path | None, str]] = []
    for m in members:
        st, rf, note = parse_member(m)
        rows.append((st, m, rf, note))
        log(f"  {'✓' if st == 'ok' else ('·' if st == 'skip' else '✗')} {m.relative_to(members_dir)} {note}".rstrip())
    ok = [r for r in rows if r[0] == "ok"]
    fail = [r for r in rows if r[0] == "fail"]
    skip = [r for r in rows if r[0] == "skip"]
    if not ok:
        log(f"✗ 읽은 구성원 0 / {len(rows)}: {zpath.name}")
        return False
    corrections = [f"zip 구성원 {len(rows)}개 중 파싱 {len(ok)} · 실패 {len(fail)} · 미지원 {len(skip)}"]
    corrections += [f"실패: {r[1].relative_to(members_dir)} — {r[3]}" for r in fail]
    corrections += [f"미지원: {r[1].relative_to(members_dir)}" for r in skip]
    conf = "ok" if not fail else "low"
    body = [f"# {zpath.name} — 구성원 {len(rows)}개\n"]
    body.append("| # | 구성원 | 상태 | 비고 |\n|---|---|---|---|")
    for i, (st, m, _rf, note) in enumerate(rows, 1):
        body.append(f"| {i} | `{m.relative_to(members_dir)}` | {st} | {note} |")
    body.append("")
    for st, m, rf, _note in rows:
        if st != "ok" or rf is None:
            continue
        body.append(f"\n---\n\n## {m.relative_to(members_dir)}\n")
        body.append(_strip_front(rf.read_text(encoding="utf-8", errors="replace")).rstrip("\n"))
    (out / "refined.md").write_text(_front(zpath, "zip-aggregate", conf, corrections) + "\n".join(body) + "\n",
                                    encoding="utf-8")
    log(f"✓ {zpath.name}: 구성원 {len(ok)}/{len(rows)} → {out / 'refined.md'}")
    return True


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__); return 2
    good = 0
    for a in argv:
        z = pathlib.Path(a).expanduser().resolve()
        if not z.is_file():
            log(f"✗ 파일 없음: {z}"); continue
        if refine_zip(z):
            good += 1
    log(f"성공 {good} / 실패 {len(argv) - good}")
    return 0 if good == len(argv) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
