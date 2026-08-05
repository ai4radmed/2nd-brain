#!/usr/bin/env python3
"""
2nd-brain 아침 헬스 보고 — health-check.py 의 요약(JSON)을 텔레그램으로 보낸다.

    python3 health-report.py <summary.json>

환경변수:
    HEALTH_REPORT        = all(기본) | fail | off   보고 on/off. 정상이어도 매일 한 통이 기본.
    HEALTH_REPORT_STYLE  = plain(기본) | both | tech  항목 표기 방식.
    HEALTH_TG_TOKEN / HEALTH_TG_CHAT                 발송 자격. 없으면 문안만 출력하고 끝.
                                                     토큰 미지정 시 openclaw.json 에서 재사용.

문안 설계는 radsafety-pwa `scripts/health-report.mjs` 와 같은 규약을 따른다:
  · 번호식 — 큰분류 `1.` `2.`, 세부 `1-1.` `1-2.` … 세부번호는 큰분류를 가로질러 이어서 증가.
    그래서 **마지막 항목 번호 = 전체 항목 수**이고 머리줄의 (N/N) 과 같은 축을 쓴다.
    두 숫자가 어긋나면 그 자체가 버그 신호다.
  · 무이모지 — 상태는 줄 **맨 끝**에 [o]/[!]/[x] 로. 눈이 한 열만 훑으면 된다.
  · 쉬운 말 — 기술 라벨은 점검 스크립트(콘솔용)에 그대로 두고, 번역은 이 보고 계층에서만 한다.
    사전에 없는 라벨은 원문 그대로 나간다 — 번역이 없다고 항목이 조용히 사라지면 안 된다.
  · 명사형 — "…열림" 이지 "…열렸습니다" 가 아니다. 판정은 줄 끝 표식이 지므로,
    문장과 표식이 서로 반대말이 되는 사고를 막는다.

이 스크립트의 exit code 는 **보고 발송 성패만** 나타낸다. 시스템의 건강 상태는
health-check.py 의 exit code 가 이미 표현하므로 여기서 중복해 실패시키지 않는다.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

MARK = {"ok": "[o]", "warn": "[!]", "fail": "[x]"}
STYLES = {"plain", "both", "tech"}
MAX_LISTED = 12
KST = timezone(timedelta(hours=9))

# 점검 영역(health-check.py 의 section key) → 초중급 눈높이 제목.
# key 는 health-check.py 와의 계약 — 거기서 바뀌면 여기도 함께.
GROUP_TITLES = {
    "gateway": "텔레그램 게이트웨이",
    "auth": "로그인 자격(클로드·구글)",
    "cron": "자동 실행 일정",
    "wiring": "메일 자료 받는 통로",
    "hostauto": "PC 안 자동 작업",
    "data": "저장 공간·자료 상태",
    "sync": "기기 간 동기화",
}

# 기술 라벨 → 쉬운 말. 값이 매번 달라지는 부분은 접두 일치로 잡는다.
PLAIN_EXACT = {
    "컨테이너 healthcheck": "게이트웨이 자체 진단",
    "이미지 버전 핀 일치": "게이트웨이 버전이 지정한 값 그대로",
    "클론·이미지 dual-pin 일치": "설정 사본과 실행 버전 짝 맞음",
    "컨테이너 Claude 자격 파일 존재": "클로드 로그인 정보 파일",
    "refresh token 보유": "자동 재로그인 열쇠 보유",
    "refresh token 유효기간": "자동 재로그인 열쇠 남은 기간",
    "access token 신선도": "지금 쓰는 출입증 신선도",
    "Claude 라이브 호출 (실제 1턴)": "클로드에 실제로 말 걸어보기",
    "gog keyring 비밀번호 주입": "구글 열쇠고리 비밀번호 설정",
    "GMAIL_ROUTER_INBOX=/inbox": "받은 첨부의 도착지 설정",
    "vault 읽기전용 마운트": "볼트 읽기 연결",
    "extra.yml env 블록 생존": "직접 손댄 설정이 지워지지 않음",
    "cron 스케줄 진행중 (stuck 아님)": "예약 실행이 멈춰 있지 않음",
    "인박스 적체": "처리 대기 중인 자료",
    "vault 최근 변경": "볼트가 최근에 갱신됨",
    "디스크 여유": "디스크 남은 공간",
    "SyncThing 구동": "동기화 프로그램 실행중",
    "인박스 rw 마운트 (/inbox → vault)": "받은 첨부가 볼트로 직행",
}

# 접두 치환 — 뒤에 잡 이름·유닛명 같은 고유명사가 붙는 라벨용.
# 구분자로 '—' 를 쓰지 않는다: 항목 줄의 '—' 는 이미 "사유" 구분자라 두 개가 겹치면 읽기 나쁘다.
PLAIN_PREFIX = [
    ("컨테이너 실행중", "게이트웨이 실행중"),
    ("컨테이너 존재", "게이트웨이 컨테이너 존재"),
    ("gog 계정 인증", "구글 계정 로그인"),
    ("cron: ", "예약 실행: "),
    ("유닛 활성: ", "자동 작업 켜짐: "),
    ("마지막 실행 결과: ", "지난 실행 결과: "),
]


def plain_label(label: str) -> str | None:
    """기술 라벨 → 쉬운 말. 사전·규칙에 없으면 None(원문을 쓰라는 뜻)."""
    if label in PLAIN_EXACT:
        return PLAIN_EXACT[label]
    for pre, rep in PLAIN_PREFIX:
        if label.startswith(pre):
            return rep + label[len(pre):]
    return None


def item_line(it: dict, style: str) -> list[str]:
    """세부 항목 줄. 정상은 이름만(수치는 소음), 경고·문제는 사유까지."""
    mark = MARK.get(it["status"], MARK["fail"])
    tail = f" — {it['detail']}" if it["status"] != "ok" and it.get("detail") else ""
    plain = plain_label(it["label"])
    if style == "tech" or not plain:
        return [f"{it['no']}. {it['label']}{tail} {mark}"]
    if style == "both":
        return [f"{it['no']}. {it['label']}{tail} {mark}", f"      {plain}"]
    return [f"{it['no']}. {plain}{tail} {mark}"]


def build_groups(summary: dict) -> tuple[list, int, int, list]:
    groups = []
    for s in summary.get("sections", []):
        items = s.get("items") or []
        if not items:
            continue
        groups.append({"title": GROUP_TITLES.get(s["key"], s.get("name", s["key"])), "items": items})

    n = ok = 0
    problems = []
    for gi, g in enumerate(groups, 1):
        g["no"] = gi
        for it in g["items"]:
            n += 1
            it["no"] = f"{gi}-{n}"
            if it["status"] == "ok":
                ok += 1
            else:
                problems.append(it)
    return groups, n, ok, problems


def headline(host: str, total: int, ok: int, fail_n: int, warn_n: int) -> str:
    """전부 정상일 때만 '모든 점검항목 정상' — 경고 1건도 그 말을 쓰지 않는다."""
    if not fail_n and not warn_n:
        return f"2nd-brain({host}) 모든 점검항목 정상 ({total}/{total})"
    parts = []
    if fail_n:
        parts.append(f"문제 {fail_n}건")
    if warn_n:
        parts.append(f"경고 {warn_n}건")
    return f"2nd-brain({host}) 점검항목 {' · '.join(parts)} ({ok}/{total} 정상)"


def format_kst(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
    except Exception:
        return ""


def format_report(summary: dict | None, style: str = "plain") -> str:
    lines: list[str] = []

    # 요약이 없다 = 점검이 결과를 남기기도 전에 죽었다. 정상으로 오인하면 안 된다.
    if not summary:
        return "\n".join([
            "2nd-brain 점검 실행 자체 실패 [x]",
            "헬스체크 스크립트가 결과를 남기지 못했습니다(크래시·타임아웃).",
        ])

    style = style if style in STYLES else "plain"
    groups, total, ok, problems = build_groups(summary)
    fail_n = sum(1 for p in problems if p["status"] == "fail")
    warn_n = len(problems) - fail_n

    lines.append(headline(summary.get("host", "?"), total, ok, fail_n, warn_n))
    lines.append(format_kst(summary.get("checkedAt", "")))

    for g in groups:
        lines.append("")
        lines.append(f"{g['no']}. {g['title']}")
        for it in g["items"]:
            lines.extend(item_line(it, style))

    # 문제가 있으면 번호만 한 줄로 되짚는다 — 긴 목록에서 눈으로 [x] 를 찾지 않게.
    if problems:
        def ref(kind):
            sel = [p for p in problems if (p["status"] == "fail") == (kind == "fail")]
            return ", ".join(p["no"] for p in sel[:MAX_LISTED])
        parts = []
        if fail_n:
            parts.append(f"문제 {ref('fail')}")
        if warn_n:
            parts.append(f"경고 {ref('warn')}")
        lines.append("")
        lines.append(" · ".join(parts))

    return "\n".join(lines)


def should_send(summary: dict | None, mode: str | None) -> bool:
    m = (mode or "all").lower()
    if m == "off":
        return False
    if m == "fail":
        return not summary or not summary.get("ok")   # 요약 누락도 이상으로 취급
    return True  # all(기본) — 정상이어도 매일 한 통(하트비트)


def telegram_token() -> str:
    tok = os.environ.get("HEALTH_TG_TOKEN", "")
    if tok:
        return tok
    # 호스트 로컬 openclaw.json 재사용(미동기 secret). 게이트웨이가 죽어 있어도 파일은 읽힌다.
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
            # 발송 실패를 조용히 넘기면 "조용하니 정상"이라는 최악의 착각이 생긴다.
            raise RuntimeError(f"텔레그램 발송 실패: HTTP {r.status}")


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        summary = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        summary = None  # → format_report 가 "점검 실행 자체 실패"로 보고

    if not should_send(summary, os.environ.get("HEALTH_REPORT")):
        print(f"보고 생략 (HEALTH_REPORT={os.environ.get('HEALTH_REPORT')})")
        return 0

    text = format_report(summary, (os.environ.get("HEALTH_REPORT_STYLE") or "").lower())
    print(text)

    token, chat = telegram_token(), os.environ.get("HEALTH_TG_CHAT", "8669227844")
    if not token or not chat:
        print("\n텔레그램 자격 미설정 — 발송 생략(문안만 출력).")
        return 0

    send_telegram(text, token, chat)
    print("\n텔레그램 발송 완료.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"보고 실패: {e}", file=sys.stderr)
        sys.exit(1)
