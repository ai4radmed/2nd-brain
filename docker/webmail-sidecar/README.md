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
Playwright 공식 이미지(full chromium 크래시 無) + headed(`WEBMAIL_HEADED=1`, SPA 렌더) + **Xvfb 직접 기동**(래퍼 행 회피). 상세: [`../../docs/openclaw-docker-operations.md`](../../docs/openclaw-docker-operations.md) §9b, 메모리 `project-openclaw-docker-migration`.

## 마운트 (최소권한 4경로 — full home 아님)
사이드카는 `~/.openclaw` *전체*가 아니라 run.py 가 쓰는 **4경로만** 마운트한다 → root 사이드카 탈취 시에도 prod 봇토큰·gog키링(openclaw.json)·Claude OAuth(.claude)·credentials **노출 0**:

| 경로 | 성격 | 동기 |
|---|---|---|
| `~/.openclaw/workspace/skills/webmail-watch` | 스킬 코드 | GitHub(openclaw-workspace repo) |
| `~/.openclaw/secrets/webmail-watch-kirams.toml` | 로그인 secret(KIRAMS PW·OTP) | **PC별 로컬**(미동기) |
| `~/.openclaw/skills/webmail-watch/chrome-profile` | 브라우저 프로필 | PC별 로컬 |
| `~/.openclaw/agents/main/memory` | state(중복 forward 방지) | PC별 로컬 |

> KIRAMS 비번은 로그인하는 컨테이너라 불가피 노출(어떤 방식이든). 보호 가능한 것(봇토큰·OAuth·키링)은 미마운트로 차단.

## 이력
- 2026-05-25 — `~/projects/openclaw-docker/webmail-sidecar/`(본가 클론 안 로컬 자산)을 여기로 canonical 화. build context `./webmail-sidecar`→`.`.
- 2026-05-25 — 스킬·secret·profile 을 `~/.openclaw-docker`→`~/.openclaw` 로 이식, 마운트를 full home→**4경로 최소권한**으로. **로그인 fix**: MailPlug React 로그인 버튼이 `fill()` 로는 활성화 안 됨 → `press_sequentially`(실제 키 타이핑)로 교체(run.py, openclaw-workspace repo). 사이드카 end-to-end forward 검증 완료.
