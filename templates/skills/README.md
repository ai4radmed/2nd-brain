# 스킬 템플릿

복사해서 쓰는 스킬 예제 모음. **런타임이 둘이라 하위 폴더로 구분**하며, 설치(복사) 대상 디렉토리가 다르다.

| 폴더 | 런타임 | 무엇이 실행하나 | 설치(복사) 대상 |
|---|---|---|---|
| [`openclaw/`](openclaw/) | **OpenClaw** | 봇(Telegram·cron)이 발화하는 스킬. 결정형(run.py) 작업에 적합 — LLM 핫패스 최소화로 watchdog stall 회피. | `~/.openclaw/workspace/skills/` (Docker 운영 시 `~/.openclaw-docker/workspace/skills/`) |
| [`claude-code/`](claude-code/) | **Claude Code** | Claude Code 세션 또는 `claude -p`(cron)가 실행하는 스킬. 무거운 LLM 판단(요약·분류·링크)에 적합 — OpenClaw 임베디드 turn watchdog 밖에서 동작. | `~/.claude/skills/` |

## 런타임 선택 기준

**무거운 LLM 추론이 어디서 실행되느냐**로 정한다:

- 작업이 **결정형**(검색·다운로드·파일이동 등 판단 0)이고 *반응형 발화*(메신저/cron)가 필요하면 → **OpenClaw 스킬**. 에이전트는 `run.py` 한 줄만 부르므로 stall 노출이 wrapper 한 겹뿐.
- 작업이 **LLM 판단 그 자체**(PARA 분류·요약·링크)라 run.py로 환원 불가하면 → **Claude Code 스킬**. OpenClaw 임베디드 turn에서 돌리면 그 긴 추론이 90초 no-output watchdog에 걸리므로, watchdog 없는 Claude Code 런타임에서 실행.

> 자세한 배경: [`docs/openclaw-skills.md`](../../docs/openclaw-skills.md), [`docs/openclaw-docker-install.md`](../../docs/openclaw-docker-install.md)(스트리밍 stall·신뢰성 섹션).

## 설치 일반 절차

1. 해당 스킬 폴더를 위 표의 **설치 대상**으로 `cp -r`.
2. 각 스킬 README 의 "설치/적용" 절을 따른다 (env·라벨·경로 등).
3. 개인 계정·경로는 **이 공개 repo 가 아니라 런타임 쪽**(컨테이너 `.env` 등)에 둔다 — commit 누출 방지.
