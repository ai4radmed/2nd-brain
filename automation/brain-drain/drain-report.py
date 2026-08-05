#!/usr/bin/env python3
"""
brain-drain 활동 보고 — 드레인 1회 결과를 텔레그램으로 보낸다.

    python3 drain-report.py --refine 0 --brainify 1 --fail 0 --budget 0

문안 규약은 `automation/health/health-report.py` 와 **같은 것을 쓴다.** 두 보고가 같은
텔레그램 방에 섞여 도착하므로, 서로 다른 문법(이모지 vs 번호식)을 쓰면 읽는 눈이 매번
모드를 바꿔야 한다. 그래서 아래를 공유한다:

  · 번호식 — 큰분류 `1.` `2.`, 세부 `1-1.` `1-2.` … 세부번호는 큰분류를 가로질러 이어서
    증가한다. 따라서 **마지막 세부번호 = 전체 항목 수**이고 머리줄 (N/N) 과 축이 같다.
  · 무이모지 — 상태는 줄 **맨 끝**에 [o]/[!]/[x]. 눈이 한 열만 훑으면 된다.
  · 명사형 — "…없음" 이지 "…없습니다" 가 아니다. 판정은 줄 끝 표식이 진다.
  · 머리줄 + KST 시각줄 2줄로 시작.

health 보고와 다른 점은 **성격**뿐이다: health 는 매일 아침 상태 점검(하트비트),
이쪽은 처리한 게 있을 때만 나가는 활동 보고다. 발송 여부 판단(activity>0)은 호출자
(brain-drain.sh)가 이미 하므로 여기서 중복하지 않는다.

환경변수:
    BRAIN_DRAIN_TG_TOKEN / BRAIN_DRAIN_TG_CHAT   발송 자격. 토큰 미지정 시 openclaw.json 재사용.
    BRAINIFY_PY                                   brainify 헬퍼 경로(플래그 집계용).
    OPENCLAW_JSON                                 토큰 재사용 원본.

exit code 는 **발송 성패만** 나타낸다. 드레인 자체의 성패는 호출자가 이미 표현한다.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

MARK = {"ok": "[o]", "warn": "[!]", "fail": "[x]"}
KST = timezone(timedelta(hours=9))
MAX_LISTED = 5          # 플래그 파일 나열 상한 — 넘치면 "…외 N건" 으로 **밝히고** 자른다.


def collect_low() -> tuple[int, list[str], int, bool]:
    """플래그 집계. 반환 (파싱오류 건수, 파일명 목록, 원본부재 건수, 집계성공여부).

    parse_confidence:low 만 파싱오류로 센다. 두 가지를 의도적으로 뺀다:
      · para_review:pending 대량 백로그 — 주간 감사 몫. 섞이면 매 틱 같은 숫자가 떠서 배경소음.
      · source_missing:true — 첨부 0 self-forward 등 **파싱할 원본이 아예 없는** 건.
        파서를 고쳐도 해결되지 않아 영구히 붉게 남는다 → 별도로 세어 따로 보고한다(2026-08-05).
    집계 자체가 실패하면 0 이 아니라 **미상**으로 돌려준다(0 으로 뭉개면 정상으로 오인된다).
    """
    helper = os.environ.get("BRAINIFY_PY", str(Path.home() / ".claude/skills/brainify/brainify.py"))
    try:
        out = subprocess.run(["python3", helper, "audit"],
                             capture_output=True, text=True, timeout=120).stdout
        flagged = json.loads(out).get("flagged", [])
        low = [f for f in flagged
               if f.get("parse_confidence") == "low" and not f.get("source_missing")]
        missing = [f for f in flagged if f.get("source_missing")]
        names = [Path(f.get("note", "")).name for f in low]
        return len(low), names, len(missing), True
    except Exception:
        return 0, [], 0, False


def build_items(refine: int, brainify: int, renote: int, fail: int, budget_hit: bool,
                low_n: int, low_names: list[str], missing_n: int, low_ok: bool) -> list[dict]:
    """(그룹번호, 제목, 항목들) 을 평평한 리스트로. 항목 = {group, label, status, extra}."""
    items: list[dict] = [
        {"g": 1, "gt": "처리 결과", "label": f"정제(refine) {refine}건", "status": "ok"},
        {"g": 1, "gt": "처리 결과", "label": f"편입(brainify) {brainify}건", "status": "ok"},
        {"g": 1, "gt": "처리 결과", "label": f"재작성(renote) {renote}건", "status": "ok"},
        {"g": 1, "gt": "처리 결과",
         "label": f"처리 실패 {fail}건", "status": "fail" if fail else "ok"},
        {"g": 1, "gt": "처리 결과",
         "label": "예산상한 도달(다음 틱 재개)" if budget_hit else "예산상한 여유",
         "status": "warn" if budget_hit else "ok"},
    ]

    if not low_ok:
        items.append({"g": 2, "gt": "남은 플래그", "label": "파싱오류 stub 집계 실패 — 건수 미상",
                      "status": "warn"})
    else:
        extra = []
        for n in low_names[:MAX_LISTED]:
            extra.append(f"      · {n}")
        if low_n > MAX_LISTED:
            extra.append(f"      · …외 {low_n - MAX_LISTED}건")
        items.append({"g": 2, "gt": "남은 플래그",
                      "label": f"파싱오류 stub {low_n}건 (parse_confidence:low)",
                      "status": "warn" if low_n else "ok", "extra": extra})

    # 원본 부재는 **고장이 아니다** — 첨부 없이 온 포워드라 파싱할 대상 자체가 없다.
    # 경고로 띄우면 고칠 수 없는 항목이 매일 붉게 남아 [!] 의 신뢰를 깎으므로, 건수만 알린다.
    items.append({"g": 2, "gt": "남은 플래그",
                  "label": f"원본 부재 {missing_n}건 (source_missing — 첨부 0 포워드)",
                  "status": "ok"})
    return items


def format_report(items: list[dict], now: datetime) -> str:
    host = socket.gethostname()
    total = len(items)
    for i, it in enumerate(items, 1):
        it["no"] = f"{it['g']}-{i}"
    problems = [it for it in items if it["status"] != "ok"]
    fail_n = sum(1 for p in problems if p["status"] == "fail")
    warn_n = len(problems) - fail_n
    ok = total - len(problems)

    if not problems:
        head = f"2nd-brain({host}) 드레인 모든 항목 정상 ({total}/{total})"
    else:
        parts = []
        if fail_n:
            parts.append(f"문제 {fail_n}건")
        if warn_n:
            parts.append(f"경고 {warn_n}건")
        head = f"2nd-brain({host}) 드레인 {' · '.join(parts)} ({ok}/{total} 정상)"

    lines = [head, now.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")]

    last_g = None
    for it in items:
        if it["g"] != last_g:
            lines.append("")
            lines.append(f"{it['g']}. {it['gt']}")
            last_g = it["g"]
        lines.append(f"{it['no']}. {it['label']} {MARK[it['status']]}")
        lines.extend(it.get("extra", []))

    # 문제가 있으면 번호만 한 줄로 되짚는다 — 긴 목록에서 눈으로 [x] 를 찾지 않게.
    if problems:
        parts = []
        if fail_n:
            parts.append("문제 " + ", ".join(p["no"] for p in problems if p["status"] == "fail"))
        if warn_n:
            parts.append("경고 " + ", ".join(p["no"] for p in problems if p["status"] == "warn"))
        lines.append("")
        lines.append(" · ".join(parts))

    return "\n".join(lines)


def telegram_token() -> str:
    tok = os.environ.get("BRAIN_DRAIN_TG_TOKEN", "")
    if tok:
        return tok
    p = Path(os.environ.get("OPENCLAW_JSON", Path.home() / ".openclaw/openclaw.json"))
    try:
        return json.loads(p.read_text(encoding="utf-8"))["channels"]["telegram"]["botToken"]
    except Exception:
        return ""


def send_telegram(text: str, token: str, chat: str) -> None:
    data = urllib.parse.urlencode({
        "chat_id": chat, "text": text, "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=20) as r:
        if r.status != 200:
            raise RuntimeError(f"텔레그램 발송 실패: HTTP {r.status}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refine", type=int, default=0)
    ap.add_argument("--brainify", type=int, default=0)
    ap.add_argument("--renote", type=int, default=0)
    ap.add_argument("--fail", type=int, default=0)
    ap.add_argument("--budget", type=int, default=0, help="1=예산상한 도달")
    ap.add_argument("--no-send", action="store_true", help="문안만 출력(발송 안 함)")
    a = ap.parse_args()

    low_n, low_names, missing_n, low_ok = collect_low()
    items = build_items(a.refine, a.brainify, a.renote, a.fail, bool(a.budget),
                        low_n, low_names, missing_n, low_ok)
    text = format_report(items, datetime.now(timezone.utc))
    print(text)

    if a.no_send:
        return 0
    token, chat = telegram_token(), os.environ.get("BRAIN_DRAIN_TG_CHAT", "8669227844")
    if not token or not chat:
        print("\n텔레그램 자격 미설정 — 발송 생략(문안만 출력).", file=sys.stderr)
        return 0
    send_telegram(text, token, chat)
    print("\n텔레그램 발송 완료.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"보고 실패: {e}", file=sys.stderr)
        sys.exit(1)
