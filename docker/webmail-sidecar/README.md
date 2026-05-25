# webmail-sidecar — 브라우저형 스킬 전용 headed 사이드카 (canonical)

webmail-watch(KIRAMS) 같은 **anti-headless SPA** 스킬은 headless 면 빈 shell 백지 →
**headed(가상 디스플레이 Xvfb)** 라야 렌더. 게이트웨이 컨테이너엔 playwright/chromium 이 없으므로,
이 **별도 사이드카**(Playwright 공식 이미지 + Xvfb)로 구동한다. 게이트웨이와 분리된 일회성 런타임.

## 파일
- `Dockerfile` — Playwright 공식 이미지(`v1.59.0-noble`) + root 에 playwright·pyotp + Xvfb entrypoint
- `headed-entrypoint.sh` — `Xvfb :99` 직접 기동(xvfb-run 래퍼는 행 → 직접) 후 `exec`
- `compose.yml` — 일회성 폴 서비스 (`run --rm`)

## 실행 / 스케줄
```bash
cd ~/projects/2nd-brain/docker/webmail-sidecar
docker compose -f compose.yml run --rm webmail-sidecar          # kirams 1회 폴
```
주기 실행 = HOST systemd-user 타이머 **`openclaw-webmail-sidecar.timer`**
(OnCalendar `Mon-Fri 08..18:00:00`, native cron 미러). `systemctl --user enable --now`.

## 승리 레시피 (2026-05-25 실측)
Playwright 공식 이미지(full chromium 크래시 無) + headed(`WEBMAIL_HEADED=1`, SPA 렌더) + **Xvfb 직접 기동**(래퍼 행 회피). 상세: [`../../docs/openclaw-docker-container.md`](../../docs/openclaw-docker-container.md) §9b, 메모리 `project-openclaw-docker-migration`.

## 런타임 의존 (주의)
- **스킬 run.py + secret + profile** 은 마운트되는 home(`~/.openclaw-docker` 의 `workspace/skills/webmail-watch/`)에 있음 = *런타임 데이터*(이 repo 에 없음). `compose.yml` 의 `WEBMAIL_HOME` 으로 override 가능.
- 스킬 run.py 변경분(native→사이드카 patch)은 vault `knowledge/02_areas/brain-system/tools/openclaw/webmail-sidecar/` 에 백업.

## 이력
- 2026-05-25 — `~/projects/openclaw-docker/webmail-sidecar/` + `docker-compose.webmail-sidecar.yml`(본가 클론 안 로컬 자산)을 여기로 canonical 화. 게이트웨이(`../openclaw-gateway/`)와 동일하게 2nd-brain repo 로 동기·재현 가능. build context `./webmail-sidecar`→`.`.
