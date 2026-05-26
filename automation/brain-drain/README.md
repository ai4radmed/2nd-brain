# brain-drain — host-측 refine+brainify 자동 드레인

`parser-drain`(extract, 결정형)의 형제. parser-drain 이 만든 `_parse/` 를 받아 **refine→brainify**
까지 무인으로 진행한다. extract 와 달리 LLM 판단이 필요하므로 **호스트 `claude -p` 헤드리스**로 호출한다.

```
parser-drain.timer (extract, 결정형 컨테이너)  ──→  _parse/{docling,mineru,diff}.json
        │  (file-state 로만 연결 — 서로 호출 안 함)
        ▼
brain-drain.timer
   Phase R refine.py scan → action=promote: refine.py promote (claude 0)
                          → action=refine : claude -p "/refine --headless <dir>"  (diverge, vision)
   Phase B brainify.py scan → 미brainify: claude -p "/brainify --headless <item>"
```

## 구성

- `brain-drain.sh` — 드레인 본체. concurrency=1(systemd 단일 + flock), per-item 실패격리,
  **비용 가드**(항목당 `--max-budget-usd`, 드레인당 누적 `CAP_GLOBAL`), 멱등(refine=refined.md /
  brainify=vault-wide dedup 마커가 done 을 skip). claude 호출은 `--permission-mode bypassPermissions`
  + headless 지시(`--append-system-prompt`)로 **묻지 않고 낙관배치+플래그**(automate-first 정책).
- `brain-drain.service` — oneshot, 위 스크립트 실행.
- `brain-drain.timer` — 종료 10분 후 재발화(`OnUnitInactiveSec`), 부팅 5분 뒤 첫 발화(extract 우선).

## 설치

```bash
cd ~/projects/2nd-brain/automation && make install-brain-drain
# 검증(1회 수동 드레인):
systemctl --user start brain-drain.service && tail -f ~/.local/state/brain-drain.log
# 이상 없으면 활성화:
systemctl --user enable --now brain-drain.timer
```

로그: `~/.local/state/brain-drain.log`. 일괄 on/off: Claude Code `/cron`. 정지: `systemctl --user disable --now brain-drain.timer`.

## 튜닝 (env, service 의 `Environment=` 또는 셸)

| env | 기본 | 의미 |
|---|---|---|
| `CAP_REFINE` | `0.50` | diverge refine 항목당 $ 상한 |
| `CAP_BRAINIFY` | `0.75` | brainify 항목당 $ 상한 |
| `CAP_GLOBAL` | `5.00` | 드레인 1회 누적 $ 상한(초과 시 중단) |
| `CLAUDE_TIMEOUT` | `600` | claude 호출당 초 |
| `BRAIN_DRAIN_MODEL` | `claude-opus-4-7` | 모델 |

## 경계

- **정본 vault = WSL2 ext4 `~/projects/2nd-brain-vault`**(git 아님·SyncThing) — commit 안 함.
- refine `match/single` 은 promote(LLM 0), `diverge` 만 claude. brainify 는 항상 claude(판단).
- 품질 보증은 **주간 감사**(`para_review: pending`·`parse_confidence|refine_confidence: low` 플래그) — `automation-review-policy`.
- 비용 폭주 방지: 항목당 + 드레인당 2단 상한. 처음엔 timer enable 전에 `start` 로 1회 실측 권장.
