# Claude Code 스킬 템플릿

Claude Code 세션 또는 `claude -p`(cron headless)가 실행하는 스킬. **설치 대상: `~/.claude/skills/`**.

무거운 LLM 판단(요약·PARA 분류·링크·dedup 추론)을 담는 스킬용. OpenClaw 임베디드 turn의 90초 no-output watchdog 밖에서 동작하므로 stall 위험이 없다. (런타임 선택 기준은 상위 [README](../README.md).)

## 설치

```bash
cp -r templates/skills/claude-code/<skill> ~/.claude/skills/
```

## 예정

- **brainify (thread)** — `sources/00_inbox/` 의 캡처(`_thread.md` + 첨부)를 읽어 PARA 분류·동반 노트 생성, threadId frontmatter 로 vault-wide dedup. 정규 무인은 cron → `claude -p`, 수동은 Claude Code 세션. (gmail-label-actions 가 캡처 → 이 스킬이 brainify 의 분업)
