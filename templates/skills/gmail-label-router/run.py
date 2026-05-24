#!/usr/bin/env python3
"""gmail-label-router — 결정형 Gmail 라벨 라우터 (예제·템플릿).

라벨이 붙은 메일을 *판단 없이* 정해진 동작으로 처리하는 결정론적 스크립트.
LLM 추론을 핫패스에서 제거 → 빠르고 watchdog 종료·고아(미아) 위험이 없다.
(배경: docs/openclaw-skills.md "실습 — 라벨 자동화" 의 *결정형 래퍼* 버전)

현재 라우트 (1개, 라벨 고정):
  "1 저장"  →  스레드(대화) 전체를 저장 디렉토리에 캡처
                   (스레드별 폴더: _thread.md 본문 + 첨부파일 원본)
                →  라벨을 "9 완료" 로 교체 (캡처 성공 시에만)

캡처 단위 = 스레드 전체. 본문(text/plain)을 _thread.md 로, 첨부는 원본 그대로.
요약·PARA 분류·링크는 *하지 않는다* — 그건 brainify 단계의 판단 영역이고,
이 스킬은 판단0 결정형 캡처만 담당한다 (첨부 없는 본문-only 메일도 캡처됨).

사용:
  GMAIL_ROUTER_ACCOUNT=you@gmail.com python3 run.py            # 실행 (첨부 저장 + 라벨 교체)
  GMAIL_ROUTER_ACCOUNT=you@gmail.com python3 run.py --dry-run  # 검색만 (gog 응답 구조 검증용)

환경변수:
  GMAIL_ROUTER_ACCOUNT  gog 계정 (필수 — 본인 Gmail 계정)
  GMAIL_ROUTER_INBOX    저장 대상 (기본: ~/.openclaw/workspace/attachments)

전제: gog CLI 설치 + 해당 계정 인증 완료. 자세한 적용·설치법은 같은 폴더 README.md.

⚠️ 적용 전 본인 환경에 맞게 고치세요 (라벨은 제외 — 고정 규칙):
  - GMAIL_ROUTER_ACCOUNT (env) — 반드시 본인 계정 (기본값 없음).
  - GMAIL_ROUTER_INBOX (env)  — 저장 위치.

라벨("1 저장"·"9 완료")은 이 스킬의 고정 규칙입니다 (사용자 수정 대상 아님).
Gmail 에 이 두 라벨을 그대로 만들어 사용하세요.
"""
from __future__ import annotations
import base64
import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

# ── 설정 ────────────────────────────────────────────────────────────────
ACCOUNT = os.environ.get("GMAIL_ROUTER_ACCOUNT", "").strip()  # 필수 — 본인 계정 (기본값 없음: 누출 방지)
INBOX = pathlib.Path(os.path.expanduser(
    os.environ.get("GMAIL_ROUTER_INBOX", "~/.openclaw/workspace/attachments")))
SRC_LABEL = "1 저장"   # 고정 규칙 — 사용자 수정 대상 아님 (Gmail 에 이 라벨 생성)
DONE_LABEL = "9 완료"      # 고정 규칙 — 사용자 수정 대상 아님 (Gmail 에 이 라벨 생성)
MAX = 50
STAGING = pathlib.Path("/tmp/gmail-label-router")

# ── gog 래퍼 ───────────────────────────────────────────────────────────────
def gog_json(*args: str, timeout: int = 30, results_only: bool = True):
    """`gog ... --account ACCOUNT -j [--results-only]`. JSON 파싱, [] 빈출력, None 실패.
    results_only=False: 봉투(envelope) 보존 — `thread get --download` 시 thread+downloaded 둘 다 필요."""
    cmd = ["gog", *args, "--account", ACCOUNT, "-j"]
    if results_only:
        cmd.append("--results-only")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0:
        return None
    out = r.stdout.strip()
    if not out:
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def gog_call(*args: str, timeout: int = 30) -> tuple[bool, str]:
    """변경(mutating) 명령용. (ok, msg). gog 가 exit0 으로 googleapi 에러 흘리는 케이스 방어."""
    cmd = ["gog", *args, "--account", ACCOUNT]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return (False, "timeout")
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    if r.returncode != 0:
        return (False, (err or out).strip())
    combined = f"{out}\n{err}".strip()
    if "googleapi: Error" in combined:
        return (False, combined)
    return (True, out)


# ── 스레드 본문 파싱 (결정형) ───────────────────────────────────────────────
def _b64url(data: str) -> str:
    """Gmail body.data 는 base64url. 패딩 보정 후 디코드."""
    try:
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
    except Exception:
        return ""


def _headers(payload: dict) -> dict:
    """payload.headers 리스트 → {from,to,subject,date} (소문자 키)."""
    h = {x.get("name", "").lower(): x.get("value", "") for x in payload.get("headers", [])}
    return {k: h.get(k, "") for k in ("from", "to", "subject", "date")}


def _find_text(payload: dict) -> str:
    """본문 추출: text/plain 우선, 없으면 text/html(raw). MIME 트리 재귀."""
    def walk(p: dict, want: str):
        if p.get("mimeType") == want and p.get("body", {}).get("data"):
            return _b64url(p["body"]["data"])
        for c in p.get("parts", []) or []:
            r = walk(c, want)
            if r:
                return r
        return None
    return walk(payload, "text/plain") or walk(payload, "text/html") or ""


def build_thread_md(thread: dict, tid: str) -> str:
    """스레드 전 메시지 → 마크다운. 프론트매터(멱등성 키) + 헤더 + 본문(시간순).
    프론트매터의 gmail_thread_id·message_count 가 Router/brainify 멱등성의 단일 근거."""
    msgs = sorted(thread.get("messages", []), key=lambda m: int(m.get("internalDate", "0") or 0))
    last_ts = max((int(m.get("internalDate", "0") or 0) for m in msgs), default=0)
    last_iso = datetime.datetime.fromtimestamp(last_ts / 1000).strftime("%Y-%m-%d %H:%M") if last_ts else ""
    top = _headers(msgs[-1].get("payload", {})) if msgs else {"from": "", "to": "", "subject": "", "date": ""}
    fm = (
        "---\n"
        f"gmail_thread_id: {tid}\n"
        f"message_count: {len(msgs)}\n"
        f"last_internal_date: \"{last_iso}\"\n"
        f"subject: {json.dumps(top['subject'], ensure_ascii=False)}\n"
        f"from: {json.dumps(top['from'], ensure_ascii=False)}\n"
        "---\n\n"
    )
    blocks = []
    for m in msgs:
        pl = m.get("payload", {})
        h = _headers(pl)
        body = (_find_text(pl) or m.get("snippet", "")).strip()
        blocks.append(
            f"### {h['date']}\n"
            f"**From:** {h['from']}  \n**To:** {h['to']}  \n**Subject:** {h['subject']}\n\n"
            f"{body}"
        )
    return fm + "\n\n---\n\n".join(blocks)


def _slug(s: str, maxlen: int = 50) -> str:
    """파일/폴더명용 슬러그 (한글 허용, 공백→-, 위험문자 제거)."""
    s = re.sub(r"\s+", "-", (s or "").strip())
    s = re.sub(r'[\\/:*?"<>|]', "", s)
    s = s.strip("-. ")
    return s[:maxlen] or "no-subject"


def thread_folder_name(thread: dict, tid: str) -> str:
    """스레드 → 결정형 폴더명 'YYYY-MM-DD_발신_제목'. staging 용 — brainify 가 정식 명명."""
    msgs = thread.get("messages", [])
    if not msgs:
        return tid
    last = max(msgs, key=lambda m: int(m.get("internalDate", "0") or 0))
    H = _headers(last.get("payload", {}))
    try:
        ts = int(last.get("internalDate", "0") or 0) / 1000
        date = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        date = "0000-00-00"
    frm = H["from"]
    m = re.search(r"<([^>]+)>", frm)
    sender = (frm.split("<")[0].strip() or (m.group(1) if m else frm)) if frm else "unknown"
    return f"{date}_{_slug(sender, 24)}_{_slug(H['subject'])}"


# ── 헬퍼 ──────────────────────────────────────────────────────────────────
def search_threads(label: str):
    """라벨로 검색 → (고유 thread_id 목록, 디버그용 첫 항목). 실패 시 (None, None).
    멱등성 게이트의 message_count 는 검색이 아니라 thread get 후 len(messages) 로 계산
    (검색 messageCount 는 '라벨 일치 메시지 수'라 스레드 전체 수와 다를 수 있음)."""
    res = gog_json("gmail", "search", f'label:"{label}"', "--max", str(MAX))
    if res is None:
        return None, None
    items = res if isinstance(res, list) else (res.get("messages") or res.get("items") or [])
    tids: list[str] = []
    for m in items:
        if not isinstance(m, dict):
            continue
        tid = m.get("threadId") or m.get("id")
        if tid and tid not in tids:
            tids.append(tid)
    return tids, (items[0] if items else None)


def extract_attachments(result, out_dir: pathlib.Path) -> list[tuple[pathlib.Path, str]]:
    """`thread get --download` 반환 → (실제경로, 저장이름) 목록.
    --download 반환은 *첨부객체 리스트* [{path, filename, mimeType, size, ...}].
    (dict 로 오면 downloaded 안에 동일.) 둘 다 비면 out_dir 스캔(fallback)."""
    objs = []
    if isinstance(result, list):
        objs = result
    elif isinstance(result, dict):
        d = result.get("downloaded")
        if isinstance(d, list):
            objs = d
        elif isinstance(d, dict):
            objs = d.get("files") or []
    out: list[tuple[pathlib.Path, str]] = []
    for a in objs:
        if isinstance(a, dict) and a.get("path"):
            p = pathlib.Path(a["path"])
            out.append((p, a.get("filename") or p.name))
    if not out and out_dir.exists():
        for c in out_dir.iterdir():
            if c.is_file() and not c.name.startswith("."):
                out.append((c, c.name))
    return out


def unique_dest(dst: pathlib.Path) -> pathlib.Path:
    """이름 충돌 시 _1, _2 … 로 회피 (덮어쓰지 않음). 단일 캡처 내 동명 첨부용."""
    if not dst.exists():
        return dst
    i = 1
    while True:
        cand = dst.with_name(f"{dst.stem}_{i}{dst.suffix}")
        if not cand.exists():
            return cand
        i += 1


def _read_front(path: pathlib.Path) -> dict:
    """_thread.md 프론트매터의 단순 `key: value` 파싱 (멱등성 키 읽기용)."""
    out: dict = {}
    try:
        txt = path.read_text(encoding="utf-8")
    except Exception:
        return out
    if not txt.startswith("---"):
        return out
    end = txt.find("\n---", 3)
    if end == -1:
        return out
    for line in txt[3:end].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


def find_existing_capture(tid: str) -> tuple:
    """INBOX 에서 이 threadId 의 기존 캡처 폴더 탐색 (프론트매터 grep).
    멱등성 키는 폴더명이 아니라 _thread.md 의 gmail_thread_id. 반환 (폴더|None, message_count|None)."""
    if not INBOX.exists():
        return (None, None)
    for d in sorted(INBOX.iterdir()):
        if not d.is_dir():
            continue
        meta = _read_front(d / "_thread.md")
        if meta.get("gmail_thread_id") == tid:
            mc = meta.get("message_count", "")
            return (d, int(mc) if mc.isdigit() else None)
    return (None, None)


def process_thread(tid: str) -> tuple[bool, str, list[str]]:
    """스레드를 INBOX 의 스레드별 폴더에 캡처: _thread.md(본문) + 첨부 원본.
    멱등성(게이트 = threadId + message_count):
      - 이미 캡처 + 메시지 수 동일 → 파일 재기록 생략 (라벨 정리만; 중복 0)
      - 메시지 수 변동(새 답장/삭제) → 기존 폴더 비우고 덮어쓰기 (폴더명=불변 스탬프)
      - 없음 → 신규 캡처 (날짜-우선 폴더)
    본문은 항상 저장(첨부 없는 본문-only 메일도 캡처). (ok, msg, 항목목록)."""
    staging = STAGING / tid
    staging.mkdir(parents=True, exist_ok=True)
    # --results-only 제거: download 모드는 그게 붙으면 첨부 리스트만 반환 → thread(본문) 유실.
    # envelope 보존 시 {thread:{messages}, downloaded:[...]} 둘 다 받음 (1회 호출).
    result = gog_json("gmail", "thread", "get", tid, "--full",
                      "--download", "--out-dir", str(staging), timeout=60, results_only=False)
    if result is None:
        return (False, "thread get 실패", [])
    thread = result.get("thread", {}) if isinstance(result, dict) else {}
    cur_mc = len(thread.get("messages", []))
    existing, prev_mc = find_existing_capture(tid)

    # 멱등 skip: 이미 캡처 + 메시지 수 동일 → 재기록 안 함 (라벨 정리는 main 이 수행)
    if existing is not None and prev_mc is not None and prev_mc == cur_mc:
        files = [p.name for p in existing.iterdir() if p.is_file()]
        return (True, "멱등 skip (동일)", files)

    # 갱신이면 기존 폴더 비우고 재사용(폴더명 유지), 신규면 날짜-우선 폴더 생성
    if existing is not None:
        for c in existing.iterdir():
            if c.is_file():
                c.unlink()
        dest_dir = existing
    else:
        dest_dir = INBOX / thread_folder_name(thread, tid)
    dest_dir.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    (dest_dir / "_thread.md").write_text(build_thread_md(thread, tid), encoding="utf-8")
    saved.append("_thread.md")
    for src, name in extract_attachments(result, staging):
        if not src.exists():
            continue
        dst = unique_dest(dest_dir / name)
        shutil.copy2(src, dst)
        saved.append(dst.name)
    return (True, "갱신(덮어쓰기)" if existing is not None else "ok", saved)


# ── main ──────────────────────────────────────────────────────────────────
def main() -> None:
    if not ACCOUNT:
        print("✋ 환경변수 GMAIL_ROUTER_ACCOUNT 가 비어 있습니다.\n"
              "   예: GMAIL_ROUTER_ACCOUNT=you@gmail.com python3 run.py")
        sys.exit(2)

    dry = "--dry-run" in sys.argv
    print(f"▶ gmail-label-router  계정={ACCOUNT}")
    print(f"  라우트: '{SRC_LABEL}' → 스레드 캡처(본문+첨부) → '{DONE_LABEL}'")
    print(f"  저장 대상: {INBOX}")

    tids, sample = search_threads(SRC_LABEL)
    if tids is None:
        print("✋ 검색 실패 (gog 인증·네트워크·라벨명 확인). 중단.")
        sys.exit(1)
    print(f"  대상 thread: {len(tids)}건")

    if dry:
        print("  [DRY-RUN] 검색만 — 저장·라벨변경 없음.")
        if isinstance(sample, dict):
            print(f"  raw 첫 항목 키: {list(sample.keys())}")
            print(f"    threadId={sample.get('threadId')!r}  id={sample.get('id')!r}")
        else:
            print(f"  raw 첫 항목: {sample!r}")
        return

    if not tids:
        print("  처리할 메일 없음. 종료.")
        return

    STAGING.mkdir(parents=True, exist_ok=True)
    n_ok = n_skip = 0
    for tid in tids:
        ok, msg, saved = process_thread(tid)
        if not ok:
            n_skip += 1
            print(f"  ↷ [{tid}] skip — {msg} (라벨 유지)")
            continue
        # 라벨 교체 (멱등 skip 포함 — 잔류 라벨 정리). --remove 는 콤마단일플래그.
        rok, rerr = gog_call("gmail", "labels", "modify", tid,
                             "--add", DONE_LABEL, "--remove", SRC_LABEL)
        if not rok:
            n_skip += 1
            print(f"  ⚠️ [{tid}] {msg} — 라벨변경 실패: {rerr}")
            continue
        n_ok += 1
        print(f"  ✅ [{tid}] {msg} → '{DONE_LABEL}'  ({', '.join(saved)})")

    print(f"🎉 완료: 처리 {n_ok} / 건너뜀 {n_skip} / 총 {len(tids)}")


if __name__ == "__main__":
    main()
