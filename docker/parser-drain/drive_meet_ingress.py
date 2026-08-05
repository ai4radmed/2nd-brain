#!/usr/bin/env python3
"""Google Meet 녹화 ingress — Drive `Meet Recordings` → vault inbox.

배경: 회의 녹화(Google Meet, AI Pro 프리미엄)는 주최자 Drive 의 `Meet Recordings`
  폴더에 자동 저장된다. 폰 음성녹음이 SyncThing ingress 를 타는 것과 같은 자리에
  Drive 를 붙여, 이후 전사·편입은 기존 오디오 레인(audio_refine.py)이 그대로 처리.
  → 이 스크립트의 경계 = "Drive 에서 inbox 까지". 전사·PARA 편입은 하지 않는다.

멱등: fileId ledger(`~/.local/state/drive-meet.ledger`). brainify 가 inbox 밖으로
  옮겨도 재다운로드하지 않는다(폰 ingress ledger 와 동일 규약, 키만 이름:크기 →
  fileId 로 강화 — Drive 는 안정 ID 가 있으므로).

파일명: Meet 기본명은 `cbq-cjqb-gda (2026-08-10 15:03 GMT+9).mp4` 처럼 **회의 코드**라
  무슨 회의인지 안 보인다. vault 의 허브노트 frontmatter `meet_link:` 를 역인덱스로
  써서 `YYYY-MM-DD_<회의체>_녹화.mp4` 로 정규화한다(CLAUDE.md 파일명 규칙).
  매핑 실패 시 코드를 그대로 출처 자리에 쓴다 — 실패해도 유입은 막지 않는다.

전제: 호스트 `gog` CLI + 인증된 계정. gog 부재·계정 미설정 머신은 skip(device-adaptive,
  머신-specific 하드코딩 없음 — 오디오 레인의 venv 어댑터와 동일 패턴).

사용: drive_meet_ingress.py [--dry-run]
환경변수: DRIVE_ACCOUNT(필수 — 미설정 시 skip) · DRIVE_MEET_FOLDER(기본 'Meet Recordings')
  · DRIVE_LEDGER · SB_DATA(vault 루트)
반환코드: 0 성공/skip, 1 일부 실패.
"""
import json
import os
import re
import shutil
import subprocess
import sys

VAULT = os.environ.get("SB_DATA", os.path.expanduser("~/projects/2nd-brain-vault"))
INBOX = os.path.join(VAULT, "sources", "00_inbox")
ACCOUNT = os.environ.get("DRIVE_ACCOUNT", "")
FOLDER = os.environ.get("DRIVE_MEET_FOLDER", "Meet Recordings")
LEDGER = os.environ.get("DRIVE_LEDGER",
                        os.path.expanduser("~/.local/state/drive-meet.ledger"))

# Meet 기본 파일명에서 회의 코드와 날짜를 뽑는다: "abc-defg-hij (2026-08-10 15:03 GMT+9)"
NAME_RE = re.compile(r"([a-z]{3}-[a-z]{4}-[a-z]{3}).*?(\d{4}-\d{2}-\d{2})")


def gog(*args):
    """gog 호출 → JSON. 실패 시 None (호출부가 skip 판단)."""
    try:
        r = subprocess.run(["gog", *args, "--account", ACCOUNT, "-j"],
                           capture_output=True, text=True, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def rows(payload):
    """gog JSON 은 명령마다 모양이 다르다 — 리스트가 나올 자리를 실측 순으로 훑는다."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    for key in ("files", "items", "results", "result", "data"):
        v = payload.get(key)
        if isinstance(v, list):
            return v
    return []


def meet_link_index():
    """vault frontmatter `meet_link:` → {회의코드: 회의체명}. 없으면 빈 dict."""
    idx = {}
    kb = os.path.join(VAULT, "knowledge")
    for root, dirs, files in os.walk(kb):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in files:
            if not fn.endswith(".md"):
                continue
            path = os.path.join(root, fn)
            try:
                with open(path, encoding="utf-8") as fh:
                    head = fh.read(2048)
            except OSError:
                continue
            m = re.search(r"^meet_link:\s*\S*?/([a-z]{3}-[a-z]{4}-[a-z]{3})",
                          head, re.MULTILINE)
            if m:
                idx[m.group(1)] = os.path.splitext(fn)[0]
    return idx


def target_name(drive_name, idx):
    """Meet 기본명 → `YYYY-MM-DD_<회의체>_녹화.ext` (실패 시 원본명 정규화)."""
    ext = os.path.splitext(drive_name)[1] or ".mp4"
    m = NAME_RE.search(drive_name)
    if not m:
        return drive_name.replace(" ", "_")
    code, date = m.group(1), m.group(2)
    who = idx.get(code, code)
    return f"{date}_{who}_녹화{ext}"


def main(argv):
    dry = "--dry-run" in argv
    if not ACCOUNT:
        print("[drive-meet] DRIVE_ACCOUNT 미설정 → skip")
        return 0
    if shutil.which("gog") is None:
        print("[drive-meet] gog 없음 → skip")
        return 0

    folders = rows(gog("drive", "search",
                       f"name = '{FOLDER}' and "
                       "mimeType = 'application/vnd.google-apps.folder' and "
                       "trashed = false"))
    if not folders:
        print(f"[drive-meet] '{FOLDER}' 폴더 없음 → skip (녹화 이력 없음)")
        return 0
    fid = folders[0].get("id") or folders[0].get("fileId")

    files = rows(gog("drive", "ls", "--query",
                     f"'{fid}' in parents and trashed = false"))
    if not files:
        print("[drive-meet] 신규 녹화 없음")
        return 0

    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    os.makedirs(INBOX, exist_ok=True)
    seen = set()
    if os.path.exists(LEDGER):
        with open(LEDGER, encoding="utf-8") as fh:
            seen = {ln.strip() for ln in fh if ln.strip()}

    idx = meet_link_index()
    got, failed = 0, []
    for f in files:
        fid_ = f.get("id") or f.get("fileId")
        name = f.get("name") or f.get("title") or ""
        if not fid_ or fid_ in seen:
            continue
        dest = os.path.join(INBOX, target_name(name, idx))
        if dry:
            print(f"  [dry-run] {name} → {os.path.basename(dest)}")
            got += 1
            continue
        if os.path.exists(dest):                       # 이미 있으면 ledger 만 갱신
            with open(LEDGER, "a", encoding="utf-8") as fh:
                fh.write(fid_ + "\n")
            continue
        r = subprocess.run(["gog", "drive", "download", fid_,
                            "--out", dest, "--account", ACCOUNT],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(dest):
            failed.append((name, r.stderr.strip()[:120]))
            continue
        with open(LEDGER, "a", encoding="utf-8") as fh:
            fh.write(fid_ + "\n")
        got += 1
        print(f"  ok: {name} → {os.path.basename(dest)}")

    print(f"[drive-meet] 유입 {got} / 실패 {len(failed)}")
    for name, why in failed:
        print(f"     ✗ {name} — {why}", file=sys.stderr)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
