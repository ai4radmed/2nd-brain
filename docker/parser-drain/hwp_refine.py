#!/usr/bin/env python3
"""호스트-측 HWP/HWPX 추출기 — `<원본>_parse/refined.md` 직접 생산.

배경: 2nd-brain-parser 컨테이너의 HWP 경로(soffice+H2Orestart→docx→docling)는
  ① headless soffice user 프로필 미초기화로 자주 실패하고(inbox 91건 .parse-error)
  ② hwpx 표를 H2Orestart 가 버린다.
호스트엔 이미 검증된 우월 경로가 있다(radsafety-laws/_parse_attachments.py):
  · hwpx = OWPML(개방형 XML) 직독 → LibreOffice 완전 우회 → 무손실 표 복원
  · hwp  = soffice(+H2Orestart)→docx→pandoc gfm(병합셀 clean HTML)
HWP 는 단일소스(mineru N/A·diff 불가)라 refine 이 no-op → 추출=refine 을 한 번에 하고
refined.md 를 곧장 쓴다. brainify `_refined()` 가 이 refined.md 를 소비하며 컨테이너를 안 탄다.

전제: soffice(+H2Orestart 확장, user 프로필) · pandoc. 없으면 해당 파일 실패(.parse-error).
사용: hwp_refine.py <파일.hwp|.hwpx> [<파일2> ...]
  각 파일에 대해 `<파일>_parse/refined.md` 생성(멱등: 있으면 skip), .parse-error 제거.
반환코드: 전건 성공 0, 일부/전부 실패 1.
"""
import sys, os, re, struct, subprocess, tempfile, shutil, zipfile, socket, datetime, zlib
import xml.etree.ElementTree as ET

VAULT = os.environ.get("SB_DATA", os.path.expanduser("~/projects/2nd-brain-vault"))
HOST = socket.gethostname()
TODAY = datetime.date.today().isoformat()


# ── OWPML(hwpx) 직접 파싱 — LibreOffice 우회(radsafety-laws 검증 로직 이식) ──
def _ln(tag):
    return tag.split("}")[-1]


def _owpml_hyperlink_url(field_begin):
    """fieldBegin(type=HYPERLINK) 의 parameters 에서 URL 추출 — Path 우선, 없으면 Command 정리."""
    for sp in field_begin.iter():
        if _ln(sp.tag) == "stringParam" and sp.get("name") == "Path":
            return (sp.text or "").strip()
    for sp in field_begin.iter():
        if _ln(sp.tag) == "stringParam" and sp.get("name") == "Command":
            # "URL;n;n;n" 형태 — 세미콜론 뒤 메타데이터 제거
            return (sp.text or "").split(";")[0].strip()
    return None


# 그림 컨텍스트 — parse_hwpx 가 파일마다 리셋. {id: (파일명, 폭, 높이)}
_IMG = {"map": {}, "hits": 0, "docx": []}
MIN_IMG_PX = 200          # 이 미만(긴 변)은 장식으로 보고 본문 마커 생략(추출은 함)


def _img_size(data):
    """BMP/JPEG/PNG 픽셀 크기 sniff (stdlib). 모르면 (0, 0)."""
    try:
        if data[:2] == b"BM":
            w, h = struct.unpack_from("<ii", data, 18)
            return abs(w), abs(h)
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack_from(">II", data, 16)
            return w, h
        if data[:2] == b"\xff\xd8":                    # JPEG — SOF0~SOF15 세그먼트 탐색
            i = 2
            while i < len(data) - 9:
                if data[i] != 0xFF:
                    i += 1
                    continue
                m = data[i + 1]
                if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack_from(">HH", data, i + 5)
                    return w, h
                i += 2 + struct.unpack_from(">H", data, i + 2)[0]
    except Exception:
        pass
    return 0, 0


def _owpml_img_marker(el):
    """<hc:img binaryItemIDRef="imageN"/> → 누락 사실을 남기는 마커.

    OWPML 은 그림을 BinData 바이너리로 품고 있어 텍스트 추출에서 **소리 없이 사라진다**.
    PDF 경로(docling)가 `<!-- image -->` 를 남기는 것과 달리 흔적조차 없어, 도식이 있었다는
    사실 자체를 잃는다(2026-09-13 실측: 제1차 원자력안전종합계획 hwpx 에 내용 도식 2개 —
    계획 위상도·5개년 로드맵 — 이 통째로 유실, refined.md 의 이미지 표기 0건).
    → 위치에 마커를 남기고 실물은 `_parse/images/` 로 꺼내 `Read` 로 볼 수 있게 한다.
    """
    ref = el.get("binaryItemIDRef")
    name, w, h = _IMG["map"].get(ref, (ref or "?", 0, 0))
    # 장식(글머리 아이콘·구분선 등)은 마커를 내지 않는다 — 실측상 72×72 아이콘 하나가
    # 12번 반복돼 본문을 덮었다. 파일은 그대로 추출되므로 유실이 아니라 소음 제거다.
    # 크기를 모르면(sniff 실패) 마커를 낸다 — 놓치는 쪽보다 시끄러운 쪽이 안전.
    if w and h and max(w, h) < MIN_IMG_PX:
        return ""
    _IMG["hits"] += 1
    dim = f" {w}×{h}" if w and h else ""
    return f"\n<!-- image: images/{name}{dim} -->\n"


def _owpml_ptext(p):
    """문단 텍스트 추출. HWPHYPERLINK 필드(fieldBegin~fieldEnd)는 마크다운 [텍스트](URL) 로 변환."""
    parts = []
    link_stack = []  # [(begin_id, url, parts에서 시작 인덱스)]
    for el in p.iter():
        ln = _ln(el.tag)
        if ln == "t":
            parts.append("".join(el.itertext()))
        elif ln == "img":
            parts.append(_owpml_img_marker(el))
        elif ln == "fieldBegin" and el.get("type") == "HYPERLINK":
            url = _owpml_hyperlink_url(el)
            if url:
                link_stack.append((el.get("id"), url, len(parts)))
        elif ln == "fieldEnd" and link_stack and el.get("beginIDRef") == link_stack[-1][0]:
            begin_id, url, start = link_stack.pop()
            text = "".join(parts[start:])
            del parts[start:]
            parts.append(f"[{text}]({url})" if text else url)
    return "".join(parts)


def _owpml_has_tbl(e):
    return any(_ln(d.tag) == "tbl" for d in e.iter())


def _owpml_cell(tc):
    sub = next((c for c in tc if _ln(c.tag) == "subList"), None)
    if sub is None:
        return ""
    out = []
    for p in sub:
        if _ln(p.tag) != "p":
            continue
        if _owpml_has_tbl(p):
            _owpml_walk(p, out)
        else:
            t = _owpml_ptext(p).strip()
            if t:
                out.append(t)
    return "\n".join(out)


def _owpml_table(tbl):
    rows = ["<table>"]
    for tr in (c for c in tbl if _ln(c.tag) == "tr"):
        rows.append("<tr>")
        for tc in (c for c in tr if _ln(c.tag) == "tc"):
            span = next((c for c in tc if _ln(c.tag) == "cellSpan"), None)
            cs = int(span.get("colSpan", "1")) if span is not None else 1
            rs = int(span.get("rowSpan", "1")) if span is not None else 1
            a = (f' colspan="{cs}"' if cs > 1 else "") + (f' rowspan="{rs}"' if rs > 1 else "")
            rows.append(f"<td{a}>{_owpml_cell(tc)}</td>")
        rows.append("</tr>")
    rows.append("</table>")
    return "\n".join(rows)


def _owpml_walk(elem, out):
    for ch in elem:
        ln = _ln(ch.tag)
        if ln == "tbl":
            out.append(_owpml_table(ch))
        elif ln == "p":
            if _owpml_has_tbl(ch):
                _owpml_walk(ch, out)
            else:
                t = _owpml_ptext(ch).strip()
                if t:
                    out.append(t)
        else:
            _owpml_walk(ch, out)


def _extract_images(z, parse_dir):
    """BinData 이미지를 `_parse/images/` 로 꺼내고 {id: (파일명, 폭, 높이)} 맵을 만든다.

    id→href 매핑 권위 = `Contents/content.hpf` 의 <opf:item id=".." href="BinData/..">.
    Preview/PrvImage 는 한글이 만든 썸네일이라 제외(문서 내용 아님).
    """
    mapping = {}
    try:
        hpf = z.read("Contents/content.hpf").decode("utf-8", "ignore")
    except KeyError:
        hpf = ""
    items = dict(re.findall(r'<opf:item[^>]*id="([^"]+)"[^>]*href="(BinData/[^"]+)"', hpf))
    if not items:                                      # hpf 없으면 BinData 를 그대로
        items = {os.path.splitext(os.path.basename(n))[0]: n
                 for n in z.namelist() if n.startswith("BinData/")}
    if not items:
        return mapping
    img_dir = os.path.join(parse_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    for iid, href in items.items():
        try:
            data = z.read(href)
        except KeyError:
            continue
        base = os.path.basename(href)
        with open(os.path.join(img_dir, base), "wb") as f:
            f.write(data)
        w, h = _img_size(data)
        mapping[iid] = (base, w, h)
    return mapping


def parse_hwpx(path):
    """hwpx → 문단+표(HTML) markdown. 실패 시 '' (호출부가 docx 폴백)."""
    _IMG["map"], _IMG["hits"], _IMG["docx"] = {}, 0, []
    try:
        with zipfile.ZipFile(path) as z:
            _IMG["map"] = _extract_images(z, path + "_parse")
            secs = sorted(n for n in z.namelist()
                          if re.match(r"Contents/section\d+\.xml", n))
            out = []
            for n in secs:
                _owpml_walk(ET.fromstring(z.read(n)), out)
        return re.sub(r"\n{3,}", "\n\n", "\n\n".join(out)).strip()
    except Exception as e:
        print(f"  ? OWPML 파싱 실패({e}) → docx 폴백", file=sys.stderr)
        return ""


# ── HWP 3.0(구형, OLE2 아님): raw-deflate + Johab 직접 디코딩 ──
# 근거: EM/PINT(원내 특허관리 시스템)가 찍어내는 양도증이 이 포맷 — soffice("source file
# could not be loaded")·hwp-mcp("not an OLE2 structured storage file")·OWPML 모두 실패한다
# (2026-09-11 최초 실측, [[hwp3-em-yangdo-extraction]]). offset 1166 부터 raw deflate 로
# 풀면 2바이트 LE 코드 스트림이 나오고, ASCII(32~126)는 그대로, 한글 영역(0x8441~0xD3BD)은
# Johab 으로 디코딩된다. 제어 레코드가 스트림 중간중간 홀수 바이트를 끼워 넣어 정렬이 구간마다
# 어긋나므로(parity 0 이 맞는 구간·1 이 맞는 구간이 섞여 있음 — 2026-09-18 재검증: 실제로 한
# 서명자(오세영) 이름이 parity 0 단독 스캔에서는 통째로 빠지고 parity 1 에만 나타났다) 두
# parity 를 모두 스캔해 합친다. 도장(인영) 이미지 자리는 짧은 무의미 한글 조각(예: '뼴뽔')으로
# 남는데, 실제로 이미지가 아니라 파싱 불가 이진 조각이라 정렬을 맞춰도 사라지지 않는다 —
# 지우지 않고 그대로 둔다(다른 hwp 경로의 이미지 마커와 같은 원칙: 숨기는 것보다 시끄러운 게
# 안전). 2자 이하 조각은 전체 잡음의 71%(2026-09-18 실측: 16640→4821줄)를 차지해 걸러내되,
# 실명 최소 길이가 3자(예: '김병일')라 그 밑으로는 안 자른다.
HWP3_MAGIC = b"HWP Document File V3"


def is_hwp3(path):
    try:
        with open(path, "rb") as f:
            return f.read(len(HWP3_MAGIC)) == HWP3_MAGIC
    except OSError:
        return False


def _hwp3_decode_stream(raw, parity):
    runs, buf, start = [], [], None
    i, n = parity, len(raw)
    while i + 1 < n:
        code = raw[i] | (raw[i + 1] << 8)
        ch = None
        if 32 <= code <= 126:
            ch = chr(code)
        elif 0x8441 <= code <= 0xD3BD:
            try:
                ch = bytes([code >> 8, code & 0xFF]).decode("johab")
            except UnicodeDecodeError:
                ch = None
        if ch is not None:
            if start is None:
                start = i
            buf.append(ch)
        else:
            if buf:
                runs.append((start, "".join(buf)))
                buf, start = [], None
        i += 2
    if buf:
        runs.append((start, "".join(buf)))
    return runs


def parse_hwp3(path):
    """HWP 3.0 → raw-deflate(offset 1166)+Johab, parity 0·1 병합. 실패 시 ''."""
    try:
        data = open(path, "rb").read()
        raw = zlib.decompressobj(-15).decompress(data[1166:])
    except (OSError, zlib.error) as e:
        print(f"  ? HWP3 raw-deflate 실패({e})", file=sys.stderr)
        return ""
    runs = _hwp3_decode_stream(raw, 0) + _hwp3_decode_stream(raw, 1)
    runs = [(s, t.strip()) for s, t in runs if len(t.strip()) >= 3]
    runs.sort(key=lambda r: r[0])
    body = "\n".join(t for _, t in runs)
    return re.sub(r"\n{2,}", "\n", body).strip()


# ── hwp(바이너리): soffice→docx→pandoc ──
def clean_md(body):
    """docx→gfm 산출 정리: colgroup 노이즈 + 바깥 페이지-래퍼 표 제거(내용 무손실)."""
    body = re.sub(r"<colgroup>.*?</colgroup>\s*", "", body, flags=re.S)
    m = re.match(r"^<table>\s*<tbody>\s*<tr[^>]*>\s*<td>(.*)</td>\s*</tr>\s*"
                 r"</tbody>\s*</table>\s*$", body, re.S)
    if m:
        body = m.group(1)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def _docx_images(docx, parse_dir):
    """중간 docx 의 그림을 `_parse/images/` 로 꺼내고 **문서순** 목록을 만든다.

    hwp 경로에도 hwpx 와 같은 그림 유실이 있다 — 다만 사라지는 지점이 다르다:
    soffice 가 만든 docx 에는 그림이 `word/media/` 에 **멀쩡히 남아 있고**, 그 다음
    `pandoc -t gfm` 이 버린다(실측: LibreOffice 가 그림을 `w:pict` 로 감싸 내보내는데
    pandoc docx 리더가 이를 건너뛴다 → `--extract-media` 를 줘도 마크다운에 `![]` 참조가
    0건). 따라서 pandoc 에 맡기지 않고 직접 꺼낸다.

    ⚠️ hwpx(OWPML) 와 달리 **본문 위치를 복원하지 못한다** — 마크다운 어느 지점에 붙은
    그림인지 대응시킬 앵커가 없다. 그래서 위치 마커 대신 *문서순 인벤토리*를 끝에 붙인다.
    목적은 위치 재현이 아니라 **"그림이 있었다"는 사실과 실물을 잃지 않는 것**이다.
    """
    try:
        with zipfile.ZipFile(docx) as z:
            names = z.namelist()
            rels = z.read("word/_rels/document.xml.rels").decode("utf-8", "ignore")
            rid2tgt = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
            doc = z.read("word/document.xml").decode("utf-8", "ignore")
            order = [rid2tgt.get(r) for r in
                     re.findall(r'<(?:a:blip|v:imagedata)[^>]*r:(?:embed|id)="([^"]+)"', doc)]
            seen, ordered = set(), []
            for tgt in order:                          # 문서순, 중복 참조는 1회만
                if tgt and tgt not in seen:
                    seen.add(tgt)
                    ordered.append(tgt)
            for n in names:                            # 문서에서 참조 안 된 media 도 보존
                t = n.replace("word/", "", 1)
                if n.startswith("word/media/") and t not in seen:
                    seen.add(t)
                    ordered.append(t)
            if not ordered:
                return []
            img_dir = os.path.join(parse_dir, "images")
            os.makedirs(img_dir, exist_ok=True)
            out = []
            for tgt in ordered:
                src = "word/" + tgt.lstrip("/")
                if src not in names:
                    continue
                data = z.read(src)
                base = os.path.basename(tgt)
                with open(os.path.join(img_dir, base), "wb") as f:
                    f.write(data)
                w, h = _img_size(data)
                out.append((base, w, h))
            return out
    except Exception as e:
        print(f"  ? docx 그림 추출 실패({e}) — 본문은 정상", file=sys.stderr)
        return []


def parse_hwp(path, tmp):
    """hwp → docx(soffice) → gfm(pandoc) → clean_md. 실패 시 ''."""
    subprocess.run(["soffice", "--headless", "--convert-to", "docx", "--outdir", tmp, path],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    stem = os.path.splitext(os.path.basename(path))[0]
    docx = os.path.join(tmp, stem + ".docx")
    if not os.path.exists(docx) or os.path.getsize(docx) < 200:
        return ""
    _IMG["docx"] = _docx_images(docx, path + "_parse")
    raw = subprocess.run(["pandoc", "-f", "docx", "-t", "gfm", "--wrap=none", docx],
                         capture_output=True, text=True).stdout
    return clean_md(raw)


def relink_images(body):
    """pandoc 이 남긴 media/ 참조를 `_parse/images/` 로 돌려놓고, 살아남은 파일명을 돌려준다.

    pandoc 은 이 docx 의 그림 일부를 markdown `![]()` 가 아니라 **원시 HTML**
    `<img src="media/imageN.png" .../>` 로 내보낸다(그래서 `![` grep 이 0건이었다).
    그 참조는 존재하지 않는 `media/` 를 가리키므로 그대로 두면 깨진 링크다 —
    실제 추출 위치인 `images/` 로 고쳐 **위치 정보를 살린다**.
    """
    seen = set()

    def sub(m):
        name = os.path.basename(m.group(2))
        seen.add(name)
        return m.group(1) + "images/" + name

    body = re.sub(r'(src=")(?:\./)?media/([^"]+)', sub, body)
    body = re.sub(r'(\]\()(?:\./)?media/([^)\s]+)', sub, body)
    return body, seen


def image_inventory(items, linked):
    """본문에 위치가 안 잡힌 그림만 문서순 목록으로. 장식은 제외하되 파일은 남아 있다."""
    rows = [f"<!-- image: images/{n}{f' {w}×{h}' if w and h else ''} -->"
            for n, w, h in items
            if n not in linked and not (w and h and max(w, h) < MIN_IMG_PX)]
    if not rows:
        return ""
    return ("\n\n## 그림 (문서순 · 본문 위치 미상)\n\n"
            "hwp→docx→pandoc 경로는 일부 그림의 본문 위치를 복원하지 못한다(본문에 "
            "`<img src=\"images/...\">` 로 들어간 것은 위치가 살아 있다). 실물은 "
            "`_parse/images/` 에 있으니 필요하면 `Read` 로 직접 볼 것.\n\n" + "\n".join(rows))


def vault_rel(path):
    try:
        return os.path.relpath(path, VAULT)
    except ValueError:
        return path


def refined_frontmatter(src_path, engine, images=0):
    img = (f"images: {images}   # _parse/images/ 로 추출. 본문 참조(<!-- image: --> 마커 또는 "
           f"<img src=images/..>)는 긴 변 {MIN_IMG_PX}px 이상만(장식 제외)\n") if images else ""
    return (f"---\n"
            f"source_pdf: {vault_rel(src_path)}\n"
            f"base_engine: {engine}\n"
            f"corrections: []\n"
            f"{img}"
            f"generated: {TODAY}\n"
            f"host: {HOST}\n"
            f"refine_confidence: ok\n"
            f"---\n\n")


def process(path, tmp):
    """파일 1개 → refined.md 생산. (ok, engine|err)."""
    parse_dir = path + "_parse"
    out = os.path.join(parse_dir, "refined.md")
    os.makedirs(parse_dir, exist_ok=True)
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    if ext != "hwpx" and is_hwp3(path):
        body = parse_hwp3(path)
        engine = "hwp3-rawdeflate-johab"
    elif ext == "hwpx":
        body = parse_hwpx(path)
        engine = "owpml"
        if not body:                                   # OWPML 실패 → docx 폴백
            body = parse_hwp(path, tmp)
            engine = "hwpx-libreoffice-pandoc"
    else:
        body = parse_hwp(path, tmp)
        engine = "hwp-libreoffice-pandoc"
    if not body:
        open(os.path.join(parse_dir, ".parse-error"), "w").close()
        reason = ("HWP3 raw-deflate/Johab 실패" if engine == "hwp3-rawdeflate-johab"
                  else "본문 추출 실패(soffice/pandoc/OWPML 모두)")
        return False, reason
    if engine == "owpml":
        n_img = len(_IMG["map"])
    elif engine == "hwp3-rawdeflate-johab":
        n_img = 0                                       # 이미지 추출 미지원 — 도장 등은 잡음 조각으로 남음
    else:                                              # hwp·hwpx-폴백 = docx 경유
        body, linked = relink_images(body)
        body += image_inventory(_IMG["docx"], linked)
        n_img = len(_IMG["docx"])
    open(out, "w", encoding="utf-8").write(refined_frontmatter(path, engine, n_img) + body + "\n")
    err = os.path.join(parse_dir, ".parse-error")
    if os.path.exists(err):
        os.remove(err)                                 # 재실행 성공 시 실패마커 제거
    return True, engine


def main(argv):
    files = argv[1:]
    if not files:
        print("사용: hwp_refine.py <파일.hwp|.hwpx> [...]", file=sys.stderr)
        return 2
    missing = [t for t in ("soffice", "pandoc") if not shutil.which(t)]
    if missing:
        print(f"[hwp_refine] 도구 미설치: {' '.join(missing)} → 중단", file=sys.stderr)
        return 3
    tmp = tempfile.mkdtemp(prefix="hwp_refine_")
    ok = 0
    fail = []
    try:
        for f in files:
            if not os.path.exists(f):
                fail.append((f, "파일 없음"))
                continue
            out = f + "_parse/refined.md"
            if os.path.exists(out):                     # 멱등
                print(f"  skip(이미 refined): {os.path.basename(f)}")
                ok += 1
                continue
            good, info = process(f, tmp)
            if good:
                ok += 1
                print(f"  ok({info}): {os.path.basename(f)}")
            else:
                fail.append((f, info))
                print(f"  FAIL({info}): {os.path.basename(f)}", file=sys.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n[hwp_refine] 성공 {ok} / 실패 {len(fail)}")
    for f, why in fail:
        print(f"     ✗ {os.path.basename(f)} — {why}")
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
