#!/usr/bin/env python3
"""gmail-label-router — 결정형 Gmail 라벨 라우터 (예제·템플릿).

라벨이 붙은 메일을 *판단 없이* 정해진 동작으로 처리하는 결정론적 스크립트.
LLM 추론을 핫패스에서 제거 → 빠르고 watchdog 종료·고아(미아) 위험이 없다.
(배경: docs/openclaw-skills.md "실습 — 라벨 자동화" 의 *결정형 래퍼* 버전)

현재 라우트 (1개, 라벨 고정):
  "1 첨부저장"  →  첨부파일을 저장 디렉토리에 다운로드
                →  라벨을 "4 완료" 로 교체 (저장 성공 시에만)

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

라벨("1 첨부저장"·"4 완료")은 이 스킬의 고정 규칙입니다 (사용자 수정 대상 아님).
Gmail 에 이 두 라벨을 그대로 만들어 사용하세요.
"""
from __future__ import annotations
import json
import os
import pathlib
import shutil
import subprocess
import sys

# ── 설정 ────────────────────────────────────────────────────────────────
ACCOUNT = os.environ.get("GMAIL_ROUTER_ACCOUNT", "").strip()  # 필수 — 본인 계정 (기본값 없음: 누출 방지)
INBOX = pathlib.Path(os.path.expanduser(
    os.environ.get("GMAIL_ROUTER_INBOX", "~/.openclaw/workspace/attachments")))
SRC_LABEL = "1 첨부저장"   # 고정 규칙 — 사용자 수정 대상 아님 (Gmail 에 이 라벨 생성)
DONE_LABEL = "4 완료"      # 고정 규칙 — 사용자 수정 대상 아님 (Gmail 에 이 라벨 생성)
MAX = 50
STAGING = pathlib.Path("/tmp/gmail-label-router")

# ── gog 래퍼 ───────────────────────────────────────────────────────────────
def gog_json(*args: str, timeout: int = 30):
    """`gog ... --account ACCOUNT -j --results-only`. JSON 파싱, [] 빈출력, None 실패."""
    cmd = ["gog", *args, "--account", ACCOUNT, "-j", "--results-only"]
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


# ── 헬퍼 ──────────────────────────────────────────────────────────────────
def search_threads(label: str):
    """라벨로 검색 → (고유 thread_id 목록, 디버그용 첫 항목). 실패 시 (None, None)."""
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
    """이름 충돌 시 _1, _2 … 로 회피 (덮어쓰지 않음)."""
    if not dst.exists():
        return dst
    i = 1
    while True:
        cand = dst.with_name(f"{dst.stem}_{i}{dst.suffix}")
        if not cand.exists():
            return cand
        i += 1


def process_thread(tid: str) -> tuple[bool, str, list[str]]:
    """thread 의 첨부를 INBOX 에 저장. (ok, msg, 저장된파일명목록)."""
    out_dir = STAGING / tid
    out_dir.mkdir(parents=True, exist_ok=True)
    result = gog_json("gmail", "thread", "get", tid, "--full",
                      "--download", "--out-dir", str(out_dir), timeout=60)
    if result is None:
        return (False, "thread get 실패", [])
    atts = extract_attachments(result, out_dir)
    if not atts:
        return (False, "첨부 없음", [])
    INBOX.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for src, name in atts:
        if not src.exists():
            continue
        dst = unique_dest(INBOX / name)
        shutil.copy2(src, dst)
        saved.append(dst.name)
    if not saved:
        return (False, "첨부 경로 미존재", [])
    return (True, "ok", saved)


# ── main ──────────────────────────────────────────────────────────────────
def main() -> None:
    if not ACCOUNT:
        print("✋ 환경변수 GMAIL_ROUTER_ACCOUNT 가 비어 있습니다.\n"
              "   예: GMAIL_ROUTER_ACCOUNT=you@gmail.com python3 run.py")
        sys.exit(2)

    dry = "--dry-run" in sys.argv
    print(f"▶ gmail-label-router  계정={ACCOUNT}")
    print(f"  라우트: '{SRC_LABEL}' → 첨부 저장 → '{DONE_LABEL}'")
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
        # 라벨 교체는 저장 성공 후에만 (fail-safe). --remove 는 콤마단일플래그.
        rok, rerr = gog_call("gmail", "labels", "modify", tid,
                             "--add", DONE_LABEL, "--remove", SRC_LABEL)
        if not rok:
            n_skip += 1
            print(f"  ⚠️ [{tid}] 첨부 {len(saved)}건 저장됐으나 라벨변경 실패: {rerr}")
            continue
        n_ok += 1
        print(f"  ✅ [{tid}] 첨부 {len(saved)}건 저장 → '{DONE_LABEL}'  ({', '.join(saved)})")

    print(f"🎉 완료: 처리 {n_ok} / 건너뜀 {n_skip} / 총 {len(tids)}")


if __name__ == "__main__":
    main()
