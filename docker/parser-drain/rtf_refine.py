#!/usr/bin/env python3
"""rtf_refine — .rtf 를 호스트 pandoc 으로 markdown 풀텍스트(refined.md)로 추출한다.

    python3 rtf_refine.py <파일.rtf> [...]

`xls_refine.py`·`hwp_refine.py` 의 짝. 산출물 규약(`<원본>_parse/refined.md` + frontmatter)은
동일하고 읽는 방식만 다르다 — pandoc 이 RTF 를 네이티브로 읽는다.

**왜 만들었나 (2026-09-28).** brainify `PARSEABLE` 은 `.rtf` 를 파싱 대상으로 인정하는데
parser-drain `candidates()` 에는 `.rtf` 가 없었다 — 두 단계의 잣대 불일치. 그래서 rtf 첨부가
있는 노트는 `_parse` 가 영영 생기지 않아 `parse_confidence: low` 로 남고, `renote-scan` 은
`no_source`(붙은 _parse 0)로 분류해 매 무인 드레인 보고에 "파싱오류 stub" 경고로 떴다
(실측: IAEA RAS6097 참가자 명단 rtf 4개 중 2노트). docling 은 RTF 를 입력으로 받지 않는다.

**왜 pandoc 인가.** 호스트에 이미 있고(hwp→docx→pandoc 경로가 쓰는 것과 같은 바이너리),
soffice 를 띄우지 않아 프로필 초기화 문제가 없으며, 컨테이너·GPU 가 필요 없다.

한계:
  · 서식·그림은 버린다. 표는 셀에 문단이 여럿이면 HTML `<table>` 로 남는다(grep 가능, 육안 판독 가능).
  · 암호화·손상 RTF 는 pandoc 이 실패하면 그대로 실패로 보고한다.
"""
from __future__ import annotations

import datetime
import pathlib
import re
import shutil
import socket
import subprocess
import sys

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f﻿]")


def refine(path: pathlib.Path) -> tuple[bool, str]:
    out_dir = path.parent / (path.name + "_parse")
    out = out_dir / "refined.md"
    if shutil.which("pandoc") is None:
        return False, "pandoc 미설치"
    try:
        r = subprocess.run(
            ["pandoc", "-f", "rtf", "-t", "gfm", "--wrap=none", str(path)],
            capture_output=True, text=True, timeout=120,
        )
    except Exception as e:  # noqa: BLE001 — 타임아웃 등 전부 실패로 보고
        return False, f"{type(e).__name__}: {e}"
    if r.returncode != 0:
        return False, f"pandoc rc={r.returncode}: {r.stderr.strip()[:200]}"
    text = _CTRL.sub("", r.stdout).strip()
    if len(text) < 20:
        return False, "pandoc 출력이 사실상 비어 있음"

    out_dir.mkdir(parents=True, exist_ok=True)
    fm = [
        "---",
        f"source_pdf: {path}",
        "base_engine: rtf-pandoc",
        "corrections: []",
        f"generated: {datetime.date.today().isoformat()}",
        f"host: {socket.gethostname()}",
        "refine_confidence: ok",
        "note: pandoc -f rtf 직독 — 서식·그림 제외, 텍스트·표만",
        "---",
        "",
    ]
    out.write_text("\n".join(fm) + text + "\n", encoding="utf-8")
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
            print(f"  ok(rtf-pandoc): {p.name} → {msg}")
        else:
            fail += 1
            print(f"  ✗ {p.name}: {msg}", file=sys.stderr)
    print(f"[rtf_refine] 성공 {ok} / 실패 {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
