#!/usr/bin/env python3
r"""pptx-deck-fill — markdown deck source → pptx 산출물

목적
-----
발표·회신용 pptx 의 **작업 표면을 마크다운으로 옮긴다.** 마크다운이 내용 권위,
pptx 는 매번 재생성되는 산출물. hwpx-report-fill 의 pptx 판이며 설계가 평행하다.

    hwpx:  <stem>_fillable.md  ── fill.py ──▶  <stem>_filled.hwpx
    pptx:  <stem>_deck.md      ── fill.py ──▶  <출력 pptx>

왜 이 방식인가 (2026-09-13 Dr. Ben 결정)
------------------------------------------
- pptx 직접 편집: 바이너리라 AI 왕복편집·diff·grep·버전추적이 전부 안 됨.
- Slidev → pptx export: 실측 결과 슬라이드를 통째로 PNG 로 굽는다(텍스트 런 0개).
  받는 쪽이 취합·재편집·텍스트검색을 못 해 제출물로 부적합.
- 이 도구: 편집은 마크다운, 산출물은 **네이티브 텍스트 pptx**. 양식(표지·판형·서식)은
  base pptx 에서 그대로 승계하므로 수신처 양식을 이탈하지 않는다.

마크다운 형식
--------------
frontmatter::

    ---
    base:   sources/.../양식.pptx      # vault-root 상대 또는 절대경로
    output: sources/.../산출물.pptx    # 없으면 -o 로 지정
    title_size: 2400                   # 선택 (1/100 pt)
    body_size:  1600                   # 선택 — ○ 줄
    sub_size:   1350                   # 선택 — - 줄
    ---

본문::

    ## 슬라이드 제목

    ○ 레벨0 문장 (굵게)
    - 레벨1 문장
    - 레벨1 문장

    ```notes
    발표 스크립트. 슬라이드 노트로 들어간다.
    ```

- `## ` = 새 슬라이드. base 의 표지(slide1)는 그대로 보존되고 그 뒤에 붙는다.
- `○` 줄과 `-` 줄 두 단계만 쓴다 (원 양식의 서식 체계).
- ```` ```notes ```` 블록은 선택. 있으면 해당 슬라이드의 발표자 노트가 된다.

사용 예
--------
  fill.py <deck>.md                 # frontmatter 의 output 으로
  fill.py <deck>.md -o out.pptx     # 명시적 출력
  fill.py <deck>.md --dry-run       # 생성 없이 슬라이드·글자수 점검만

설계 메모
----------
- 의존성 없음(zipfile + 문자열 템플릿). python-pptx 는 슬라이드 복제를 정식 지원하지
  않아 deepcopy 우회가 필요한데, 그 우회보다 XML 직접 생성이 서식 재현에 더 정확하다.
- base 의 slide1(표지)·마스터·레이아웃·테마·notesMaster 는 손대지 않고 승계.
  slide2 이후와 notesSlides 만 전량 재생성한다 → 멱등.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

VAULT = Path.home() / "projects" / "2nd-brain-vault"

NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT_SLIDE = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
CT_NOTES = "application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"

DEFAULTS = {
    "title_size": 2400,
    "body_size": 1600,
    "sub_size": 1350,
    # 제목이 길어 양식 기본폭(3799274)으로는 두 줄이 된다. 넓힌 값이 실사용 표준.
    "title_width": 6949440,
    "title_height": 822960,
    "chevron_width": 7132320,
    "font": "맑은 고딕",
}


# ── markdown 파싱 ────────────────────────────────────────────────────────────
def parse_deck(md: str) -> tuple[dict, list[dict]]:
    meta: dict = {}
    body = md
    if md.startswith("---"):
        end = md.find("\n---", 3)
        if end != -1:
            for line in md[3:end].splitlines():
                if ":" in line and not line.strip().startswith("#"):
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.split("  #")[0].strip()
            body = md[end + 4 :]

    slides: list[dict] = []
    cur: dict | None = None
    in_notes = False
    notes_buf: list[str] = []

    for raw in body.splitlines():
        line = raw.rstrip()
        if in_notes:
            if line.strip() == "```":
                in_notes = False
                if cur is not None:
                    cur["notes"] = "\n".join(notes_buf).strip()
                notes_buf = []
            else:
                notes_buf.append(line)
            continue
        if line.strip().startswith("```notes"):
            in_notes = True
            notes_buf = []
            continue
        if line.startswith("## "):
            cur = {"title": line[3:].strip(), "lines": [], "notes": ""}
            slides.append(cur)
            continue
        if cur is None or not line.strip():
            continue
        s = line.strip()
        if s.startswith("○"):
            cur["lines"].append((0, s.lstrip("○").strip()))
        elif s.startswith("- "):
            cur["lines"].append((1, s[2:].strip()))
        elif s.startswith("-"):
            cur["lines"].append((1, s[1:].strip()))
        else:  # 마커 없는 줄 = 직전 단계 이어쓰기로 보지 않고 레벨0 취급
            cur["lines"].append((0, s))

    if in_notes:
        raise SystemExit("오류: ```notes 블록이 닫히지 않았습니다.")
    return meta, slides


def esc(t: str) -> str:
    return (
        t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


# ── XML 생성 ────────────────────────────────────────────────────────────────
def rpr(size: int, bold: int, font: str) -> str:
    return (
        f'<a:rPr sz="{size}" b="{bold}"><a:solidFill><a:srgbClr val="000000"/></a:solidFill>'
        f'<a:latin typeface="{font}"/><a:ea typeface="{font}"/><a:cs typeface="{font}"/></a:rPr>'
    )


def para(level: int, text: str, cfg: dict) -> str:
    font = cfg["font"]
    if level == 0:
        ppr = (
            '<a:pPr algn="just" fontAlgn="base" latinLnBrk="1">'
            '<a:lnSpc><a:spcPct val="200000"/></a:lnSpc>'
            '<a:spcBef><a:spcPts val="400"/></a:spcBef></a:pPr>'
        )
        run = rpr(cfg["body_size"], 1, font) + f"<a:t>○ {esc(text)}</a:t>"
        tail = '<a:endParaRPr lang="ko-KR" altLang="en-US" b="1" dirty="0"/>'
    else:
        ppr = '<a:pPr lvl="1"><a:spcBef><a:spcPts val="100"/></a:spcBef></a:pPr>'
        run = rpr(cfg["sub_size"], 0, font) + f"<a:t>   - {esc(text)}</a:t>"
        tail = ""
    return f"<a:p>{ppr}<a:r>{run}</a:r>{tail}</a:p>"


def slide_xml(sl: dict, cfg: dict) -> str:
    font = cfg["font"]
    paras = "".join(para(lvl, txt, cfg) for lvl, txt in sl["lines"])
    title_run = rpr(cfg["title_size"], 1, font) + f"<a:t>{esc(sl['title'])}</a:t>"
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="{REL}" xmlns:p="{NS_P}"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr><p:sp><p:nvSpPr><p:cNvPr id="12" name="화살표: 갈매기형 수장 11"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="-339634" y="241700"/><a:ext cx="{cfg['chevron_width']}" cy="627469"/></a:xfrm><a:prstGeom prst="chevron"><a:avLst><a:gd name="adj" fmla="val 36121"/></a:avLst></a:prstGeom><a:solidFill><a:schemeClr val="accent2"/></a:solidFill><a:ln w="127000" cap="sq" cmpd="tri"><a:solidFill><a:schemeClr val="accent2"/></a:solidFill><a:bevel/></a:ln></p:spPr><p:style><a:lnRef idx="2"><a:schemeClr val="accent1"><a:shade val="15000"/></a:schemeClr></a:lnRef><a:fillRef idx="1"><a:schemeClr val="accent1"/></a:fillRef><a:effectRef idx="0"><a:schemeClr val="accent1"/></a:effectRef><a:fontRef idx="minor"><a:schemeClr val="lt1"/></a:fontRef></p:style><p:txBody><a:bodyPr rtlCol="0" anchor="ctr"/><a:lstStyle/><a:p><a:pPr algn="ctr"/><a:endParaRPr lang="ko-KR" altLang="en-US"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill></a:endParaRPr></a:p></p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id="2" name="제목 1"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="ctrTitle"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x="-162276" y="0"/><a:ext cx="{cfg['title_width']}" cy="{cfg['title_height']}"/></a:xfrm></p:spPr><p:txBody><a:bodyPr><a:normAutofit/></a:bodyPr><a:lstStyle/><a:p><a:r>{title_run}</a:r><a:endParaRPr lang="ko-KR" altLang="en-US" sz="2000" dirty="0"/></a:p></p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id="5" name="TextBox 4"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="278674" y="1537925"/><a:ext cx="8778240" cy="1401409"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr><p:txBody><a:bodyPr wrap="square"><a:spAutoFit/></a:bodyPr><a:lstStyle/>{paras}</p:txBody></p:sp></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"""


def notes_xml(text: str) -> str:
    paras = "".join(
        f"<a:p><a:r><a:t>{esc(line)}</a:t></a:r></a:p>" for line in text.split("\n") if line.strip()
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:notes xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:p="{NS_P}" xmlns:r="{REL}"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr><p:sp><p:nvSpPr><p:cNvPr id="2" name="Slide Image Placeholder 1"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="sldImg" idx="2"/></p:nvPr></p:nvSpPr><p:spPr/></p:sp><p:sp><p:nvSpPr><p:cNvPr id="3" name="Notes Placeholder 2"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="body" idx="3" sz="quarter"/></p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>{paras}</p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id="4" name="Slide Number Placeholder 3"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="sldNum" idx="5" sz="quarter"/></p:nvPr></p:nvSpPr><p:spPr/></p:sp></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>"""


# ── 패키지 조립 ─────────────────────────────────────────────────────────────
def build(base_pptx: Path, out_pptx: Path, slides: list[dict], cfg: dict) -> None:
    zin = zipfile.ZipFile(base_pptx)
    names = zin.namelist()

    def is_regen(n: str) -> bool:
        """표지(slide1)를 뺀 슬라이드·노트 파트는 전량 재생성한다."""
        if re.match(r"ppt/slides/slide\d+\.xml$", n):
            return n != "ppt/slides/slide1.xml"
        if re.match(r"ppt/slides/_rels/slide\d+\.xml\.rels$", n):
            return n != "ppt/slides/_rels/slide1.xml.rels"
        return "ppt/notesSlides/notesSlide" in n

    # presentation.xml.rels — 슬라이드 관계만 갈아끼운다
    prels = zin.read("ppt/_rels/presentation.xml.rels").decode()
    prels = re.sub(r'<Relationship [^>]*Type="[^"]*/slide"[^>]*/>', "", prels)
    cover_rid = "rId900"
    new_rels = [
        f'<Relationship Id="{cover_rid}" Type="{REL}/slide" Target="slides/slide1.xml"/>'
    ]
    for i in range(len(slides)):
        new_rels.append(
            f'<Relationship Id="rId{901 + i}" Type="{REL}/slide" Target="slides/slide{i + 2}.xml"/>'
        )
    prels = prels.replace("</Relationships>", "".join(new_rels) + "</Relationships>")

    # presentation.xml — sldIdLst 재작성
    pres = zin.read("ppt/presentation.xml").decode()
    ids = [f'<p:sldId id="256" r:id="{cover_rid}"/>']
    ids += [f'<p:sldId id="{257 + i}" r:id="rId{901 + i}"/>' for i in range(len(slides))]
    pres = re.sub(
        r"<p:sldIdLst>.*?</p:sldIdLst>", "<p:sldIdLst>" + "".join(ids) + "</p:sldIdLst>", pres, flags=re.S
    )

    # [Content_Types].xml — slide/notesSlide override 재작성
    ct = zin.read("[Content_Types].xml").decode()
    ct = re.sub(r'<Override PartName="/ppt/slides/slide\d+\.xml"[^>]*/>', "", ct)
    ct = re.sub(r'<Override PartName="/ppt/notesSlides/notesSlide\d+\.xml"[^>]*/>', "", ct)
    ov = [f'<Override PartName="/ppt/slides/slide1.xml" ContentType="{CT_SLIDE}"/>']
    note_no = 0
    for i, sl in enumerate(slides):
        ov.append(f'<Override PartName="/ppt/slides/slide{i + 2}.xml" ContentType="{CT_SLIDE}"/>')
        if sl["notes"]:
            note_no += 1
            ov.append(
                f'<Override PartName="/ppt/notesSlides/notesSlide{note_no}.xml" ContentType="{CT_NOTES}"/>'
            )
    ct = ct.replace("</Types>", "".join(ov) + "</Types>")

    out_pptx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_pptx, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in names:
            if is_regen(n) or n in ("[Content_Types].xml", "ppt/presentation.xml", "ppt/_rels/presentation.xml.rels"):
                continue
            zout.writestr(n, zin.read(n))
        zout.writestr("[Content_Types].xml", ct)
        zout.writestr("ppt/presentation.xml", pres)
        zout.writestr("ppt/_rels/presentation.xml.rels", prels)

        note_no = 0
        for i, sl in enumerate(slides):
            sn = i + 2
            zout.writestr(f"ppt/slides/slide{sn}.xml", slide_xml(sl, cfg))
            rels = [f'<Relationship Id="rId1" Type="{REL}/slideLayout" Target="../slideLayouts/slideLayout3.xml"/>']
            if sl["notes"]:
                note_no += 1
                rels.append(
                    f'<Relationship Id="rId2" Type="{REL}/notesSlide" Target="../notesSlides/notesSlide{note_no}.xml"/>'
                )
                zout.writestr(f"ppt/notesSlides/notesSlide{note_no}.xml", notes_xml(sl["notes"]))
                zout.writestr(
                    f"ppt/notesSlides/_rels/notesSlide{note_no}.xml.rels",
                    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    f'<Relationship Id="rId1" Type="{REL}/notesMaster" Target="../notesMasters/notesMaster1.xml"/>'
                    f'<Relationship Id="rId2" Type="{REL}/slide" Target="../slides/slide{sn}.xml"/>'
                    f"</Relationships>",
                )
            zout.writestr(
                f"ppt/slides/_rels/slide{sn}.xml.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + "".join(rels)
                + "</Relationships>",
            )
    zin.close()


def resolve(p: str, md_path: Path) -> Path:
    path = Path(p).expanduser()
    if path.is_absolute():
        return path
    for cand in (VAULT / p, md_path.parent / p):
        if cand.exists() or cand.parent.exists():
            return cand
    return VAULT / p


def main() -> int:
    ap = argparse.ArgumentParser(description="markdown deck source → pptx")
    ap.add_argument("markdown", help="<stem>_deck.md")
    ap.add_argument("-o", "--output", help="출력 pptx (기본: frontmatter output)")
    ap.add_argument("--base", help="양식 pptx (기본: frontmatter base)")
    ap.add_argument("--dry-run", action="store_true", help="생성 없이 점검만")
    args = ap.parse_args()

    md_path = Path(args.markdown).expanduser().resolve()
    meta, slides = parse_deck(md_path.read_text(encoding="utf-8"))
    if not slides:
        print("오류: '## 제목' 슬라이드가 하나도 없습니다.", file=sys.stderr)
        return 1

    cfg = dict(DEFAULTS)
    for k in DEFAULTS:
        if k in meta:
            cfg[k] = int(meta[k]) if str(meta[k]).isdigit() else meta[k]

    print(f"슬라이드 {len(slides)}매 (+ 표지 1) · 노트 {sum(1 for s in slides if s['notes'])}매")
    for i, sl in enumerate(slides, start=2):
        longest = max((len(t) for _, t in sl["lines"]), default=0)
        warn = "  ⚠ 긴 줄" if longest > 62 else ""
        print(f"  slide{i}: {sl['title'][:44]!r} · {len(sl['lines'])}줄 · 최장 {longest}자{warn}")
    if args.dry_run:
        return 0

    base_s = args.base or meta.get("base")
    out_s = args.output or meta.get("output")
    if not base_s or not out_s:
        print("오류: base/output 이 frontmatter 에도 인자에도 없습니다.", file=sys.stderr)
        return 1
    base_pptx, out_pptx = resolve(base_s, md_path), resolve(out_s, md_path)
    if not base_pptx.exists():
        print(f"오류: 양식이 없습니다 — {base_pptx}", file=sys.stderr)
        return 1
    if out_pptx.exists():
        bak = out_pptx.with_suffix(".pptx.bak")
        shutil.copy2(out_pptx, bak)
        print(f"기존본 백업 → {bak.name}")

    build(base_pptx, out_pptx, slides, cfg)
    print(f"생성 완료 → {out_pptx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
