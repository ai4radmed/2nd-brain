#!/usr/bin/env python3
"""xls_refine — 구형 엑셀(.xls, BIFF5/BIFF8)을 표준 라이브러리만으로 markdown 표로 추출한다.

    python3 xls_refine.py <파일.xls> [...]

`xlsx_refine.py` 의 .xls 짝. 산출물 규약(`refined.md`·frontmatter)은 동일하고 **읽는 방식만**
다르다 — .xlsx 는 zip+XML 이지만 .xls 는 OLE 복합문서(CFB) 안의 `Workbook` 바이너리 스트림이다.

**왜 stdlib 인가.** 이 vault 에서 .xls 를 여는 다른 경로가 전부 막혀 있다 (2026-08-07 실측):
  · `soffice --convert-to xlsx/csv` → `no export filter` / `source file could not be loaded`.
    호스트에 **libreoffice-calc 가 미설치**다(writer·math 만). hwp→pandoc 경로가 멀쩡한 것과
    대조적 — 그쪽은 writer 필터라서다.
  · 컨테이너(parser-drain)에는 soffice 자체가 없다.
  · docling 은 .xls 를 입력으로 받지 않는다.
apt 로 libreoffice-calc 를 깔면 kimbi 만 되고 ai4lt·컨테이너는 조용히 실패하는 **비대칭**이
생긴다. stdlib 단독이면 git 으로 따라가고 어디서든 같게 동작한다.

한계(xlsx_refine 와 동일한 선):
  · 수식은 **계산 결과값**만. 원본 수식 문자열은 버린다.
  · 서식·병합·차트·이미지는 버린다. 표의 *내용*만 남긴다.
  · 날짜는 엑셀 시리얼 숫자로 남는다(서식을 안 보므로). 정확한 표시가 필요하면 원본을 연다.
  · 암호화된 .xls(FILEPASS 레코드)는 거부한다 — 복호화는 범위 밖.

**확장자가 .xls 라고 다 BIFF 는 아니다.** 관공서 웹시스템은 HTML `<table>` 을 그대로 .xls 로
내려준다(2026-08-07 실측: 양천구 재산세 고지). 매직바이트로 갈라 HTML 이면 `<table>` 을 직독한다
— 이 부류가 soffice 에서 "source file could not be loaded" 로 뜨는 진짜 이유다(필터 부재가 아니라
정말로 엑셀이 아니어서).
"""
from __future__ import annotations

import datetime
import os
import pathlib
import socket
import struct
import sys
from html.parser import HTMLParser

MAX_ROWS = int(os.environ.get("XLS_MAX_ROWS", os.environ.get("XLSX_MAX_ROWS", "2000")))
FREE = 0xFFFFFFFA          # CFB: 이 값 이상은 종료·특수 섹터 표식
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
LAST_WARN = ""            # 파싱 중 발견한 무결성 경고(SST 개수 불일치 등)


# ── CFB(OLE 복합문서) ────────────────────────────────────────────────────────
def cfb_streams(raw: bytes) -> dict[str, bytes]:
    """복합문서에서 {스트림 이름: 바이트} 를 뽑는다. 512B 헤더 + FAT/miniFAT 체인."""
    if raw[:8] != OLE_MAGIC:
        raise ValueError("OLE 복합문서가 아님")
    ssz = 1 << struct.unpack_from("<H", raw, 0x1E)[0]        # 섹터 크기(보통 512)
    mssz = 1 << struct.unpack_from("<H", raw, 0x20)[0]       # 미니섹터 크기(보통 64)
    n_fat, dir_start = struct.unpack_from("<II", raw, 0x2C)
    cutoff = struct.unpack_from("<I", raw, 0x38)[0]          # 미니스트림 경계(보통 4096)
    mini_start = struct.unpack_from("<I", raw, 0x3C)[0]
    difat_start, n_difat = struct.unpack_from("<II", raw, 0x44)

    def sect(n: int) -> bytes:
        off = 512 + n * ssz
        return raw[off:off + ssz]

    # DIFAT: 헤더 안 109개 + 추가 DIFAT 섹터 체인
    difat = list(struct.unpack_from("<109I", raw, 0x4C))
    s, per = difat_start, ssz // 4 - 1
    for _ in range(n_difat):
        if s >= FREE:
            break
        d = sect(s)
        difat += list(struct.unpack_from(f"<{per}I", d, 0))
        s = struct.unpack_from("<I", d, ssz - 4)[0]

    fat: list[int] = []
    for fs in difat[:n_fat]:
        if fs < FREE:
            fat += list(struct.unpack_from(f"<{ssz // 4}I", sect(fs), 0))

    def chain(start: int, table: list[int]) -> list[int]:
        out, seen, s = [], set(), start
        while s < FREE and s < len(table) and s not in seen:
            seen.add(s)
            out.append(s)
            s = table[s]
        return out

    def read_fat(start: int, size: int) -> bytes:
        return b"".join(sect(x) for x in chain(start, fat))[:size]

    minifat: list[int] = []
    for s in chain(mini_start, fat):
        minifat += list(struct.unpack_from(f"<{ssz // 4}I", sect(s), 0))

    dirdata = b"".join(sect(x) for x in chain(dir_start, fat))
    if len(dirdata) < 128:
        raise ValueError("디렉터리 엔트리 없음")
    mini_stream = b"".join(sect(x) for x in
                           chain(struct.unpack_from("<I", dirdata, 0x74)[0], fat))

    def read_mini(start: int, size: int) -> bytes:
        out, seen, s = [], set(), start
        while s < FREE and s < len(minifat) and s not in seen:
            seen.add(s)
            out.append(mini_stream[s * mssz:(s + 1) * mssz])
            s = minifat[s]
        return b"".join(out)[:size]

    streams: dict[str, bytes] = {}
    for i in range(0, len(dirdata) - 127, 128):
        e = dirdata[i:i + 128]
        nlen = struct.unpack_from("<H", e, 0x40)[0]
        if e[0x42] != 2 or nlen < 4:                     # type 2 = 스트림만
            continue
        name = e[:nlen - 2].decode("utf-16-le", "ignore")
        start = struct.unpack_from("<I", e, 0x74)[0]
        size = min(struct.unpack_from("<I", e, 0x78)[0], len(raw))
        streams[name] = read_mini(start, size) if size < cutoff else read_fat(start, size)
    return streams


# ── BIFF 문자열 ─────────────────────────────────────────────────────────────
def _legacy(b: bytes) -> str:
    """BIFF5 바이트 문자열 — 코드페이지를 안 읽고 한국어 우선으로 시도."""
    for enc in ("cp949", "cp1252", "utf-8"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("cp949", "replace")


class _Cursor:
    """SST 전용 커서. CONTINUE 경계에서 **플래그 바이트가 다시 나온다**는 BIFF8 의 함정 때문에
    레코드들을 이어붙이지 않고 조각 목록 그대로 훑는다."""

    def __init__(self, chunks: list[bytes]):
        self.chunks, self.i, self.p = chunks, 0, 0

    def _roll(self) -> bool:
        while self.i < len(self.chunks) and self.p >= len(self.chunks[self.i]):
            self.i += 1
            self.p = 0
        return self.i < len(self.chunks)

    def eof(self) -> bool:
        return not self._roll()

    def take(self, n: int) -> bytes:
        """**현재 조각 안에서만** — 문자 데이터 전용. 조각을 넘으면 새 플래그를 읽어야 하므로
        여기서 자동으로 넘어가면 안 된다."""
        self._roll()
        if self.i >= len(self.chunks):
            return b""
        b = self.chunks[self.i][self.p:self.p + n]
        self.p += len(b)
        return b

    def raw(self, n: int) -> bytes:
        """조각을 **넘나들며** n 바이트. 헤더·리치런·phonetic 처럼 플래그가 끼지 않는 구간용.
        이걸 조각 안으로 가두면(초판 버그) 리치런이 CONTINUE 에 걸릴 때 덜 소비하고,
        그 뒤 SST 전체가 한 칸씩 밀려 UTF-16 이 바이트로 새어 나온다(2026-08-07 실측)."""
        out = b""
        while n > 0 and self._roll():
            b = self.chunks[self.i][self.p:self.p + n]
            self.p += len(b)
            out += b
            n -= len(b)
        return out

    def u8(self) -> int:
        b = self.raw(1)
        return b[0] if b else 0

    def u16(self) -> int:
        b = self.raw(2)
        return struct.unpack("<H", b)[0] if len(b) == 2 else 0

    def u32(self) -> int:
        b = self.raw(4)
        return struct.unpack("<I", b)[0] if len(b) == 4 else 0

    def string(self) -> str:
        """XLUnicodeRichExtendedString — 문자 데이터가 CONTINUE 를 넘어가면 새 플래그를 읽는다."""
        cch = self.u16()
        flags = self.u8()
        n_run = self.u16() if flags & 0x08 else 0
        n_ext = self.u32() if flags & 0x04 else 0
        wide = bool(flags & 0x01)
        parts, left = [], cch
        while left > 0 and self._roll():
            cur = self.i
            avail = len(self.chunks[cur]) - self.p
            take = min(left, avail // 2 if wide else avail)
            if take > 0:
                buf = self.take(take * 2 if wide else take)
                # 압축형(fHighByte=0)은 **Latin-1** 이다 — UTF-16 하위바이트만 저장한 형태라
                # 비-Latin1 문자가 하나라도 있으면 엑셀이 wide 로 쓴다. cp949 로 읽으면 안 된다.
                parts.append(buf.decode("utf-16-le", "ignore") if wide else buf.decode("latin-1"))
                left -= take
            if left > 0:
                # 조각을 다 썼는데 글자가 남았다 = 문자열이 CONTINUE 로 이어진다.
                # → 다음 조각의 **첫 바이트는 새 플래그**다. 이 재읽기를 `take<=0` 조건에 걸어
                #   두면(초판) 압축형에서는 avail 이 0 이 될 일이 없어 **영원히 발동하지 않는다**.
                #   그러면 플래그 바이트를 글자로 먹고 길이가 밀려 SST 뒷부분이 통째로 날아간다
                #   (2026-08-07 실측: 1825행 중 252행 이후 문자열 소실).
                self.i, self.p = cur + 1, 0
                if self.i >= len(self.chunks):
                    break
                wide = bool(self.u8() & 0x01)
        self.raw(4 * n_run)          # 리치런·phonetic 은 CONTINUE 를 넘어갈 수 있다
        self.raw(n_ext)
        return "".join(parts)


def _short_string(data: bytes, off: int, biff8: bool) -> str:
    """BOUNDSHEET 의 시트 이름 (길이 1바이트)."""
    cch = data[off]
    if not biff8:
        return _legacy(data[off + 1:off + 1 + cch])
    flags = data[off + 1]
    body = data[off + 2:]
    return body[:cch * 2].decode("utf-16-le", "ignore") if flags & 1 else _legacy(body[:cch])


def _rk(v: int) -> float:
    if v & 2:
        iv = v >> 2
        if iv & 0x20000000:
            iv -= 0x40000000
        num = float(iv)
    else:
        num = struct.unpack("<d", struct.pack("<Q", (v & 0xFFFFFFFC) << 32))[0]
    return num / 100.0 if v & 1 else num


def _num(x: float) -> str:
    return str(int(x)) if x == int(x) and abs(x) < 1e15 else repr(round(x, 10))


# ── BIFF 워크북 ─────────────────────────────────────────────────────────────
def _records(buf: bytes, pos: int = 0):
    while pos + 4 <= len(buf):
        rt, ln = struct.unpack_from("<HH", buf, pos)
        yield pos, rt, buf[pos + 4:pos + 4 + ln]
        pos += 4 + ln


def parse_workbook(buf: bytes) -> list[tuple[str, list[list[str]]]]:
    """{시트이름: 행들} 을 문서 순서대로. 전역 substream 에서 SST·BOUNDSHEET 를 먼저 읽는다."""
    global LAST_WARN
    LAST_WARN = ""
    biff8, sheets, sst_chunks, sst, prev, n_unique = True, [], None, [], None, 0
    for pos, rt, data in _records(buf):
        if rt == 0x0809 and pos == 0:                                # BOF
            biff8 = struct.unpack_from("<H", data, 0)[0] >= 0x0600
        elif rt == 0x002F:                                           # FILEPASS
            raise ValueError("암호로 보호된 통합문서 — 복호화 불가")
        elif rt == 0x0085:                                           # BOUNDSHEET
            off, dt = struct.unpack_from("<I", data, 0)[0], data[5]
            sheets.append((off, dt, _short_string(data, 6, biff8)))
        elif rt == 0x00FC:                                           # SST
            n_unique = struct.unpack_from("<I", data, 4)[0]
            sst_chunks = [data[8:]]
        elif rt == 0x003C and sst_chunks is not None and prev in (0x00FC, 0x003C):
            sst_chunks.append(data)
        elif rt == 0x000A and sheets:                                # 전역 substream 끝
            break
        prev = rt

    if sst_chunks:
        cur = _Cursor(sst_chunks)
        while not cur.eof() and len(sst) < n_unique:
            sst.append(cur.string())
        # SST 는 헤더가 문자열 개수를 선언한다 → 파싱 수와 대조하면 CONTINUE 처리 오류를
        # 스스로 잡는다. 안 맞으면 뒷부분 셀이 조용히 빈칸이 되므로 반드시 표면화한다.
        if len(sst) != n_unique:
            LAST_WARN = f"SST 문자열 {len(sst)}/{n_unique} 만 복원 — 일부 셀이 빌 수 있음"

    out = []
    for off, dt, name in sheets:
        if dt != 0 or off >= len(buf):                               # dt 0 = 워크시트
            continue
        out.append((name, _sheet_cells(buf, off, sst, biff8)))
    return out


def _sheet_cells(buf: bytes, off: int, sst: list[str], biff8: bool) -> list[list[str]]:
    cells: dict[tuple[int, int], str] = {}
    pending: tuple[int, int] | None = None                           # FORMULA → STRING 대기
    for _, rt, d in _records(buf, off):
        if rt == 0x000A:                                             # EOF
            break
        try:
            if rt == 0x00FD and len(d) >= 10:                        # LABELSST
                r, c, _, idx = struct.unpack_from("<HHHI", d, 0)
                cells[(r, c)] = sst[idx] if idx < len(sst) else ""
            elif rt in (0x0204, 0x00D6) and len(d) >= 8:             # LABEL / RSTRING
                r, c = struct.unpack_from("<HH", d, 0)
                cch = struct.unpack_from("<H", d, 6)[0]
                if biff8:
                    wide = d[8] & 1
                    body = d[9:]
                    cells[(r, c)] = (body[:cch * 2].decode("utf-16-le", "ignore") if wide
                                     else _legacy(body[:cch]))
                else:
                    cells[(r, c)] = _legacy(d[8:8 + cch])
            elif rt == 0x0203 and len(d) >= 14:                      # NUMBER
                r, c = struct.unpack_from("<HH", d, 0)
                cells[(r, c)] = _num(struct.unpack_from("<d", d, 6)[0])
            elif rt == 0x027E and len(d) >= 10:                      # RK
                r, c = struct.unpack_from("<HH", d, 0)
                cells[(r, c)] = _num(_rk(struct.unpack_from("<I", d, 6)[0]))
            elif rt == 0x00BD and len(d) >= 6:                       # MULRK
                r, c0 = struct.unpack_from("<HH", d, 0)
                for k in range((len(d) - 6) // 6):
                    v = struct.unpack_from("<I", d, 4 + k * 6 + 2)[0]
                    cells[(r, c0 + k)] = _num(_rk(v))
            elif rt == 0x0205 and len(d) >= 8:                       # BOOLERR
                r, c = struct.unpack_from("<HH", d, 0)
                cells[(r, c)] = ("TRUE" if d[6] else "FALSE") if d[7] == 0 else "#ERR"
            elif rt == 0x0006 and len(d) >= 14:                      # FORMULA
                r, c = struct.unpack_from("<HH", d, 0)
                if d[12:14] == b"\xff\xff":                          # 결과가 문자열·불리언·오류
                    if d[6] == 0:
                        pending = (r, c)
                    elif d[6] == 1:
                        cells[(r, c)] = "TRUE" if d[8] else "FALSE"
                    elif d[6] == 2:
                        cells[(r, c)] = "#ERR"
                else:
                    cells[(r, c)] = _num(struct.unpack_from("<d", d, 6)[0])
            elif rt == 0x0207 and pending:                           # STRING (수식 결과)
                cch = struct.unpack_from("<H", d, 0)[0]
                if biff8:
                    body = d[3:]
                    cells[pending] = (body[:cch * 2].decode("utf-16-le", "ignore")
                                      if d[2] & 1 else _legacy(body[:cch]))
                else:
                    cells[pending] = _legacy(d[2:2 + cch])
                pending = None
        except (struct.error, IndexError):
            continue                                                 # 손상 레코드 1개는 건너뛴다

    if not cells:
        return []
    rows, truncated = [], False
    last = max(r for r, _ in cells)
    if last >= MAX_ROWS:
        last, truncated = MAX_ROWS - 1, True
    for r in range(last + 1):
        cs = {c: v for (rr, c), v in cells.items() if rr == r and v.strip()}
        rows.append([cs.get(i, "") for i in range(max(cs) + 1)] if cs else [])
    while rows and not any(rows[-1]):
        rows.pop()
    if truncated:
        rows.append([f"…({MAX_ROWS}행 초과분 생략 — 원본을 열 것)"])
    return rows


_CTRL = {c: None for c in list(range(0x20)) + [0x7F, 0xFEFF] if c not in (0x09, 0x0A, 0x0D)}


def _clean(s: str) -> str:
    """제어문자·BOM 제거 — 안전망이다. 파서가 어긋나 제어문자가 새면 refined.md 가 grep 에
    **바이너리로 판정**돼(NUL 하나면 충분) vault 전역 검색에서 조용히 사라진다. 파서를 고치는 게
    1차지만, 검색 가능성은 파서 버그에 걸지 않는다(U+FEFF 제거 선례와 같은 이유)."""
    return s.translate(_CTRL)


def _md_table(rows: list[list[str]]) -> str:
    rows = [r for r in rows if any(r)]
    if not rows:
        return "_(빈 시트)_\n"
    width = max(len(r) for r in rows)

    def line(r):
        cells = [_clean(r[i] if i < len(r) else "").replace("|", "\\|").replace("\n", " ")
                 for i in range(width)]
        return "| " + " | ".join(cells) + " |"

    return "\n".join([line(rows[0]), "|" + "---|" * width]
                     + [line(r) for r in rows[1:]]) + "\n"


# ── HTML 위장 .xls ──────────────────────────────────────────────────────────
class _TableParser(HTMLParser):
    """관공서·웹시스템이 HTML `<table>` 을 그대로 `.xls` 로 내보내는 관행을 받는다.
    OLE 도 zip 도 아니라 soffice·docling 모두 "열 수 없음"으로 떨어지는 부류."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._tbl = self._row = None
        self._cell: list[str] | None = None
        self._span = 1

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self._tbl = []
        elif tag == "tr" and self._tbl is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            try:
                self._span = max(1, min(int(a.get("colspan", 1)), 50))
            except ValueError:
                self._span = 1
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._row += [""] * (self._span - 1)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self._tbl.append(self._row)
            self._row = None
        elif tag == "table" and self._tbl is not None:
            if self._tbl:
                self.tables.append(self._tbl)
            self._tbl = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data.replace("\xa0", " "))


def parse_html(raw: bytes) -> list[tuple[str, list[list[str]]]]:
    text = None
    for enc in ("utf-8", "cp949", "utf-16", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    p = _TableParser()
    p.feed(text or raw.decode("cp949", "replace"))
    p.close()
    if not p.tables:
        raise ValueError("HTML 이지만 <table> 이 없음")
    out = []
    for i, rows in enumerate(p.tables, 1):
        rows = rows[:MAX_ROWS]
        while rows and not any(c.strip() for c in rows[-1]):
            rows.pop()
        out.append((f"표{i}" if len(p.tables) > 1 else "Sheet1", rows))
    return out


def refine(path: pathlib.Path) -> tuple[bool, str]:
    out_dir = path.parent / (path.name + "_parse")
    out = out_dir / "refined.md"
    engine = "xls-stdlib"
    try:
        raw = path.read_bytes()
        if raw[:8] == OLE_MAGIC:
            streams = cfb_streams(raw)
            book = next((streams[n] for n in ("Workbook", "Book") if n in streams), None)
            if book is None:
                raise ValueError(f"Workbook 스트림 없음 (보유: {', '.join(sorted(streams)) or '없음'})")
            sheets = parse_workbook(book)
        elif raw[:2] == b"PK":
            raise ValueError("실제로는 xlsx(zip) — xlsx_refine.py 로 처리할 것")
        else:
            sheets, engine = parse_html(raw), "xls-html-stdlib"
        if not sheets:
            raise ValueError("워크시트 없음")
        body = []
        for title, rows in sheets:
            body += [f"## {_clean(title)}\n", _md_table(rows), ""]
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

    out_dir.mkdir(parents=True, exist_ok=True)
    fm = [
        "---",
        f"source_pdf: {path}",
        f"base_engine: {engine}",
        "corrections: []",
        f"generated: {datetime.date.today().isoformat()}",
        f"host: {socket.gethostname()}",
        f"refine_confidence: {'low' if LAST_WARN else 'ok'}",
        *( [f"warning: {LAST_WARN}"] if LAST_WARN else [] ),
        ("note: BIFF 직독 — CFB+레코드 경량 추출(서식·수식문자열 제외, 값만)"
         if engine == "xls-stdlib" else
         "note: HTML 위장 xls — <table> 직독(확장자만 xls, 실제는 HTML)"),
        "---",
        "",
    ]
    out.write_text("\n".join(fm) + "\n".join(body).rstrip("\n") + "\n", encoding="utf-8")
    return True, str(out)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    ok = fail = 0
    for a in argv:
        p = pathlib.Path(a)
        good, msg = refine(p)
        if good:
            ok += 1
            print(f"  ok(xls-stdlib): {p.name} → {msg}")
        else:
            fail += 1
            print(f"  ✗ {p.name}: {msg}", file=sys.stderr)
    print(f"[xls_refine] 성공 {ok} / 실패 {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
