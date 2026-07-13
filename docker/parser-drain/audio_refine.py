#!/usr/bin/env python3
"""호스트-측 오디오 전사기(faster-whisper) — `<원본>_parse/refined.md` 직접 생산.

배경: 폰(갤럭시 S25 FE) 음성녹음 → SyncThing ingress → inbox 로 흘러든 오디오를
  로컬 GPU 로 전사한다. 클라우드 STT 배제(이미지 OCR 과 동일 원칙 — 진료·회의
  녹음은 민감 정보). 오디오는 단일소스(docling/mineru N/A·diff 불가)라 HWP 선례대로
  추출=refine 을 한 번에 하고 refined.md 를 곧장 쓴다. brainify `_refined()` 소비.

전제: ~/.venvs/whisper (faster-whisper + nvidia-cublas/cudnn pip 라이브러리).
  venv 부재 머신(예: 노트북 — GPU 를 qwen 이 점유)은 parser-drain.sh 가 루프째 skip.
  CUDA 실패 시 CPU int8 폴백(느리지만 작동) — device-adaptive, 머신-specific 하드코딩 없음.

사용: audio_refine.py <파일.m4a|.mp3|.wav|...> [<파일2> ...]
  각 파일에 대해 `<파일>_parse/refined.md` 생성(멱등: 있으면 skip), .parse-error 제거.
반환코드: 전건 성공 0, 일부/전부 실패 1.

환경변수(어댑터): WHISPER_MODEL(기본 large-v3) · WHISPER_DEVICE(기본 cuda)
  · WHISPER_COMPUTE(기본 float16) · SB_DATA(vault 루트)
"""
import sys, os, glob, socket, datetime

# ── LD_LIBRARY_PATH 자기-재실행: dlopen 은 프로세스 시작 시점의 경로만 본다 ──
def _ensure_cuda_libs():
    sp = os.path.join(sys.prefix, "lib",
                      f"python{sys.version_info.major}.{sys.version_info.minor}",
                      "site-packages")
    libs = [d for d in (os.path.join(sp, "nvidia", "cublas", "lib"),
                        os.path.join(sp, "nvidia", "cudnn", "lib")) if os.path.isdir(d)]
    if not libs:
        return
    cur = os.environ.get("LD_LIBRARY_PATH", "")
    if all(d in cur.split(":") for d in libs):
        return
    os.environ["LD_LIBRARY_PATH"] = ":".join(libs + ([cur] if cur else []))
    os.execv(sys.executable, [sys.executable] + sys.argv)

_ensure_cuda_libs()

VAULT = os.environ.get("SB_DATA", os.path.expanduser("~/projects/2nd-brain-vault"))
HOST = socket.gethostname()
TODAY = datetime.date.today().isoformat()
MODEL = os.environ.get("WHISPER_MODEL", "large-v3")
DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")
COMPUTE = os.environ.get("WHISPER_COMPUTE", "float16")

_model = None  # 모델 1회 로드(파일 여러 개 배치 처리)


def load_model():
    global _model
    if _model is not None:
        return _model
    from faster_whisper import WhisperModel
    try:
        _model = WhisperModel(MODEL, device=DEVICE, compute_type=COMPUTE)
    except Exception as e:                              # CUDA 불가 → CPU 폴백
        print(f"  ? {DEVICE}/{COMPUTE} 로드 실패({e}) → cpu/int8 폴백", file=sys.stderr)
        _model = WhisperModel(MODEL, device="cpu", compute_type="int8")
    return _model


def fmt_ts(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def vault_rel(path):
    try:
        return os.path.relpath(path, VAULT)
    except ValueError:
        return path


def refined_frontmatter(src_path, info):
    return (f"---\n"
            f"source_pdf: {vault_rel(src_path)}\n"
            f"base_engine: faster-whisper-{MODEL}\n"
            f"corrections: []\n"
            f"generated: {TODAY}\n"
            f"host: {HOST}\n"
            f"refine_confidence: ok\n"
            f"audio_language: {info.language} (p={info.language_probability:.2f})\n"
            f"audio_duration: {fmt_ts(info.duration)}\n"
            f"---\n\n")


def process(path):
    """파일 1개 → refined.md 생산. (ok, info|err)."""
    parse_dir = path + "_parse"
    out = os.path.join(parse_dir, "refined.md")
    os.makedirs(parse_dir, exist_ok=True)
    try:
        segs, info = load_model().transcribe(path, vad_filter=True)
        lines = [f"[{fmt_ts(s.start)}] {s.text.strip()}" for s in segs if s.text.strip()]
    except Exception as e:
        open(os.path.join(parse_dir, ".parse-error"), "w").close()
        return False, f"전사 실패({e})"
    body = "\n".join(lines) if lines else "(무발화 — VAD 가 음성 구간을 찾지 못함)"
    open(out, "w", encoding="utf-8").write(refined_frontmatter(path, info) + body + "\n")
    err = os.path.join(parse_dir, ".parse-error")
    if os.path.exists(err):
        os.remove(err)                                 # 재실행 성공 시 실패마커 제거
    return True, f"{info.language} {fmt_ts(info.duration)} {len(lines)}seg"


def main(argv):
    files = argv[1:]
    if not files:
        print("사용: audio_refine.py <파일.m4a|.mp3|...> [...]", file=sys.stderr)
        return 2
    ok = 0
    fail = []
    for f in files:
        if not os.path.exists(f):
            fail.append((f, "파일 없음"))
            continue
        out = f + "_parse/refined.md"
        if os.path.exists(out):                         # 멱등
            print(f"  skip(이미 refined): {os.path.basename(f)}")
            ok += 1
            continue
        good, info = process(f)
        if good:
            ok += 1
            print(f"  ok({info}): {os.path.basename(f)}")
        else:
            fail.append((f, info))
            print(f"  FAIL({info}): {os.path.basename(f)}", file=sys.stderr)
    print(f"\n[audio_refine] 성공 {ok} / 실패 {len(fail)}")
    for f, why in fail:
        print(f"     ✗ {os.path.basename(f)} — {why}")
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
