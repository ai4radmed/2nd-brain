# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────────────────
# webmail-sidecar — 브라우저형 스킬(webmail-watch) 전용 headed 컨테이너
#
# 보안상 OpenClaw 를 컨테이너로 이행하되, 브라우저형 스킬은 anti-headless SPA(MailPlug)
# 때문에 headless 로 안 됨 → headed-under-Xvfb 로 구동. 이 사이드카가 그 전용 런타임.
#
# 승리 레시피(2026-05-25 실측, 메모리 project-openclaw-docker-migration):
#   Playwright 공식 이미지(full chromium 크래시 無) + headed(SPA 렌더) + Xvfb 직접(행 회피).
#
# 빌드:  docker build -t webmail-watch-sidecar:local webmail-sidecar/
# 실행:  docker run --rm --shm-size=1g \
#          -v ~/.openclaw-docker:/root/.openclaw \
#          webmail-watch-sidecar:local              # 기본 CMD = kirams 폴 1회
#        ... webmail-watch-sidecar:local python run.py kirams --limit 1 --verbose   # 오버라이드
#
# 보안 권고(운영): egress 화이트리스트 = mail.kirams.re.kr 만(forward 는 KIRAMS UI 클릭이라
#   외부 SMTP egress 없음 — 런타임 통신면이 KIRAMS 하나뿐, 화이트리스트가 매우 좁음).
#   최소 마운트(secret·skill·profile). root 실행(secret 600·ben 소유 읽기; pwuser=uid1001 라
#   -u 불가). 브라우저는 베이스 이미지 /ms-playwright 재사용.
# ─────────────────────────────────────────────────────────────────────────────
FROM mcr.microsoft.com/playwright/python:v1.59.0-noble

ARG PLAYWRIGHT_VERSION=1.59.0
ARG PYOTP_VERSION=2.9.0

# 베이스엔 playwright 가 pwuser 용으로만 깔려 있음 → root 에도 설치(secret 읽기 위해 root 실행).
# pyotp 추가. 브라우저는 베이스의 /ms-playwright(PLAYWRIGHT_BROWSERS_PATH) 재사용 → 재다운 0.
RUN pip install --break-system-packages --no-cache-dir \
        "playwright==${PLAYWRIGHT_VERSION}" "pyotp==${PYOTP_VERSION}"

# headed under 가상 디스플레이 (스킬의 WEBMAIL_HEADED 토글 + channel="chromium" full chromium)
ENV HOME=/root \
    DISPLAY=:99 \
    WEBMAIL_HEADED=1 \
    PYTHONUNBUFFERED=1

COPY headed-entrypoint.sh /usr/local/bin/headed-entrypoint.sh
RUN chmod +x /usr/local/bin/headed-entrypoint.sh

# 스킬은 런타임 마운트(~/.openclaw-docker → /root/.openclaw). 그 경로에서 실행.
WORKDIR /root/.openclaw/workspace/skills/webmail-watch

ENTRYPOINT ["/usr/local/bin/headed-entrypoint.sh"]
CMD ["python", "run.py", "kirams"]
